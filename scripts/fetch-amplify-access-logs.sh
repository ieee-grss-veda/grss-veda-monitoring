#!/usr/bin/env bash
#
# Walk backward through Amplify access logs in small windows and stitch
# them into one CSV. Works with both BSD (macOS) and GNU (Linux) date.
#
# Usage:
#   ./fetch-amplify-access-logs.sh                         # defaults below
#   OLDEST=2026-04-01 CHUNK_DAYS=7 ./fetch-amplify-access-logs.sh
#   DOMAIN=dev.veda.grss.cloud ./fetch-amplify-access-logs.sh
#
# Notes:
# - The API caps each request at a 14-day window and errors ("reduce time
#   range") when a window holds too much data; on failure the script halves
#   the window down to 1 day before skipping past it.
# - Amplify retains access logs for the lifetime of the app, so OLDEST can
#   go back as far as the app exists.

set -euo pipefail

APP_ID="${APP_ID:-d22mb05yrshldh}"
DOMAIN="${DOMAIN:-veda.grss-ieee.org}"
REGION="${REGION:-us-west-2}"
CHUNK_DAYS="${CHUNK_DAYS:-7}"          # window size to try first
OLDEST="${OLDEST:-2026-06-01}"         # YYYY-MM-DD; stop walking back here
OUT="${OUT:-amplify-access-logs-$(echo "$DOMAIN" | tr '.' '-').csv}"

# BSD vs GNU date portability
if date -v -1d +%s >/dev/null 2>&1; then
  epoch_of() { date -j -f %Y-%m-%d "$1" +%s; }   # YYYY-MM-DD -> epoch
  day_of() { date -r "$1" +%F; }                 # epoch -> YYYY-MM-DD
else
  epoch_of() { date -d "$1" +%s; }
  day_of() { date -d "@$1" +%F; }
fi

oldest_epoch=$(epoch_of "$OLDEST")
end=$(date +%s)
total_rows=0
> "$OUT"

fetch_window() {  # $1=start $2=end -> prints logUrl or returns 1
  aws amplify generate-access-logs \
    --app-id "$APP_ID" \
    --domain-name "$DOMAIN" \
    --start-time "$1" --end-time "$2" \
    --region "$REGION" \
    --query logUrl --output text 2>/dev/null
}

while [ "$end" -gt "$oldest_epoch" ]; do
  days=$CHUNK_DAYS
  url=""
  while [ "$days" -ge 1 ]; do
    start=$((end - days * 86400))
    [ "$start" -lt "$oldest_epoch" ] && start=$oldest_epoch
    echo "requesting $(day_of "$start") .. $(day_of "$end") (${days}d)"
    if url=$(fetch_window "$start" "$end") && [ -n "$url" ] && [ "$url" != "None" ]; then
      break
    fi
    url=""
    days=$((days / 2))
    echo "  window too large or failed; retrying with ${days}d"
  done

  if [ -z "$url" ]; then
    echo "  giving up on window ending $(day_of "$end"); skipping back 1 day"
    end=$((end - 86400))
    continue
  fi

  chunk=$(mktemp)
  curl -sf "$url" -o "$chunk"
  rows=$(($(wc -l < "$chunk") - 1))
  [ "$rows" -lt 0 ] && rows=0
  if [ -s "$OUT" ]; then
    tail -n +2 "$chunk" >> "$OUT"       # drop repeated CSV header
  else
    cat "$chunk" >> "$OUT"
  fi
  rm -f "$chunk"
  total_rows=$((total_rows + rows))
  echo "  got $rows rows (total $total_rows)"

  end=$start
  sleep 2
done

echo
echo "done: $total_rows rows -> $OUT"
echo "date range in file:"
cut -d, -f1 "$OUT" | grep -v '^date$' | sort -u | sed -n '1p;$p'
