#!/usr/bin/env bash
# read.sh — Poll iMessage chat.db for an inbound reply after a given timestamp
# Usage: read.sh <sent_epoch> [timeout_seconds] [poll_interval_seconds] [req_id]
# Output (stdout): The reply text, or exits 1 on timeout
#
# Reply matching (priority order):
#   1. Explicit ID match: reply contains the request ID (e.g., "a1b2c3d4 yes")
#   2. Most-recent-pending fallback: plain reply goes to the most recent pending request
#
# Uses mkdir for atomic claiming to prevent race conditions between sessions.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RECIPIENT="CHANGE_ME"
RECIPIENT_ALIASES=""
DB="${HOME}/Library/Messages/chat.db"
PENDING_DIR="/tmp/imessage-notify-pending"

# Verify Full Disk Access before proceeding
source "${SCRIPT_DIR}/check_fda.sh"
check_fda || exit 1

sent_epoch="${1:?Usage: read.sh <sent_epoch> [timeout] [poll_interval] [req_id]}"
TIMEOUT="${2:-300}"
POLL_INTERVAL="${3:-10}"
REQ_ID="${4:-}"

# Build SQL IN clause from RECIPIENT + RECIPIENT_ALIASES
# Output: 'addr1','addr2',... (single-quoted, apostrophes escaped)
build_recipient_sql() {
    local addrs=("$RECIPIENT")
    if [ -n "$RECIPIENT_ALIASES" ]; then
        for alias in $RECIPIENT_ALIASES; do
            addrs+=("$alias")
        done
    fi
    local parts=()
    for addr in "${addrs[@]}"; do
        # Escape single quotes for SQL safety (double them)
        local escaped
        escaped="$(printf '%s' "$addr" | sed "s/'/''/g")"
        parts+=("'${escaped}'")
    done
    local IFS=","
    echo "${parts[*]}"
}

# Convert unix epoch to Apple Core Data timestamp (nanoseconds since 2001-01-01)
apple_ts=$(( (sent_epoch - 978307200) * 1000000000 ))

cleanup_pending() {
    if [ -n "$REQ_ID" ] && [ -f "${PENDING_DIR}/REQ-${REQ_ID}" ]; then
        rm -f "${PENDING_DIR}/REQ-${REQ_ID}"
    fi
}
trap cleanup_pending EXIT

# Check if this request is the most recently sent pending request
is_most_recent_pending() {
    local my_epoch="$1"
    local latest_epoch=0

    for pending_file in "${PENDING_DIR}"/REQ-*; do
        [ -f "$pending_file" ] || continue
        file_epoch="$(cat "$pending_file" 2>/dev/null || echo 0)"
        if [ "$file_epoch" -gt "$latest_epoch" ] 2>/dev/null; then
            latest_epoch="$file_epoch"
        fi
    done

    [ "$my_epoch" -ge "$latest_epoch" ] 2>/dev/null
}

# Try to atomically claim a reply using mkdir (atomic on POSIX filesystems)
try_claim() {
    local msg_rowid="$1"
    local claim_dir="${PENDING_DIR}/.claim-${msg_rowid}"

    # mkdir is atomic: only one process can successfully create it
    if mkdir "$claim_dir" 2>/dev/null; then
        echo "${REQ_ID}" > "${claim_dir}/owner"
        return 0
    fi
    return 1
}

elapsed=0

while [ "$elapsed" -lt "$TIMEOUT" ]; do
    # Query all inbound messages after our sent timestamp
    # Returns: rowid|text (one per line)
    recipient_sql="$(build_recipient_sql)"
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

    if [ -n "$messages" ]; then
        # Priority 1: Look for a reply explicitly containing our request ID
        if [ -n "$REQ_ID" ]; then
            while IFS='|' read -r rowid text; do
                if echo "$text" | grep -qi "$REQ_ID"; then
                    if try_claim "$rowid"; then
                        # Strip the request ID prefix from the reply
                        clean_reply="$(echo "$text" | sed -E "s/[Rr][Ee][Qq]-?${REQ_ID}[[:space:]]*//" | sed 's/^[[:space:]]*//')"
                        [ -z "$clean_reply" ] && clean_reply="$text"
                        echo "$clean_reply"
                        exit 0
                    fi
                fi
            done <<< "$messages"
        fi

        # Priority 2: If we're the most recent pending request, claim the newest unclaimed reply
        if is_most_recent_pending "$sent_epoch"; then
            # Process newest first for fallback
            reversed="$(echo "$messages" | tail -r)"
            while IFS='|' read -r rowid text; do
                [ -z "$rowid" ] && continue
                if try_claim "$rowid"; then
                    echo "$text"
                    exit 0
                fi
            done <<< "$reversed"
        fi
    fi

    sleep "$POLL_INTERVAL"
    elapsed=$((elapsed + POLL_INTERVAL))
done

echo "TIMEOUT: No reply received within ${TIMEOUT}s" >&2
exit 1