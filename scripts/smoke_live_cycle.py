"""Bounded live public-data worker check; writes only isolated local review state."""
import asyncio
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mom_basis.feed import Worker
from mom_basis.model import encode
from mom_basis.store import Store

async def run():
    store=Store(ROOT/'.live_probe_v1_1'/'probe.sqlite3');store.seed()
    worker=Worker(store)
    try:
        await worker.cycle()
        await worker.cycle()
        result=dict(worker=store.meta('worker'),marks_quality=store.meta('marks_quality'),
            history=store.meta('history_status'),summary={k:v for k,v in store.metrics().items() if k!='equity_curve'},
            pending_count=len(store.pending()),event_count=store.latest_event_id(),
            source='real Binance public REST, two bounded cycles',orders_submitted=0)
        (ROOT/'evidence'/'live_worker_smoke.json').write_text(encode(result),encoding='utf-8')
        print(encode(result))
    finally:
        await worker.source.close()

asyncio.run(run())
