from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import time
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from .feed import Worker
from .model import BAR, COINS, MODEL_ID, ROOT, SIGNAL_NAME, SPEC, SPEC_HASH, VERSION, PROFILE_ID, encode
from .store import Store


class ProcessLock:
    """One worker per SQLite state directory, including separate server invocations."""
    def __init__(self, path):
        self.file = open(path, "a+b")
        self.file.seek(0)
        if os.fstat(self.file.fileno()).st_size == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise RuntimeError("Another worker owns this state directory; use exactly one server worker") from None

    def close(self):
        if os.name == "nt":
            import msvcrt
            self.file.seek(0)
            msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
        self.file.close()

    def __enter__(self):
        return self

    def __exit__(self,*args):
        self.close()


def create_app(state_dir=None, live=None, use_snapshot=True):
    state = Path(state_dir or os.getenv("GFI_STATE_DIR", ROOT/"state"))
    state.mkdir(parents=True, exist_ok=True)
    store = Store(state/"model.sqlite3")
    store.seed()
    live = os.getenv("GFI_MODE", "live") == "live" if live is None else live
    secret_path = state/"session.key"
    # Atomic creation, safe under simultaneous imports.
    if not secret_path.exists():
        try:
            with secret_path.open("xb") as f:
                f.write(secrets.token_bytes(32))
        except FileExistsError:
            pass
    secret = secret_path.read_bytes()

    def signature(uid):
        return hmac.new(secret, uid.encode(), hashlib.sha256).hexdigest()

    def server_now():
        return int(time.time()*1000) + store.meta("clock_offset_ms", 0)

    @asynccontextmanager
    async def lifespan(app):
        task = None
        lock = ProcessLock(state/"worker.lock")
        try:
            if use_snapshot:
                from .continuous import initialize_snapshot
                await asyncio.to_thread(initialize_snapshot,store)
            if live:
                task = asyncio.create_task(Worker(store).run())
            else:
                store.set_meta("worker", dict(mode="offline", feed_status="historical_snapshot"))
            yield
        finally:
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            lock.close()

    app = FastAPI(title=SIGNAL_NAME+" signal service", version=VERSION, lifespan=lifespan)
    app.state.store = store

    @app.middleware("http")
    async def browser_identity(request: Request, call_next):
        token = request.cookies.get("gfi_session", "")
        uid, _, sig = token.partition(".")
        valid = len(uid) == 32 and hmac.compare_digest(sig, signature(uid))
        if not valid:
            uid = secrets.token_hex(16)
        request.state.user_id = uid
        response = await call_next(request)
        if not valid:
            response.set_cookie("gfi_session", uid+"."+signature(uid), max_age=365*86400,
                httponly=True, samesite="lax", secure=os.getenv("GFI_SECURE_COOKIE", "0") == "1")
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/api/health")
    def health():
        worker = store.meta("worker", {})
        age = server_now()-worker.get("heartbeat_ms", 0)
        history=store.meta("history_status",{})
        asof=store.meta("continuous_asof_ms")
        return dict(signal_name=SIGNAL_NAME,model_id=MODEL_ID,profile_id=PROFILE_ID,version=VERSION,spec_hash=SPEC_HASH, mode="live" if live else "offline",
                    history=history,data_as_of_ms=asof,
                    data_current=bool(asof==server_now()//BAR*BAR and history.get("phase")=="ready"),
                    worker=worker, feed_stale=bool(live and age > 30_000),
                    server_time_ms=server_now(), last_missed_interval=store.meta("last_missed_interval"),
                    marks_quality=store.meta("marks_quality", {}),
                    latest_event_id=store.latest_event_id())

    @app.get("/api/model")
    def model():
        return dict(SPEC, spec_hash=SPEC_HASH, forecast="frozen historical conditional mean, not guaranteed future price",
                    notification_limit=5, simulated_tracking=True, broker_execution=False)

    @app.get("/api/notifications")
    def notifications(request: Request):
        items = store.notifications(request.state.user_id, server_now())
        return dict(items=items, unread_count=sum(t["unread"] for t in items),
                    server_time_ms=server_now(), latest_event_id=store.latest_event_id())

    @app.post("/api/notifications/{sid}/read")
    def read(sid: str, request: Request):
        if not store.detail(sid, server_now()):
            raise HTTPException(404, "Signal no longer in the latest five notifications")
        store.read(request.state.user_id, sid)
        return dict(ok=True)

    @app.get("/api/signals/{sid}")
    def detail(sid: str):
        t = store.detail(sid, server_now())
        if not t:
            raise HTTPException(404, "Signal no longer in the latest five notifications")
        return t

    @app.get("/api/stats")
    def stats(coin: str | None = None, chart_points: int = 1000):
        if coin is not None and coin not in COINS:
            raise HTTPException(422, "Unknown coin")
        if not 100 <= chart_points <= 20000:
            raise HTTPException(422, "chart_points must be 100..20000")
        result = store.metrics(coin)
        curve = result["equity_curve"]
        result["full_equity_points"] = len(curve)
        stride = max(1, (len(curve)+chart_points-1)//chart_points)
        sampled = curve[::stride]
        if curve and sampled[-1] != curve[-1]:
            sampled.append(curve[-1])
        result["equity_curve"] = sampled
        result["cash_available_usdt"] = store.meta("cash")
        return result

    @app.get("/api/events")
    async def events(request: Request):
        raw = request.headers.get("last-event-id") or request.query_params.get("after")
        try:
            cursor = max(0, int(raw)) if raw is not None else store.latest_event_id()
        except ValueError:
            raise HTTPException(422, "Invalid event cursor") from None

        async def stream():
            nonlocal cursor
            yield "retry: 3000\n\n"
            latest = store.latest_event_id()
            # Every reconnect refreshes the current snapshot, including after a retention gap.
            if cursor > latest:
                cursor = latest
            pending = store.events(cursor)
            if pending and pending[0]["id"] > cursor+1:
                cursor = latest  # event retention gap: snapshot is authoritative
            yield f"id: {cursor}\nevent: snapshot\ndata: {encode(dict(latest_event_id=latest, server_time_ms=server_now()))}\n\n"
            ticks = 0
            while not await request.is_disconnected():
                for row in store.events(cursor):
                    cursor = row["id"]
                    yield f"id: {cursor}\nevent: {row['kind']}\ndata: {row['data']}\n\n"
                if ticks % 5 == 0:
                    payload = encode(dict(quotes=store.meta("quotes", {}), server_time_ms=server_now()))
                    yield f"event: quotes\ndata: {payload}\n\n"
                if ticks % 15 == 0:
                    yield ": keepalive\n\n"
                ticks += 1
                await asyncio.sleep(1)

        return StreamingResponse(stream(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})

    app.mount("/assets", StaticFiles(directory=ROOT/"web"), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(ROOT/"web"/"index.html")

    return app
