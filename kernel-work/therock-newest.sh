#!/usr/bin/env bash
# Correctly find the NEWEST windows gfx1151 TheRock build (version-sort, not string-sort).
echo "=== fetching listing (all pages) ==="
: > /tmp/tr_all.txt
for m in 0..9; do :; done
# the listing site paginates with ?after= or ?page=; grab several and merge
for suffix in "" "&page=2" "&page=3" "&page=4" "?page=2" "?page=3"; do
  curl -s --max-time 60 "https://rocm.nightlies.amd.com/tarball/${suffix}" \
    | grep -oiE 'therock-dist-windows-gfx1151-[0-9]+[0-9a-z.-]*\.tar\.gz' >> /tmp/tr_all.txt
done
sort -u /tmp/tr_all.txt > /tmp/tr_u.txt
echo "  distinct windows gfx1151 builds found: $(wc -l < /tmp/tr_u.txt)"
echo
echo "=== VERSION-SORTED, NEWEST 12 ==="
sort -uV /tmp/tr_u.txt | tail -12
echo
echo "=== OLDEST 3 (sanity) ==="
sort -uV /tmp/tr_u.txt | head -3
echo
echo "=== anything dated after 2026-09-15? ==="
sort -uV /tmp/tr_u.txt | grep -E '2026(09(1[6-9]|[2-9][0-9])|1[0-2])' | tail -10 || echo "  none"
