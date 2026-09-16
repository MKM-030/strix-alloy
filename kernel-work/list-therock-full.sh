#!/usr/bin/env bash
# List the S3 bucket properly (paginated) and find the newest windows gfx1151 build.
BASE="https://rocm.nightlies.amd.com/tarball/"
TOKEN=""
FOUND=""
for page in 1 2 3 4 5 6 7 8; do
  URL="${BASE}?list-type=2&prefix=therock-dist-windows-gfx1151&max-keys=1000"
  [ -n "$TOKEN" ] && URL="${URL}&continuation-token=${TOKEN}"
  OUT=$(curl -s --max-time 90 "$URL")
  echo "$OUT" | grep -oE '<Key>[^<]*</Key>' | sed 's/<[^>]*>//g' >> /tmp/tr_pages.txt
  TOKEN=$(echo "$OUT" | grep -oE '<NextContinuationToken>[^<]*' | sed 's/<[^>]*>//')
  [ -z "$TOKEN" ] && break
done
echo "=== total window-gfx1151 keys: $(sort -u /tmp/tr_pages.txt | wc -l) ==="
echo
echo "=== NEWEST 15 windows gfx1151 builds ==="
sort -u /tmp/tr_pages.txt | tail -15
echo
echo "=== does anything newer than 20260915 exist? ==="
grep -oE '2026091[5-9]|202609[2-9][0-9]' /tmp/tr_pages.txt | sort -u | tail -10 || echo "  none"
echo
echo "=== verify our current build URL still resolves ==="
curl -s -o /dev/null -w "  10.2.0a20260915 -> HTTP %{http_code}\n" --max-time 60 \
  "${BASE}therock-dist-windows-gfx1151-10.2.0a20260915.tar.gz"
