#!/usr/bin/env bash
# Atomic state file updater for ZCombinator agents
# Usage:
#   update-state.sh <file> <json-content>     -- Replace entire file
#   update-state.sh --append <file> <json-line> -- Append line (for activity.jsonl)
#
# All writes use temp file + mv for atomicity.

set -euo pipefail

STATE_DIR="$(cd "$(dirname "$0")/state" && pwd)"

if [ "${1:-}" = "--append" ]; then
  FILE="$STATE_DIR/$(basename "$2")"
  CONTENT="$3"
  TMPFILE=$(mktemp "$STATE_DIR/.tmp.XXXXXX")
  if [ -f "$FILE" ]; then
    cp "$FILE" "$TMPFILE"
  fi
  echo "$CONTENT" >> "$TMPFILE"
  mv "$TMPFILE" "$FILE"
else
  FILE="$STATE_DIR/$(basename "$1")"
  CONTENT="$2"
  TMPFILE=$(mktemp "$STATE_DIR/.tmp.XXXXXX")
  echo "$CONTENT" > "$TMPFILE"
  mv "$TMPFILE" "$FILE"
fi
