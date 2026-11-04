# Exact retained Engine.cache_stats only; provenance in adjacent JSON.
class Engine:
    async def cache_stats(self):
        await self._ensure()
        if self.n_slots > 1:
            while not self.cstat.empty():
                self.cstat.get_nowait()
            async with self.wlock:
                self.w.write(b"CSTAT\n")
                await self.w.drain()
            try:
                p = await asyncio.wait_for(self.cstat.get(), timeout=10)
            except asyncio.TimeoutError:
                if self._cstat_last is None:
                    raise HTTPException(503, "the engine is inside a long request and has not "
                                        "reported its cache counters yet; try again in a moment")
                d = dict(self._cstat_last)
                d["stale_s"] = round(time.monotonic() - self._cstat_at, 1)
                return d
        else:
            async with self.slots:
                self.w.write(b"CSTAT\n")
                await self.w.drain()
                raw = await asyncio.wait_for(self.r.readline(), timeout=10)
            p = raw.decode().split()
        if not p or p[0] != "C" or len(p) < 10:
            return None
        d = {"entries": int(p[1]), "bytes": int(p[2]),
             "last_entry_bytes": int(p[3]), "max_entries": int(p[4]),
             "hits": int(p[5]), "misses": int(p[6]), "stores": int(p[7]),
             "evicted": int(p[8]), "prompt_tokens_saved": int(p[9])}
        if len(p) >= 14:
            d.update(store_ms_total=float(p[10]),
                     restore_ms_total=float(p[11]),
                     last_store_ms=float(p[12]),
                     last_restore_ms=float(p[13]))
        if len(p) >= 15:
            d["refused"] = int(p[14])
        if len(p) >= 17:
            d["rows_copied"] = int(p[15])
            d["rows_copied_ms"] = float(p[16])
        if len(p) >= 18:
            d["superseded"] = int(p[17])
        if len(p) >= 24:
            d["composable_context"] = {
                "chunks": int(p[18]), "bytes": int(p[19]),
                "stored": int(p[20]), "composed": int(p[21]),
                "evicted": int(p[22]), "composed_tokens": int(p[23])}
        if len(p) >= 37:
            d["disk"] = {
                "on": p[24] == "1", "records": int(p[25]), "lineages": int(p[26]),
                "bytes": int(p[27]), "budget_bytes": int(p[28]),
                "hits": int(p[29]), "misses": int(p[30]), "persisted": int(p[31]),
                "branches": int(p[32]), "evicted": int(p[33]), "skipped": int(p[34]),
                "restore_ms_total": float(p[35]), "restored_bytes": int(p[36])}
        if len(p) >= 39:
            d["tapped"] = int(p[37])
            d["full_hits"] = int(p[38])
        if len(p) >= 43:
            d["pool"] = {"waiting_for_room": int(p[39]),
                         "waiting_s": float(p[40]),
                         "relocated": int(p[41]),
                         "cold_resorts": int(p[42])}
        if len(p) >= 49:
            d["pool"].update(positions=int(p[44]), used=int(p[43]),
                             busy_regions=int(p[45]), held_regions=int(p[46]),
                             room_clamped=int(p[47]), moved=int(p[48]))
            self._note_pool({"pool_used": p[43], "pool_positions": p[44]})
        if len(p) >= 50:
            d["pool"]["packed"] = int(p[49])
        if len(p) >= 51:
            d["dropped"] = int(p[50])
        if len(p) >= 52:
            d["pool"]["taken_over"] = int(p[51])
        if len(p) >= 53:
            d["cache_root"] = p[52]
        if len(p) >= 55 and p[53].isdigit() and p[54].isdigit():
            d["rerendered"] = int(p[53])
            if "disk" in d:
                d["disk"]["cut_back"] = int(p[54])
        if len(p) >= 56 and p[55].isdigit() and "pool" in d:
            d["pool"]["grown"] = int(p[55])
        if len(p) >= 57 and p[56].isdigit() and "pool" in d:
            d["pool"]["grown_moved"] = int(p[56])
        self._cstat_last = dict(d)
        self._cstat_at = time.monotonic()
        return d
