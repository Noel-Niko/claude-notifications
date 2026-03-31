# ADR: attributedBody Fallback for macOS Sequoia

**Status:** Implemented
**Date:** 2026-03-31

## Problem

On macOS Sequoia, iMessage inconsistently stores message content in the `attributedBody` column (binary typedstream blob) instead of the `text` column (plain text). The original `read.sh` SQL query filtered with `AND m.text IS NOT NULL AND m.text != ''`, silently dropping these messages. User replies ("Yes", "Switch to IDE mode") were stored only in `attributedBody` and never seen by `read.sh`.

Two compounding issues:

1. **NULL text drops messages.** Any message stored only in `attributedBody` was invisible to the polling loop.
2. **is_from_me filter breaks on NULL text.** The SQL filter `m.text NOT LIKE '[%|REQ-%]%'` evaluates to NULL when `text` is NULL. In SQL, `FALSE OR NULL` is NULL (falsy), so **all** blob-only `is_from_me=1` messages were excluded — not just Claude-tagged ones. This extended the known ~6% self-reply false negative rate to 100% for blob-only messages.

### Evidence

Database analysis on macOS Sequoia 15.4:

| is_from_me | Storage  | Count |
|------------|----------|-------|
| 0          | text     | 31,931 |
| 0          | blob     | 807    |
| 1          | text     | 5,339  |
| 1          | blob     | 2,677  |

~10% of messages (3,484 of 40,754) are stored only in `attributedBody`.

## Decision

Replace the `sqlite3` CLI call in `read.sh` with a Python helper script (`query_messages.py`) that queries both `text` and `attributedBody`, decodes the typedstream blob when `text` is NULL, and applies the `is_from_me` tag filter on the decoded text in Python instead of SQL.

### Alternatives considered

| Option | Pros | Cons |
|--------|------|------|
| **SQL-only extraction** (SUBSTR, hex functions) | No new dependency | Fragile, can't reliably parse variable-length encoding in SQLite |
| **Python one-liner in bash** | No new file | Unreadable, untestable, quoting hell |
| **Full Python rewrite of read.sh** | Cleaner long-term | Scope creep; claim mechanism, pending files, and polling are fine in bash |
| **Python helper script** (chosen) | Testable, minimal change to read.sh, standard library only | Adds a .py file to the skill directory |

### Why Python

- Already a declared dependency in SKILL.md (`python3` required for JSON injection and hooks)
- `sqlite3` module is in the standard library — no pip install needed
- The typedstream binary format requires byte-level parsing that is trivial in Python but impractical in SQL or bash

## Typedstream Format

The `attributedBody` column contains an `NSAttributedString` serialized via Apple's [typedstream](https://en.wikipedia.org/wiki/Typedstream) format (NSArchiver, not NSKeyedArchiver). The plain text is embedded as a length-prefixed UTF-8 string.

### Structure (relevant portion)

```
... NSString <header_bytes> 0x2b <length_encoding> <text_bytes> 0x86 ...
```

### Length encoding

| First byte | Meaning | Example |
|-----------|---------|---------|
| `0x00`-`0x7F` | Direct single-byte length | `0x03` = 3 bytes ("Yes") |
| `0x80`+ | Multi-byte: `(byte & 0x7F) + 1` bytes follow, little-endian | `0x81 0x1d 0x01` = `0x011d` = 285 bytes |

The multi-byte encoding uses **little-endian** byte order and `(indicator & 0x7F) + 1` additional bytes — not `(indicator & 0x7F)` bytes in big-endian. The latter coincidentally works when the high byte is `0x00` (strings 128-255 bytes) but silently truncates longer strings.

### Leading control characters

Some decoded strings begin with control characters (`0x00`-`0x1F`) that are typedstream encoding artifacts. These are stripped after decoding.

### Extraction algorithm

```
1. Find the byte sequence "NSString" in the blob
2. After NSString, find the next 0x2b ('+') byte
3. Read the byte after '+':
   a. If < 0x80: this is the string length directly
   b. If >= 0x80: read (byte & 0x7F) + 1 additional bytes as little-endian length
4. Read that many UTF-8 bytes
5. Strip leading control characters (0x00-0x1F)
```

## Implementation

### Files changed

| File | Change |
|------|--------|
| `src/imessage-notify/query_messages.py` | **New.** Python helper: SQLite query + typedstream decoder. CLI interface (`rowid\|text` output) and importable API (`extract_text_from_typedstream`, `query_messages`). |
| `src/imessage-notify/read.sh` | Replaced 12-line `sqlite3` CLI call with single `python3 query_messages.py` call. Rest of script unchanged. |
| `tests/test_imessage_scripts.py` | Added `TestAttributedBodyFallback` (10 tests). Updated `TestReadIsFromMeFix` (3 tests adapted for new architecture). |
| `tests/conftest.py` | Added `TYPEDSTREAM_BLOBS` (4 real captured blobs), `create_chat_db()`, `chat_db` fixture, `load_query_messages_module()`. |

### How read.sh calls query_messages.py

Before:
```bash
messages="$(sqlite3 "$DB" "
    SELECT m.ROWID, m.text
    FROM message m
    JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
    JOIN chat c ON cmj.chat_id = c.ROWID
    WHERE c.chat_identifier IN (${recipient_sql})
      AND m.date > ${apple_ts}
      AND (m.is_from_me = 0 OR m.text NOT LIKE '[%|REQ-%]%')
      AND m.text IS NOT NULL
      AND m.text != ''
    ORDER BY m.date ASC;
" 2>/dev/null || true)"
```

After:
```bash
messages="$(python3 "${SCRIPT_DIR}/query_messages.py" "$DB" "$recipient_sql" "$apple_ts" 2>/dev/null || true)"
```

The Python script handles text/blob resolution and the `is_from_me` filter internally using a regex (`^\[.+\|REQ-[0-9a-f]+\]`) on the decoded text. Output format is identical: `rowid|text` per line.

## Consequences

### Positive

- User replies stored only in `attributedBody` are now recovered (fixes the macOS Sequoia bug)
- The `is_from_me` Claude-tag filter now works correctly for blob-only messages
- The extraction logic is unit-testable with real captured blobs
- No new external dependencies (uses `sqlite3` from Python's standard library)

### Negative

- Adds a Python file to the skill directory (9 scripts + 1 .py, up from 9 scripts)
- The typedstream format is undocumented by Apple; if the serialization format changes in a future macOS release, the extraction may need updating
- The `text` column behavior may vary by macOS version — future versions could store `text` consistently again, making the fallback unnecessary (but harmless)

### Neutral

- `read.sh` still owns the polling loop, claim mechanism, and priority matching — no behavioral change there
- `build_recipient_sql()` remains in `read.sh` and its output is passed to the Python script as an argument

## Test coverage

10 new tests in `TestAttributedBodyFallback`:

| Test | What it verifies |
|------|-----------------|
| `test_extract_text_from_typedstream_valid` | Correct text from real typedstream blob |
| `test_extract_text_from_typedstream_with_leading_control_chars` | Leading 0x00-0x1F stripped |
| `test_extract_text_from_typedstream_empty_blob` | Returns None for empty/None |
| `test_extract_text_from_typedstream_no_nsstring_marker` | Returns None for malformed blob |
| `test_query_prefers_text_over_attributed_body` | text column wins when both exist |
| `test_query_recovers_text_from_attributed_body` | NULL text + valid blob returns decoded text |
| `test_query_skips_null_text_null_blob` | Both NULL → row excluded |
| `test_query_filters_claude_tagged_from_blob` | is_from_me=1 + Claude-tagged blob → excluded |
| `test_query_passes_untagged_from_blob` | is_from_me=1 + untagged blob → included |
| `test_query_output_format_matches_sqlite3` | CLI output is `rowid\|text` per line |

Test fixtures use 4 real typedstream blobs captured from a macOS Sequoia chat.db, covering short messages, long messages with multi-byte length encoding, Claude-tagged messages, and messages with leading control characters.

Total test suite after change: 221 passed (76 in `test_imessage_scripts.py`).
