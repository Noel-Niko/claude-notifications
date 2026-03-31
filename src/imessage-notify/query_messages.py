"""Query iMessage chat.db with attributedBody fallback.

When the text column is NULL (common on macOS Sequoia), decodes the message
content from the attributedBody column (Apple typedstream format).

Usage (CLI):
    python3 query_messages.py <db_path> <recipient_sql> <apple_ts>

    recipient_sql: SQL IN clause values, e.g. "'+13522339160','user@example.com'"
    apple_ts:      Apple Core Data timestamp (nanoseconds since 2001-01-01)

Output:
    rowid|text (one per line, matching sqlite3 pipe-delimited format)

Importable API:
    extract_text_from_typedstream(blob) -> str | None
    query_messages(db_path, recipient_sql, apple_ts) -> list[tuple[int, str]]
"""

import re
import sqlite3
import sys


def extract_text_from_typedstream(blob):
    """Extract plain text from a typedstream-encoded attributedBody blob.

    The attributedBody column in chat.db stores an NSAttributedString serialized
    via Apple's typedstream (NSArchiver) format. The plain text is encoded as a
    length-prefixed UTF-8 string following the NSString class marker.

    Format:
        ... NSString <header_bytes> 0x2b <length> <text_bytes> 0x86 ...

    Length encoding:
        - If first byte < 0x80: single-byte length
        - If first byte >= 0x80: (byte & 0x7f) gives number of following
          big-endian length bytes

    Returns the decoded text with leading control characters stripped,
    or None if the blob is empty, malformed, or missing the NSString marker.
    """
    if not blob:
        return None

    marker = b"NSString"
    idx = blob.find(marker)
    if idx < 0:
        return None

    after = blob[idx + len(marker) :]
    plus_idx = after.find(b"\x2b")
    if plus_idx < 0:
        return None

    data = after[plus_idx + 1 :]
    if not data:
        return None

    length_byte = data[0]
    if length_byte < 0x80:
        text_start = 1
        text_len = length_byte
    else:
        # Multi-byte length: (indicator & 0x7F) + 1 bytes, little-endian
        num_bytes = (length_byte & 0x7F) + 1
        if len(data) < 1 + num_bytes:
            return None
        text_len = int.from_bytes(data[1 : 1 + num_bytes], "little")
        text_start = 1 + num_bytes

    if len(data) < text_start + text_len:
        return None

    text_bytes = data[text_start : text_start + text_len]
    try:
        text = text_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = text_bytes.decode("utf-8", errors="replace")

    # Strip leading control characters (0x00-0x1f) that appear as
    # typedstream encoding artifacts
    text = text.lstrip(
        "\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c"
        "\x0d\x0e\x0f\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19"
        "\x1a\x1b\x1c\x1d\x1e\x1f"
    )

    return text if text else None


# Pattern matching Claude-tagged messages: [repo-name|REQ-hexid] ...
_CLAUDE_TAG_RE = re.compile(r"^\[.+\|REQ-[0-9a-f]+\]")


def query_messages(db_path, recipient_sql, apple_ts):
    """Query chat.db for messages, falling back to attributedBody when text is NULL.

    Args:
        db_path: Path to the chat.db SQLite database.
        recipient_sql: SQL IN clause values (e.g. "'+13522339160','user@icloud.com'").
        apple_ts: Apple Core Data timestamp (int). Only messages after this are returned.

    Returns:
        List of (rowid, text) tuples, ordered by date ascending.
        Excludes:
        - Messages where both text and attributedBody are NULL/empty
        - Claude-tagged messages (is_from_me=1 AND text matches [repo|REQ-xxx])
    """
    apple_ts = int(apple_ts)

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(
            f"""
            SELECT m.ROWID, m.text, m.attributedBody, m.is_from_me
            FROM message m
            JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
            JOIN chat c ON cmj.chat_id = c.ROWID
            WHERE c.chat_identifier IN ({recipient_sql})
              AND m.date > {apple_ts}
            ORDER BY m.date ASC
            """
        )

        results = []
        for rowid, text, attributed_body, is_from_me in cursor:
            # Prefer text column; fall back to attributedBody decoding
            msg_text = text if text else extract_text_from_typedstream(attributed_body)

            # Skip if no text could be recovered
            if not msg_text:
                continue

            # Apply is_from_me filter: exclude Claude-tagged messages
            if is_from_me == 1 and _CLAUDE_TAG_RE.match(msg_text):
                continue

            results.append((rowid, msg_text))

        return results
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(
            "Usage: query_messages.py <db_path> <recipient_sql> <apple_ts>",
            file=sys.stderr,
        )
        sys.exit(1)

    db_path = sys.argv[1]
    recipient_sql = sys.argv[2]
    apple_ts = sys.argv[3]

    rows = query_messages(db_path, recipient_sql, apple_ts)
    for rowid, text in rows:
        print(f"{rowid}|{text}")
