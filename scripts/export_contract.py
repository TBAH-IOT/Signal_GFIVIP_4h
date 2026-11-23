import json
from pathlib import Path
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
from mom_basis.api import create_app

temp_parent=ROOT/'.contract_tmp';temp_parent.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=temp_parent) as state:
    app=create_app(state,live=False)
    with TestClient(app) as client:
        spec=client.get('/openapi.json').json()
        (ROOT/'docs'/'openapi.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding='utf-8')
        notif=client.get('/api/notifications').json()
        stats=client.get('/api/stats?chart_points=100').json()
        examples=dict(model=client.get('/api/model').json(),notifications=notif,
            signal_detail=client.get('/api/signals/'+notif['items'][0]['id']).json(),
            trade_archive=client.get('/api/trades',params={'coin':notif['items'][0]['coin'],'limit':3}).json(),
            trade_detail=client.get('/api/trades/'+notif['items'][0]['id']).json(),
            stats_total=stats,stats_coin=client.get('/api/stats?coin=BTC&chart_points=100').json(),
            health=client.get('/api/health').json())
        (ROOT/'docs'/'api_examples.json').write_text(json.dumps(examples,ensure_ascii=False,indent=2),encoding='utf-8')
print('Exported OpenAPI and real-data sample payloads')
