from __future__ import annotations

import asyncio
import logging
import time
import httpx
import numpy as np
import pandas as pd
from .model import BAR, COINS, HOLD, LIVE_WARMUP

log = logging.getLogger(__name__)


class BinancePublic:
    """Public USD-M market data only. No API key, signed requests, or orders."""
    def __init__(self, base_url="https://fapi.binance.com"):
        self.client = httpx.AsyncClient(base_url=base_url, timeout=15,
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=4))
        self.sem = asyncio.Semaphore(4)

    async def close(self):
        await self.client.aclose()

    async def get(self, endpoint, **params):
        for attempt in range(4):
            async with self.sem:
                response = await self.client.get(endpoint, params=params)
            if response.status_code in (418, 429):
                delay = min(60, max(1, float(response.headers.get("Retry-After", 30))))
                if attempt == 3:
                    response.raise_for_status()
                await asyncio.sleep(delay)
                continue
            if response.status_code >= 500 and attempt < 3:
                await asyncio.sleep(2**attempt)
                continue
            response.raise_for_status()
            return response.json()
        raise RuntimeError("Binance retry budget exhausted")

    async def server_ms(self):
        return int((await self.get("/fapi/v1/time"))["serverTime"])

    async def candles(self, coin, start=None, end=None, limit=1000):
        params = dict(symbol=coin+"USDT", interval="15m", limit=limit)
        if start is not None:
            params["startTime"] = int(start)
        if end is not None:
            params["endTime"] = int(end)
        price, premium = await asyncio.gather(self.get("/fapi/v1/klines", **params),
                                              self.get("/fapi/v1/premiumIndexKlines", **params))
        if not isinstance(price, list) or not isinstance(premium, list):
            raise ValueError(f"Invalid kline response for {coin}")
        p = {int(x[0]): float(x[4]) for x in premium}
        rows = [dict(timestamp_ms=int(x[0]), open=float(x[1]), high=float(x[2]),
                     low=float(x[3]), close=float(x[4]), basis=p.get(int(x[0]), np.nan)) for x in price]
        d = pd.DataFrame(rows, columns=["timestamp_ms", "open", "high", "low", "close", "basis"])
        if not d.empty and (d.timestamp_ms.duplicated().any() or (d.timestamp_ms % BAR != 0).any()):
            raise ValueError("Duplicate or misaligned candles")
        return d

    async def price_candles(self, coin, start, end):
        rows = await self.get("/fapi/v1/klines", symbol=coin+"USDT", interval="15m",
                              startTime=start, endTime=end, limit=1000)
        return [dict(time_ms=int(x[0]), price=float(x[1])) for x in rows if start <= int(x[0]) <= end]

    async def quotes(self, now_ms):
        rows = await self.get("/fapi/v2/ticker/price")
        return {r["symbol"][:-4]: dict(price=float(r["price"]), exchange_ms=int(r["time"]),
                    received_ms=now_ms) for r in rows if r["symbol"] in {c+"USDT" for c in COINS}}


class Worker:
    """Bootstrap/catch up the FULL reference history, then follow every 15m boundary."""
    def __init__(self,store,source=None,poll_seconds=5):
        self.store=store
        self.source=source or BinancePublic()
        self.poll_seconds=poll_seconds
        self.offset=0
        self.last_sync=0
        self.started=False

    def now(self):
        return int(time.time()*1000)+self.offset

    async def sync_clock(self):
        before=int(time.time()*1000)
        server=await self.source.server_ms()
        after=int(time.time()*1000)
        self.offset=server-(before+after)//2
        self.last_sync=after
        self.store.set_meta("clock_offset_ms",self.offset)

    async def cycle(self):
        from .continuous import synchronize
        if not self.last_sync or int(time.time()*1000)-self.last_sync>300_000:
            await self.sync_clock()
        now=self.now();boundary=now//BAR*BAR
        if not self.started or self.store.meta("continuous_asof_ms")!=boundary:
            self.store.set_meta("worker",dict(mode="live_public_data",feed_status="syncing",
                heartbeat_ms=now,clock_offset_ms=self.offset))
            if not self.store.meta("forward_started_ms"):
                self.store.set_meta("forward_started_ms",now)
            await synchronize(self.store,self.source,live_notices=True)
            self.started=True
        now=self.now()
        quotes=await self.source.quotes(now)
        self.store.set_meta("quotes",quotes)
        self.store.set_meta("worker",dict(mode="live_public_data",feed_status="ok",
            heartbeat_ms=now,quote_count=len(quotes),clock_offset_ms=self.offset,
            last_boundary_ms=self.store.meta("continuous_asof_ms"),coin_errors={},not_ready=[]))

    async def run(self):
        try:
            while True:
                try:
                    await self.cycle()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    log.exception("Continuous history synchronization will retry")
                    self.store.set_meta("worker",dict(mode="live_public_data",feed_status="error",
                        heartbeat_ms=self.now(),error=f"{type(exc).__name__}: {exc}"))
                    status=self.store.meta("history_status",{})
                    status.update(phase="error",error=f"{type(exc).__name__}: {exc}",updated_at_ms=self.now())
                    self.store.set_meta("history_status",status)
                await asyncio.sleep(self.poll_seconds)
        finally:
            await self.source.close()
