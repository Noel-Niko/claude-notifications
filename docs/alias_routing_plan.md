# Plan: Fix reply routing for multiple iMessage identities

a## Status: COMPLETE

## Problem

When `send.sh` sends to `nnosse@wgu.edu`, the reply from the phone comes back
from the user's default "Send & Receive" address (`+13522339160`). macOS Messages
puts that reply in a separate chat (`chat_identifier = '+13522339160'`), but
`read.sh` only queries `WHERE c.chat_identifier = 'nnosse@wgu.edu'` — so the
reply is never found.

## Approach: `RECIPIENT_ALIASES` in `read.sh`

Add a `RECIPIENT_ALIASES` variable that lists all alternate iMessage addresses.
The SQL query changes from `= 'recipient'` to `IN ('recipient', 'alias1', ...)`.
Backwards-compatible: empty aliases = current single-recipient behavior.

## Files to modify

### 1. `src/imessage-notify/read.sh`

- Add `RECIPIENT_ALIASES=""` after `RECIPIENT="CHANGE_ME"` (line 15)
- Add `build_recipient_sql()` function that:
  - Starts with RECIPIENT
  - Splits RECIPIENT_ALIASES on spaces and appends each
  - Escapes single quotes in addresses (double them: `''`)
  - Returns `'addr1','addr2',...` for the SQL IN clause
- Change line 77 from `WHERE c.chat_identifier = '${RECIPIENT}'`
  to `WHERE c.chat_identifier IN ($(build_recipient_sql))`

### 2. `src/imessage-notify/whitelist_commands.sh`

- Add `configure_aliases()` function that updates `RECIPIENT_ALIASES` in read.sh via sed
- Update main to accept `--aliases "addr1 addr2"` flag (optional, after positional recipient)
- Only touches read.sh (send.sh always sends to one address)

### 3. `install.sh`

- **Step 2 (detect existing)**: Also detect and preserve `EXISTING_ALIASES` from installed `read.sh`
- **Step 3b (after phone prompt)**: Prompt for additional iMessage aliases
  - Attempt auto-detection from `chat.db` via `person_centric_id` (Ventura+)
    - Wrap in try/catch — auto-detect may fail if FDA not yet granted
    - If it works, show discovered addresses and ask user to confirm
    - If it fails, fall through to manual entry
  - Manual fallback: "Enter your other iMessage addresses, space-separated, or press Enter to skip"
  - Pre-populate with EXISTING_ALIASES if reinstalling
- **Parse flags**: Add `--aliases "addr1 addr2"` for non-interactive mode
- **Step 6**: Pass aliases to `whitelist_commands.sh` via `--aliases`

### 4. `src/imessage-notify/SKILL.md`

- Add "Reply Routing / Aliases" section explaining:
  - Why replies may arrive on a different chat identifier
  - How RECIPIENT_ALIASES works
  - How to reconfigure: `whitelist_commands.sh <recipient> --aliases "addr1 addr2"`

### 5. `tests/conftest.py`

- Add `get_aliases()` helper to extract `RECIPIENT_ALIASES` from read.sh

### 6. `tests/test_imessage_scripts.py`

- Add `TestReadRecipientAliases` class:
  - `test_aliases_variable_exists` — `RECIPIENT_ALIASES` present in read.sh
  - `test_build_recipient_sql_single` — RECIPIENT only, no aliases → `IN ('addr')`
  - `test_build_recipient_sql_with_aliases` — RECIPIENT + aliases → `IN ('addr','alias1','alias2')`
  - `test_empty_aliases_backwards_compatible` — empty string = same as before
  - `test_sql_quoting_special_chars` — addresses with apostrophes are escaped

### 7. `tests/test_whitelist_commands.py`

- Add `TestAliasConfiguration` class:
  - `test_aliases_set_in_read_sh` — aliases written to read.sh
  - `test_aliases_not_in_send_sh` — send.sh should NOT have aliases
  - `test_aliases_with_phone_and_email_mix` — mixed format aliases
  - `test_aliases_overwrite_previous` — re-running updates aliases
  - `test_aliases_idempotent` — same aliases twice = no duplication
  - `test_no_aliases_leaves_empty` — no aliases arg = empty string preserved

## Steps

- [x] Step 1: Write tests first (TDD)
- [x] Step 2: Implement `read.sh` changes (RECIPIENT_ALIASES + build_recipient_sql)
- [x] Step 3: Implement `whitelist_commands.sh` changes (configure_aliases + --aliases flag)
- [x] Step 4: Implement `install.sh` changes (preserve aliases, prompt, auto-detect, --aliases flag)
- [x] Step 5: Update `SKILL.md` with alias documentation
- [x] Step 6: Update `conftest.py` with get_aliases helper
- [x] Step 7: Run tests, fix failures