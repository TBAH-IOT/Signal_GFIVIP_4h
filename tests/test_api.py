import asyncio
import json
from fastapi.testclient import TestClient
from mom_basis.api import ProcessLock, create_app


def test_api_contract_latest_five_and_model_units(tmp_path):
    app=create_app(tmp_path,live=False,use_snapshot=False)
    with TestClient(app) as client:
        assert client.get('/').status_code == 200
        assert client.get('/assets/app.js').status_code == 200
        model=client.get('/api/model').json()
        assert model['cost_bps']==10 and model['order_budget_usdt']==500
        assert model['stop_loss'] is None and model['broker_execution'] is False
        data=client.get('/api/notifications').json()
        assert len(data['items'])==5 and data['unread_count']==0
        assert all(x['status_label']=='Đã kết thúc' for x in data['items'])
        sid=data['items'][0]['id']
        detail=client.get('/api/signals/'+sid).json()
        assert detail['forecast']['latest_training_exit_ms']<=detail['entry_ms']
        assert client.post('/api/notifications/'+sid+'/read').status_code==200
        assert client.get('/api/signals/not-an-id').status_code==404
        stats=client.get('/api/stats').json()
        assert stats['n_trades']==241 and stats['net_profit']>.10
        assert stats['full_equity_points']==17268
        assert len(stats['equity_curve'])<=1001
        assert client.get('/api/stats?coin=BTC').json()['n_trades']==9
        assert client.get('/api/stats?coin=FAKE').status_code==422
        assert client.get('/api/health').json()['mode']=='offline'
        assert client.get('/openapi.json').status_code==200


def test_process_lock_rejects_second_writer(tmp_path):
    import pytest
    first=ProcessLock(tmp_path/'worker.lock')
    try:
        with pytest.raises(RuntimeError):
            ProcessLock(tmp_path/'worker.lock')
    finally:
        first.close()


def test_sse_generator_initial_snapshot_and_quote_event(tmp_path):
    # Test streaming body directly to avoid a TestClient buffering an infinite SSE stream.
    app=create_app(tmp_path,live=False)
    route=next(r for r in app.routes if getattr(r,'path',None)=='/api/events')
    class Request:
        headers={}
        query_params={}
        async def is_disconnected(self): return False
    async def run():
        response=await route.endpoint(Request())
        gen=response.body_iterator
        assert 'retry:' in await anext(gen)
        assert 'event: snapshot' in await anext(gen)
        assert 'event: quotes' in await anext(gen)
        await gen.aclose()
    asyncio.run(run())


def test_first_sse_connection_does_not_replay_old_alerts(tmp_path):
    app=create_app(tmp_path,live=False)
    with app.state.store.tx() as c:
        app.state.store.emit(c,'signal.opened',{'signal_id':'old-event','entry_ms':1},1)
    route=next(r for r in app.routes if getattr(r,'path',None)=='/api/events')
    class Request:
        headers={}
        query_params={}
        async def is_disconnected(self): return False
    async def run():
        response=await route.endpoint(Request())
        gen=response.body_iterator
        await anext(gen)
        snapshot=await anext(gen)
        assert 'id: 1' in snapshot
        assert 'event: quotes' in await anext(gen)
        await gen.aclose()
    asyncio.run(run())
