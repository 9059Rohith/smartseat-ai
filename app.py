"""Same-origin, local SmartSeat web application."""
import argparse
import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from store import Conflict, Missing, Store
from vision import Cameras
from operational import operations_status
from media_analysis import MAX_REQUEST, MediaJobs, decode_frame

ROOT = Path(__file__).resolve().parent
COOKIE = "smartseat_session"
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Size = Annotated[int, Field(ge=1, le=60)]
Point = tuple[Annotated[float, Field(ge=0, le=1)], Annotated[float, Field(ge=0, le=1)]]
Zone = Annotated[list[Point], Field(max_length=32)]


def validate_zone(points):
    if not points:
        return points
    if len(points) < 3 or len(set(points)) != len(points):
        raise ValueError("Draw at least three distinct corners.")
    def side(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    edges = list(zip(points, points[1:] + points[:1]))
    for i, (a, b) in enumerate(edges):
        for j, (c, d) in enumerate(edges):
            if j <= i + 1 or (i == 0 and j == len(edges) - 1):
                continue
            if (max(min(a[0], b[0]), min(c[0], d[0])) <= min(max(a[0], b[0]), max(c[0], d[0]))
                    and max(min(a[1], b[1]), min(c[1], d[1])) <= min(max(a[1], b[1]), max(c[1], d[1]))
                    and side(a, b, c) * side(a, b, d) <= 0 and side(c, d, a) * side(c, d, b) <= 0):
                raise ValueError("The outline crosses itself.")
    area = abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in edges)) / 2
    if area < .0001:
        raise ValueError("Draw a larger outline.")
    return points


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Input):
    name: Name
    password: Annotated[str, Field(min_length=1, max_length=160)]


class Staff(Login):
    password: Annotated[str, Field(min_length=12, max_length=160)]
    role: Literal["manager", "staff"] = "staff"


class TableInput(Input):
    name: Name
    capacity: Size
    camera: int | None = None
    zone: Zone = Field(default_factory=list)
    vision: bool = True

    _zone = field_validator("zone")(validate_zone)


class CameraInput(Input):
    name: Name
    kind: Literal["webcam", "rtsp"]
    source: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1024)]

    @field_validator("source")
    @classmethod
    def check_source(cls, source, info):
        kind = info.data.get("kind")
        if kind == "webcam" and (not source.isascii() or not source.isdecimal() or int(source) > 16):
            raise ValueError("Use a webcam index from 0 to 16.")
        if kind == "rtsp":
            parsed = urlsplit(source)
            if parsed.scheme not in ("rtsp", "rtsps") or not parsed.hostname or parsed.fragment:
                raise ValueError("Enter a valid RTSP camera URL.")
        return source


class Entrance(Input):
    zone: Zone

    _zone = field_validator("zone")(validate_zone)


class Party(Input):
    name: Name
    size: Size


class Assignment(Input):
    table: int
    action: Literal["call", "seat"]


class Reservation(Party):
    table: int
    start: datetime
    end: datetime

    @field_validator("start", "end")
    @classmethod
    def require_zone(cls, value):
        if value.utcoffset() is None:
            raise ValueError("Include a timezone offset.")
        return value


def seed_demo(store):
    if store.snapshot()["cameras"]:
        return
    source = ROOT / "demo/restaurant.mp4"
    data = json.loads((ROOT / "demo/dineassist-zones.json").read_text(encoding="utf-8"))
    camera = store.add_camera("Sample dining room", "sample", str(source))
    size = data["frame_size"]
    width, height = (size["width"], size["height"]) if isinstance(size, dict) else size
    for index, table in enumerate(data["tables"], 1):
        points = table.get("polygon") or table.get("points")
        store.add_table(f"T{index:02d}", 4, camera, [[x / width, y / height] for x, y in points])
    store.add_camera("Laptop camera", "webcam", "0")


def create_app(database, *, demo=False, greeting_seconds=None, webcam=False,public_hosts=None,public_origins=None,operations_dir=None):
    store = Store(database, greet=greeting_seconds or (5 if demo else 300))
    cameras = Cameras(store)
    media = MediaJobs(cameras.get_detector)
    attempts = {}
    if demo:
        seed_demo(store)
    webcam_id = None
    if webcam and not demo:
        existing = next((cam for cam in store.snapshot()["cameras"] if cam["kind"] == "webcam"), None)
        webcam_id = existing["id"] if existing else store.add_camera("Laptop camera", "webcam", "0")

    @asynccontextmanager
    async def lifespan(app):
        async def timer():
            while True:
                await asyncio.to_thread(store.tick)
                await asyncio.sleep(1)
        task = asyncio.create_task(timer())
        if webcam_id is not None:
            cameras.start(webcam_id)
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            await asyncio.to_thread(cameras.shutdown)
            media.close()

    app = FastAPI(title="SmartSeat AI", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    hosts=public_hosts if public_hosts is not None else [value for value in os.environ.get('SMARTSEAT_PUBLIC_HOSTS','').split(',') if value]
    origins=public_origins if public_origins is not None else [value for value in os.environ.get('SMARTSEAT_PUBLIC_ORIGINS','').split(',') if value]
    if any('*' in host or '/' in host for host in hosts):raise ValueError('Public hosts must be exact hostnames.')
    if any(urlsplit(origin).scheme!='https' or urlsplit(origin).path not in ('','/') for origin in origins):
        raise ValueError('Public origins must be exact HTTPS origins.')
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost",*hosts])
    app.state.store = store
    app.state.cameras = cameras
    app.state.media = media

    @app.middleware("http")
    async def protect(request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and origin not in origins and urlsplit(origin).netloc.lower() != request.headers.get("host", "").lower():
                return JSONResponse({"detail": "Open SmartSeat directly to perform that action."}, 403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; "
            "media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(Conflict)
    async def conflict(_, exc):
        return JSONResponse({"detail": str(exc)}, 409)

    @app.exception_handler(Missing)
    async def missing(_, exc):
        return JSONResponse({"detail": str(exc)}, 404)

    @app.exception_handler(sqlite3.IntegrityError)
    async def database_conflict(_, exc):
        return JSONResponse({"detail": "That name is already used or the selected record is unavailable."}, 409)

    def user(request: Request):
        session = store.session(request.cookies.get(COOKIE))
        if not session:
            raise HTTPException(401, "Sign in to SmartSeat.")
        return session

    def manager(session=Depends(user)):
        if session["role"] != "manager":
            raise HTTPException(403, "A manager account is required.")
        return session

    @app.get("/api/health")
    def health():
        with store.db() as db: camera_ids=[row[0] for row in db.execute('SELECT id FROM cameras')]
        statuses=[cameras.view(camera_id).status for camera_id in camera_ids]
        capture={'configured':len(statuses),'live':statuses.count('live'),'blocked':statuses.count('obscured'),
                 'stopped':statuses.count('idle')+statuses.count('complete'),
                 'unavailable':sum(status not in ('live','obscured','idle','complete') for status in statuses)}
        return {"ok": True, "app": "smartseat", "demo": demo,
                "vision_model": cameras.model.model_path.name if cameras.model else None,'capture':capture}

    @app.get('/api/operations')
    def operation_status(_=Depends(manager)):
        return operations_status(store,operations_dir or ROOT/'local')

    @app.post('/api/media/analyze',status_code=202)
    async def media_analyze(request: Request,session=Depends(user)):
        if request.headers.get('content-type','').split(';')[0]!='application/json':
            raise HTTPException(415,'Send a JPEG frame as JSON.')
        data=bytearray()
        async for chunk in request.stream():
            if len(data)+len(chunk)>MAX_REQUEST:raise HTTPException(413,'This frame is too large.')
            data.extend(chunk)
        try:
            body=json.loads(data)
            if not isinstance(body,dict) or set(body)-{'image','broad','frame_time'}:raise ValueError()
            broad=body.get('broad',False);at=body.get('frame_time',0)
            if type(broad) is not bool or type(at) not in (int,float) or not 0<=at<=86400:raise ValueError()
        except (ValueError,TypeError):raise HTTPException(422,'Invalid media analysis request.') from None
        frame=await asyncio.to_thread(decode_frame,body.get('image'))
        return media.submit(session['name'],frame,broad=broad,frame_time=at)

    @app.get('/api/media/jobs/{job}')
    def media_job(job: str,session=Depends(user)):
        return media.get(job,session['name'])

    @app.delete('/api/media/jobs/{job}')
    def media_delete(job: str,session=Depends(user)):
        media.delete(job,session['name'])
        return {'ok':True}

    @app.post("/api/login")
    async def login(body: Login, request: Request, response: Response):
        key = request.client.host if request.client else "local"
        now = time.monotonic()
        history = [at for at in attempts.get(key, []) if now - at < 90]
        if len(history) >= 8:
            raise HTTPException(429, "Too many attempts. Try again in a minute.")
        attempts[key] = history + [now]
        token = await asyncio.to_thread(store.login, body.name, body.password)
        if not token:
            raise HTTPException(401, "Username or password is incorrect.")
        attempts.pop(key, None)
        response.set_cookie(COOKIE, token, max_age=43200, httponly=True, samesite="strict",
                            secure=request.url.scheme == "https")
        return store.session(token)

    @app.get("/api/me")
    def me(request: Request):
        return store.session(request.cookies.get(COOKIE))

    @app.post("/api/logout")
    def logout(request: Request, response: Response, _=Depends(user)):
        store.logout(request.cookies[COOKIE])
        response.delete_cookie(COOKIE)
        return {"ok": True}

    @app.post("/api/users", status_code=201)
    def add_user(body: Staff, _=Depends(manager)):
        store.add_user(body.name, body.password, body.role)
        return {"ok": True}

    def snapshot():
        data = store.snapshot()
        data["demo"] = demo
        for cam in data["cameras"]:
            view = cameras.view(cam["id"])
            cam["entrance"] = json.loads(cam["entrance"])
            cam.update(status=view.status, message=view.message, frames=view.frames, people=view.people,
                       image=view.jpeg is not None, frame_at=view.at,
                       detected_tables=list(view.furniture), chairs=view.chairs, inference_ms=view.inference_ms,
                       table_scan=view.table_scan)
        return data

    @app.get("/api/state")
    def state(_=Depends(user)):
        return snapshot()

    @app.get("/api/live")
    async def live(request: Request, _=Depends(user)):
        async def feed():
            while not await request.is_disconnected():
                if not await asyncio.to_thread(store.session, request.cookies.get(COOKIE)):
                    break
                data = await asyncio.to_thread(snapshot)
                yield f"data: {json.dumps(data, separators=(',', ':'))}\n\n"
                await asyncio.sleep(1)
        return StreamingResponse(feed(), media_type="text/event-stream",
                                 headers={"X-Accel-Buffering": "no"})

    @app.post("/api/cameras", status_code=201)
    def add_camera(body: CameraInput, _=Depends(manager)):
        return {"id": store.add_camera(body.name, body.kind, body.source)}

    @app.post("/api/cameras/{camera}/{action}")
    def camera_action(camera: int, action: Literal["start", "stop"], _=Depends(manager)):
        if action == "start":
            return {"status": cameras.start(camera)}
        cameras.stop(camera)
        return {"status": "stopping"}

    @app.put("/api/cameras/{camera}/entrance")
    def entrance(camera: int, body: Entrance, _=Depends(manager)):
        store.set_entrance(camera, body.zone)
        return {"ok": True}

    @app.get("/api/cameras/{camera}/frame")
    def frame(camera: int, raw: bool = False, _=Depends(user)):
        current = cameras.view(camera)
        content = current.raw if raw else current.jpeg
        if not content:
            raise HTTPException(404, "No camera frame yet.")
        return Response(content, media_type="image/jpeg")

    @app.post("/api/tables", status_code=201)
    def add_table(body: TableInput, _=Depends(manager)):
        if bool(body.zone) != (body.camera is not None):
            raise HTTPException(422, "Select a camera and draw its zone, or leave both empty.")
        if body.camera is not None:
            store.camera(body.camera)
        table = store.add_table(body.name, body.capacity, body.camera, body.zone, vision=body.vision)
        return {"id": table}

    @app.put("/api/tables/{table}")
    def edit_table(table: int, body: TableInput, _=Depends(manager)):
        if bool(body.zone) != (body.camera is not None):
            raise HTTPException(422, "Select a camera and draw its zone, or leave both empty.")
        if body.camera is not None:
            store.camera(body.camera)
        store.edit_table(table, body.name, body.capacity, body.camera, body.zone, body.vision)
        return {"ok": True}

    @app.post("/api/tables/{table}/{action}")
    def table_action(table: int, action: Literal["occupy", "greet", "depart", "clean"], _=Depends(user)):
        store.table_action(table, action)
        return {"ok": True}

    @app.post("/api/queue", status_code=201)
    def add_party(body: Party, _=Depends(user)):
        return {"id": store.add_party(body.name, body.size)}

    @app.post("/api/queue/{party}/assign")
    def assign(party: int, body: Assignment, _=Depends(user)):
        store.seat(party, body.table, call=body.action == "call")
        return {"ok": True}

    @app.delete("/api/queue/{party}")
    def cancel_party(party: int, _=Depends(user)):
        store.cancel_party(party)
        return {"ok": True}

    @app.post("/api/reservations", status_code=201)
    def reserve(body: Reservation, _=Depends(user)):
        return {"id": store.reserve(body.name, body.size, body.table, body.start.timestamp(), body.end.timestamp())}

    @app.post("/api/reservations/{reservation}/{action}")
    def reservation_action(reservation: int, action: Literal["seat", "cancel"], _=Depends(user)):
        store.reservation_action(reservation, action)
        return {"ok": True}

    @app.get("/api/analytics")
    def analytics(start: float, end: float, tz: int = 0, _=Depends(user)):
        if not (0 <= start < end <= time.time() + 60 and end - start <= 32 * 86400):
            raise HTTPException(422, "Choose an elapsed date range of up to 31 days.")
        if not -840<=tz<=840:raise HTTPException(422,'Invalid timezone offset.')
        return store.report(start, end, timezone_offset=tz)

    web = ROOT / "web/dist"
    if (web / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=web / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        if not (web / "index.html").is_file():
            return Response("Build the browser app first with npm ci and npm run build in web/.", 503)
        return FileResponse(web / "index.html")

    @app.get("/favicon.svg", include_in_schema=False)
    def favicon():
        return FileResponse(ROOT / "web/public/favicon.svg", media_type="image/svg+xml")

    return app


def main():
    import uvicorn
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--webcam", action="store_true", help="Start the real laptop camera in a live workspace.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--greeting-seconds", type=int)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "local")
    args = parser.parse_args()
    if args.greeting_seconds is not None and not 1 <= args.greeting_seconds <= 3600:
        parser.error("The greeting deadline must be between 1 and 3600 seconds.")
    database = args.data_dir / ("demo.sqlite3" if args.demo else "smartseat.sqlite3")
    app = create_app(database, demo=args.demo, greeting_seconds=args.greeting_seconds, webcam=args.webcam)
    store = app.state.store
    if not store.users_exist():
        username = "demo" if args.demo else "manager"
        password = "smartseat-demo" if args.demo else os.environ.get("SMARTSEAT_PASSWORD") or secrets.token_urlsafe(15)
        if len(password) < 12:
            parser.error("SMARTSEAT_PASSWORD must contain at least 12 characters.")
        store.add_user(username, password, "manager")
        print(f"First sign-in — username: {username}   password: {password}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()

