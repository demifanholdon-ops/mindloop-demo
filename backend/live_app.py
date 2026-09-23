"""Connected demo entry. Uses the reviewed GitHub app plus a unified live API."""
import asyncio
import base64
import hashlib
import io
import json
import os
import time
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, RedirectResponse
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel, Field

from main import app
from live_audio import Segmenter
from live_models import Cloud, Item
from local_asr import LocalASR
from live_store import Store, FocusSession, now, uid, check_date, check_clock, TZ

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.getenv("LIVE_DB_PATH", str(Path(__file__).resolve().parents[1] / "data/live.sqlite3")))
DATA.parent.mkdir(parents=True, exist_ok=True)
store = Store(DATA)
cloud = Cloud()
local_asr = LocalASR()
asr_provider = os.getenv("ASR_PROVIDER", "local")
speech_lock = asyncio.Lock()
vision_lock = asyncio.Lock()
camera = None
frames = []
device = {"last_seen": 0, "device_id": None, "capabilities": {}}


@asynccontextmanager
async def live_lifespan(app):
    async def warmup():
        if asr_provider == 'local':
            try: await local_asr.warmup()
            except Exception: pass  # UI reports readiness; first speech returns a recoverable error.
    async def clock_loop():
        global camera
        while True:
            store.due_reminders()
            if camera and time.monotonic()-camera.last_seen > 90:
                await stop_camera({'session_id':camera.id})
            await asyncio.sleep(1)
    jobs = [asyncio.create_task(warmup()), asyncio.create_task(clock_loop())]
    yield
    for job in jobs: job.cancel()
    await asyncio.gather(*jobs, return_exceptions=True)


app.router.lifespan_context = live_lifespan
app.mount("/app", StaticFiles(directory=Path(__file__).resolve().parents[1] / "frontend-pink", html=True), name="pink-live")


@app.get('/phone-demo.html', include_in_schema=False)
async def phone_demo():
    return RedirectResponse('/app/index.html?live=1')


@app.middleware("http")
async def local_origin(request: Request, call_next):
    if request.url.path.startswith("/api/live"):
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail": "请从当前服务的 App 页面操作"}, status_code=403)
    response=await call_next(request)
    if request.url.path.startswith('/app/'):
        response.headers['Cache-Control']='no-cache'
    return response


def fingerprint(body):
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def stamp(value):
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None: raise ValueError()
        if abs((datetime.fromisoformat(now())-dt).total_seconds()) > 180: raise ValueError()
        return dt.astimezone(TZ).isoformat()
    except (TypeError, ValueError):
        raise HTTPException(422, "采集时间无效或数据超过3分钟")


class TextInput(BaseModel):
    event_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=6000)
    captured_at: str | None = None


class ImageInput(BaseModel):
    event_id: str = Field(min_length=1, max_length=100)
    session_id: str
    captured_at: str
    image: str = Field(max_length=2000000)


def cached(event_id, fp):
    try: return store.receipt(event_id, fp)
    except ValueError as exc: raise HTTPException(409, str(exc))


@app.get("/api/live/state")
async def state():
    return {**store.snapshot(), "models": {**cloud.status(), "asr_provider": asr_provider, "local_asr_ready": local_asr.model is not None}, "camera_session": camera.id if camera else None,
            "hardware": {"connected": time.monotonic()-device['last_seen'] < 15,
                         "haptic": device['capabilities'].get('haptic_pattern',False),
                         "device_id": device['device_id']}}


def applied_reply(decision, changed, source, new_items=None):
    parts=[]
    if source=='speech' and decision.tasks:
        parts.append(f"已拆成 {sum(len(t.steps) for t in decision.tasks)} 个小步骤，可以在 App 逐项查看。")
    if source=='speech' and decision.items:
        items=new_items if new_items is not None else [i.model_dump() for i in decision.items]
        pending=sum(not i.get('date') or (i['kind']=='reminder' and not i.get('time')) for i in items)
        parts.append((f"已记下 {len(items)} 件事。"+(f"其中 {pending} 件请补充日期或提醒时间。" if pending else '')) if items else '已有事项已保留，没有重复保存。')
    if changed: parts.append(f"已记录 {len(changed)} 个小步骤完成。")
    if source=='speech' and decision.returned:
        parts.append('已处理回归确认，只关联最近一次偏离。')
    if not parts and (source=='vision' or decision.completed):
        return '观察已记录，暂未新增可确认的步骤。'
    return ''.join(parts) or decision.reply


async def interpret(event_id, text, captured_at, extra=None):
    arrival = time.perf_counter()
    fp = fingerprint({"text": text})
    async with speech_lock:
        prior = cached(event_id, fp)
        if prior: return prior
        queue_ms = round((time.perf_counter()-arrival)*1000)
        context = store.context()
        decision, model_ms = await cloud.decide(context, text=text)
        previous_items={e['id'] for e in store.data['events']}
        changed = store.apply(decision, context, "speech", captured_at, text=text)
        new_items=[e for e in store.data['events'] if e['id'] not in previous_items]
        timings = {**(extra or {}), "queue_ms": queue_ms, "model_ms": model_ms, "semantic_ms": round((time.perf_counter()-arrival)*1000)}
        result = {"event_id": event_id, "text": text, "reply": applied_reply(decision,changed,'speech',new_items), "changed_steps": changed, "timings": timings}
        store.activity({"event_id": event_id, "source": "speech", **result})
        store.remember(event_id, fp, result)
        return result


@app.post("/api/live/text")
async def text_input(body: TextInput):
    try:
        return await interpret(body.event_id, body.text, stamp(body.captured_at) if body.captured_at else now())
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(502, str(exc))


@app.post("/api/live/camera/start")
async def start_camera():
    global camera
    if camera: raise HTTPException(409, "已有摄像头会话，请先关闭再切换")
    camera = FocusSession(); frames.clear()
    return {"session_id": camera.id}


@app.post("/api/live/camera/stop")
async def stop_camera(body: dict):
    global camera
    if camera and body.get("session_id") == camera.id:
        for cmd in store.data["commands"]:
            if cmd.get("session_id") == camera.id and cmd["status"] == "queued": cmd["status"] = "cancelled"
        camera = None; frames.clear(); store.save()
    return {"ok": True}


@app.post("/api/live/image")
async def image_input(body: ImageInput):
    arrival = time.perf_counter()
    captured_at = stamp(body.captured_at)
    if not camera or body.session_id != camera.id: raise HTTPException(409, "摄像头会话已结束")
    camera.last_seen=time.monotonic()
    fp = fingerprint(body.model_dump())
    prior = cached(body.event_id, fp)
    if prior: return prior
    if vision_lock.locked(): raise HTTPException(429, "上一组画面仍在识别，本次保留最新画面稍后再试")
    try:
        header, encoded = body.image.split(",", 1)
        if header not in {"data:image/jpeg;base64", "data:image/png;base64"}: raise ValueError()
        image = Image.open(io.BytesIO(base64.b64decode(encoded, validate=True)))
        if image.width * image.height > 2000000: raise ValueError()
        image.verify()
    except Exception:
        raise HTTPException(422, "图片无效，请发送不超过200万像素的JPEG/PNG")
    async with vision_lock:
        session = camera
        if frames and captured_at <= frames[-1]["captured_at"]: raise HTTPException(409, "画面乱序")
        context = store.context()
        recent = (frames + [{"captured_at": captured_at, "image": body.image}])[-3:]
        try: decision, model_ms = await cloud.decide(context, images=recent)
        except RuntimeError as exc: raise HTTPException(502, str(exc))
        if camera is not session: raise HTTPException(409, "识别期间摄像头已关闭，结果未应用")
        changed = store.apply(decision, context, "vision", captured_at)
        reason = session.observe(decision, captured_at)
        if reason: store.drift(reason, captured_at, session.id)
        frames[:] = recent
        result = {"event_id": body.event_id, "reply": applied_reply(decision,changed,'vision'), "observation": decision.observation,
                  "changed_steps": changed, "drift": bool(reason),
                  "timings": {"model_ms": model_ms, "server_ms": round((time.perf_counter()-arrival)*1000)}}
        store.activity({"source": "vision", **result})
        store.remember(body.event_id, fp, result)
        return result


class StepUpdate(BaseModel):
    step_id: str
    done: bool


class StepsInput(BaseModel):
    event_id: str
    updates: list[StepUpdate] = Field(min_length=1, max_length=20)


@app.patch("/api/live/tasks/{task_id}/steps")
async def update_steps(task_id: str, body: StepsInput):
    fp = fingerprint({"task_id": task_id, **body.model_dump()})
    prior = cached(body.event_id, fp)
    if prior: return prior
    try: changed = store.set_steps(task_id, [u.model_dump() for u in body.updates], "app")
    except ValueError as exc: raise HTTPException(422, str(exc))
    result = {"changed_steps": changed}
    store.remember(body.event_id, fp, result)
    return result


@app.post("/api/live/refocus")
async def refocus():
    store.refocus(); store.save()
    return {"ok": True}


@app.post("/api/live/items")
async def add_item(body: Item):
    if not body.title.strip(): raise HTTPException(422, "请填写事项")
    try: item = store.add_item(body.model_dump())
    except ValueError as exc: raise HTTPException(422, str(exc))
    store.save(); return item


class ItemEdit(BaseModel):
    date: str | None = None
    time: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=160)
    done: bool | None = None
    cancelled: bool | None = None


@app.patch("/api/live/items/{item_id}")
async def edit_item(item_id: str, patch: ItemEdit):
    body = patch.model_dump(exclude_unset=True)
    item = next((e for e in store.data["events"] if e["id"] == item_id), None)
    if not item: raise HTTPException(404, "事项不存在")
    try:
        if "date" in body: check_date(body["date"])
        if "time" in body: check_clock(body["time"])
    except ValueError: raise HTTPException(422, "日期或时间格式不正确")
    for key in ("date", "time", "done", "cancelled", "title"):
        if key in body: item[key] = body[key]
    for command in store.data['commands']:
        if command.get('item_id') == item_id and command['status'] == 'queued': command['status'] = 'cancelled'
    item["needs_time"] = not item.get("date") or (item["kind"] == "reminder" and not item.get("time"))
    store.save(); return item


class Heartbeat(BaseModel):
    device_id: str = Field(min_length=1,max_length=80)
    capabilities: dict[str,bool] = Field(default_factory=dict)


@app.post('/api/live/device/heartbeat')
async def heartbeat(body: Heartbeat):
    if time.monotonic()-device['last_seen'] < 15 and device['device_id'] != body.device_id:
        raise HTTPException(409,'已有硬件网关连接')
    device.update(last_seen=time.monotonic(), device_id=body.device_id, capabilities=body.capabilities)
    return {'ok':True}


@app.post('/api/live/device/next')
async def next_command(body: dict):
    if body.get('device_id') != device['device_id'] or time.monotonic()-device['last_seen'] >= 15:
        raise HTTPException(409,'请先发送硬件心跳')
    for command in store.data['commands']:
        if command['status'] == 'claimed':
            if (datetime.fromisoformat(now())-datetime.fromisoformat(command['claimed_at'])).total_seconds() > 30:
                command.update(status='failed',error='设备回执超时；执行状态未知，不自动重发')
                store.save()
            else: return {'command':None}
    for command in store.data['commands']:
        if command['status'] != 'queued': continue
        if not device['capabilities'].get('haptic_pattern'): return {'command':None}
        if command['kind'] == 'reminder' and not device['capabilities'].get('breathing_light'): return {'command':None}
        command.update(status='claimed', device_id=body['device_id'], claimed_at=now())
        store.save(); return {'command':command}
    return {'command':None}


class CommandAck(BaseModel):
    device_id: str
    executed: bool
    error: str | None = Field(default=None,max_length=200)


@app.post('/api/live/device/commands/{command_id}/ack')
async def command_ack(command_id: str, body: CommandAck):
    command = next((c for c in store.data['commands'] if c['id']==command_id),None)
    if not command or command.get('device_id') != body.device_id: raise HTTPException(409,'指令不属于此设备')
    if command['status'] in {'executed','failed'}: return {'ok':True}
    if command['status'] != 'claimed': raise HTTPException(409,'指令尚未领取')
    command.update(status='executed' if body.executed else 'failed', device_executed=body.executed, error=body.error, ack_at=now())
    store.save();return {'ok':True}


@app.post("/api/live/latency")
async def latency(body: dict):
    for row in reversed(store.data["activity"]):
        if row.get("event_id") == body.get("event_id"):
            value = body.get("capture_to_ui_ms")
            if isinstance(value, (float, int)) and 0 <= value <= 300000:
                row.setdefault("timings", {})["capture_to_ui_ms"] = round(value)
                store.save()
            break
    return {"ok": True}


@app.websocket("/api/live/audio")
async def audio_socket(ws: WebSocket):
    origin = ws.headers.get("origin")
    if origin and origin != "http://" + ws.headers.get("host", ""):
        await ws.close(code=1008); return
    await ws.accept()
    segmenter = Segmenter()
    queue = asyncio.Queue(maxsize=8)
    started = time.perf_counter()

    async def worker():
        while True:
            part = await queue.get()
            try:
                if part is None: return
                event_id = uid("voice")
                await ws.send_json({"type": "processing", "event_id": event_id})
                text, asr_ms = await (local_asr.transcribe(part["wav"]) if asr_provider == "local" else cloud.transcribe(part["wav"]))
                result = await interpret(event_id, text, part["captured_at"],
                                         {"asr_ms": asr_ms, "endpoint_ms": part["endpoint_ms"], "audio_ms": part["duration_ms"]})
                result["timings"]["utterance_to_result_ms"] = round((time.perf_counter()-part["ended_at"])*1000) + part["endpoint_ms"]
                store.save()
                await ws.send_json({"type": "result", **result})
            except Exception as exc:
                message = str(exc) if isinstance(exc, (RuntimeError, ValueError, OSError)) else "语音处理失败，请检查本地模型安装后重试"
                try: await ws.send_json({"type": "error", "message": message})
                except (RuntimeError, OSError): pass
            finally: queue.task_done()

    async def submit(part):
        if part:
            part.update(captured_at=now(), ended_at=time.perf_counter())
            if queue.full():
                await ws.send_json({"type": "error", "message": "识别速度暂时跟不上，请暂停说话等待处理"})
                raise WebSocketDisconnect()
            queue.put_nowait(part)
            await ws.send_json({"type": "sentence", "queue": queue.qsize(), "duration_ms": part["duration_ms"]})

    task = asyncio.create_task(worker())
    try:
        await ws.send_json({"type": "ready", "sample_rate": 16000, "silence_ms": 600, "max_segment_ms": 30000,
                            "vad": "webrtc" if segmenter.vad else "energy"})
        while True:
            message = await ws.receive()
            if message["type"] == "websocket.disconnect": break
            if message.get("bytes") is not None:
                data = message["bytes"]
                if len(data) > 64000 or len(data) % 2: raise ValueError("音频分块应为16位PCM，每包不超过2秒")
                for part in segmenter.feed(data): await submit(part)
            elif message.get("text"):
                control = json.loads(message["text"])
                if control.get("type") == "flush":
                    await submit(segmenter.finish())
                if control.get("type") == "stop":
                    await submit(segmenter.finish())
                    await queue.join()
                    await ws.send_json({"type": "stopped"}); break
        await ws.close()
    except (WebSocketDisconnect, RuntimeError):
        pass
    except (ValueError, json.JSONDecodeError):
        await ws.close(code=1003)
    finally:
        task.cancel()
        try: await task
        except asyncio.CancelledError: pass
