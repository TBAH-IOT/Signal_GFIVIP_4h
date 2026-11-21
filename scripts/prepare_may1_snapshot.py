"""Import the verified real-data May1 comparison into the portable release cache."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mom_basis.model import BACKTEST_START_MS,HISTORY_START_MS,PROFILE_ID,BAR,COINS,SIGNAL_NAME,encode

source=Path(sys.argv[1]) if len(sys.argv)>1 else Path('D:/Live_Trade/signal_gfivip_recent_periods')
old=json.loads((source/'manifest.json').read_text(encoding='utf-8'))
assert old['period_may1_start_ms']==BACKTEST_START_MS
destination=ROOT/'data'/'continuous';destination.mkdir(exist_ok=True)
items=[]
for coin in COINS:
    item=next(r for r in old['datasets'] if r['coin']==coin)
    path=source/'datasets'/item['file']
    assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256'],coin
    frame=pd.read_csv(path,float_precision='round_trip')
    assert np.array_equal(frame.timestamp_ms,np.arange(HISTORY_START_MS,old['asof_ms']+BAR,BAR)),coin
    assert np.isfinite(frame.iloc[:-1][['open','high','low','close','basis']].to_numpy()).all(),coin
    shutil.copyfile(path,destination/path.name)
    items.append(dict(coin=coin,file=path.name,rows=len(frame),export_sha256=item['sha256']))
manifest=dict(start_ms=BACKTEST_START_MS,history_start_ms=HISTORY_START_MS,profile_id=PROFILE_ID,
    end_ms=old['asof_ms'],captured_server_ms=old['captured_server_ms'],
    last_closed_open_ms=old['asof_ms']-BAR,datasets=items,signal_name=SIGNAL_NAME,
    source='verified real Binance USD-M15m price/premium; May1 evaluation with689-bar prior warmup',
    source_manifest_sha256=hashlib.sha256((source/'manifest.json').read_bytes()).hexdigest(),
    last_row_policy='current15m candle contributes ONLY its OPEN')
(destination/'manifest.json').write_text(encode(manifest),encoding='utf-8')
print(encode(dict(imported=len(items),start_ms=BACKTEST_START_MS,history_start_ms=HISTORY_START_MS,end_ms=manifest['end_ms'])))
