"""Regression tests for the unified live flow; models are stubbed explicitly here."""
import asyncio
import base64
import io
import os
import tempfile
from datetime import datetime, timedelta

os.environ.setdefault("MINDLOOP_DB_PATH", tempfile.mktemp(suffix=".sqlite3"))
os.environ.setdefault("LIVE_DB_PATH", tempfile.mktemp(suffix=".sqlite3"))
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

import httpx
import pytest
from PIL import Image
from live_audio import Segmenter
from live_models import Decision
from live_store import Store, FocusSession, now
import live_app as live


def plan(store):
    store.apply(Decision(tasks=[{"title":"写报告", "steps":[{"title":"打开电脑"},{"title":"打开报告文档"},{"title":"写两分钟"}]}]), store.context(), "speech", now())
    return store.data["tasks"][-1]


def test_vad_sentence_continues_and_cap():
    segmenter = Segmenter()
    segmenter.voiced = lambda frame: frame[0] == 1
    voice = b"\x01\0" * 320
    silence = b"\0\0" * 320
    assert not segmenter.feed(silence * 100)
    parts = segmenter.feed(voice * 20 + silence * 30 + voice * 20 + silence * 30)
    assert len(parts) == 2
    assert all(p["reason"] == "silence" for p in parts)
    parts = segmenter.feed(voice * 1510)
    assert len(parts) == 1 and parts[0]["duration_ms"] == 30000
    assert segmenter.finish() is not None


def test_arbitrary_steps_revision_and_persistence(tmp_path):
    path=tmp_path/"state.db"; store=Store(path); task=plan(store)
    ctx=store.context(); steps=task["steps"]
    # A later explicit correction must win even if its value was already false.
    store.set_steps(task["id"], [{"step_id":steps[0]["id"],"done":False}], "app")
    d=Decision(completed=[{"step_id":s["id"],"confidence":.99,"evidence":"测试可见证据"} for s in steps[:2]])
    changed=store.apply(d,ctx,"vision",now())
    assert changed == [steps[1]["id"]]
    store.set_steps(task["id"],[{"step_id":steps[2]["id"],"done":True}],"app")
    store.remember("event","fp",{"changed":changed})
    other=Store(path)
    assert [s["done"] for s in other.task(task["id"])["steps"]] == [False,True,True]
    assert other.receipt("event","fp") == {"changed":changed}
    with pytest.raises(ValueError): other.receipt("event","different")


def test_focus_and_latest_return(tmp_path):
    f=FocusSession(); t=datetime.fromisoformat(now())
    away=Decision(away=True,behavior="away")
    assert f.observe(away,t.isoformat()) is None
    assert f.observe(away,(t+timedelta(seconds=5)).isoformat())
    assert f.observe(away,(t+timedelta(seconds=10)).isoformat()) is None
    f.observe(Decision(away=False), (t+timedelta(seconds=15)).isoformat())
    store=Store(tmp_path/"state.db")
    for i in range(2): store.drift("测试",now(),f.id)
    store.refocus(); first=store.data["drifts"][-1]["returned_at"]; store.refocus()
    assert store.data["drifts"][0]["returned_at"] is None
    assert store.data["drifts"][-1]["returned_at"] == first


def test_missing_frame_not_away_and_three_behaviors():
    f=FocusSession(); t=datetime.fromisoformat(now())
    assert f.observe(Decision(away=True),t.isoformat()) is None
    assert f.observe(Decision(away=True),(t+timedelta(seconds=20)).isoformat()) is None
    results=[]
    for i,behavior in enumerate(["phone","phone","none","phone","fidget"]):
        results.append(f.observe(Decision(away=False,behavior=behavior),(t+timedelta(seconds=25+i*5)).isoformat()))
    assert not any(results[:-1]) and results[-1]


def test_vision_cannot_create_tasks_or_refocus(tmp_path):
    s=Store(tmp_path/"state.db");s.drift("测试",now(),"s")
    s.apply(Decision(tasks=[{"title":"新任务","steps":[{"title":"动作一"}]}],returned=True),s.context(),"vision",now())
    assert not s.data["tasks"] and not s.data["drifts"][0]["returned_at"]


@pytest.fixture
def api_store(tmp_path,monkeypatch):
    value=Store(tmp_path/"api.db")
    monkeypatch.setattr(live,"store",value)
    monkeypatch.setattr(live,"camera",None)
    monkeypatch.setattr(live,"frames",[])
    monkeypatch.setattr(live,"speech_lock",asyncio.Lock())
    monkeypatch.setattr(live,"vision_lock",asyncio.Lock())
    return value


@pytest.mark.asyncio
async def test_api_duplicate_and_model_failure(api_store,monkeypatch):
    calls=[]
    async def decide(*args,**kwargs):
        calls.append(1)
        return Decision(items=[{"kind":"reminder","title":"喝水","recurrence":"daily"}]),12
    monkeypatch.setattr(live.cloud,"decide",decide)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=live.app),base_url="http://test") as c:
        body={"event_id":"one","text":"每天提醒我喝水"}
        a=await c.post('/api/live/text',json=body);b=await c.post('/api/live/text',json=body)
        assert a.status_code==b.status_code==200 and a.json()==b.json() and len(calls)==1
        state=(await c.get('/api/live/state')).json()
        assert len(state['clarifications'])==1 and state['events'][0]['time'] is None
        assert (await c.post('/api/live/text',json={**body,'text':'不同内容'})).status_code==409
        assert (await c.post('/api/live/items',json={'title':'错误','kind':'bad'})).status_code==422
        async def fail(*args,**kwargs): raise RuntimeError('供应商失败')
        monkeypatch.setattr(live.cloud,'decide',fail)
        assert (await c.post('/api/live/text',json={'event_id':'two','text':'新的任务'})).status_code==502
        assert len(api_store.data['events'])==1


@pytest.mark.asyncio
async def test_closed_camera_late_result_ignored(api_store,monkeypatch):
    task=plan(api_store); started=asyncio.Event(); release=asyncio.Event()
    async def decide(*args,**kwargs):
        started.set(); await release.wait()
        return Decision(completed=[{'step_id':task['steps'][0]['id'],'confidence':1,'evidence':'测试'}]),1
    monkeypatch.setattr(live.cloud,'decide',decide)
    b=io.BytesIO();Image.new('RGB',(10,10)).save(b,format='JPEG')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=live.app),base_url='http://test') as c:
        session=(await c.post('/api/live/camera/start')).json()['session_id']
        pending=asyncio.create_task(c.post('/api/live/image',json={'event_id':'frame','session_id':session,'captured_at':now(),'image':'data:image/jpeg;base64,'+base64.b64encode(b.getvalue()).decode()}))
        await started.wait()
        await c.post('/api/live/camera/stop',json={'session_id':session});release.set()
        assert (await pending).status_code==409
        assert not task['steps'][0]['done']


@pytest.mark.asyncio
async def test_api_out_of_order_steps_and_origin(api_store):
    task=plan(api_store)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=live.app),base_url='http://test') as c:
        body={'event_id':'steps','updates':[{'step_id':s['id'],'done':True} for s in reversed(task['steps'])]}
        assert (await c.patch('/api/live/tasks/'+task['id']+'/steps',json=body)).status_code==200
        assert all(s['done'] for s in task['steps'])
        assert (await c.post('/api/live/refocus',headers={'origin':'http://foreign.example'})).status_code==403


def test_reminder_schedule_and_next_day_return(tmp_path):
    s=Store(tmp_path/'s.db')
    item=s.add_item({'title':'喝水','kind':'reminder','date':'2026-09-23','time':'14:00','recurrence':'daily'})
    s.due_reminders('2026-09-24T14:01:00+08:00');s.due_reminders('2026-09-24T14:02:00+08:00')
    assert len(s.data['commands'])==1
    s.due_reminders('2026-09-25T14:00:00+08:00')
    assert len(s.data['commands'])==2 and s.data['commands'][0]['light']=='breathing'
    s.drift('测试','2026-09-23T23:59:59+08:00','s')
    s.data['drifts'][0]['returned_at']='2026-09-24T00:00:01+08:00'
    snap=s.snapshot()
    assert snap['focus']['2026-09-23']=={'total':1,'returned':0}
    assert snap['focus']['2026-09-24']=={'total':0,'returned':1}


@pytest.mark.asyncio
async def test_hardware_claim_requires_capability_and_ack(api_store,monkeypatch):
    monkeypatch.setattr(live,'device',{'last_seen':0,'device_id':None,'capabilities':{}})
    api_store.drift('测试',now(),'session')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=live.app),base_url='http://test') as c:
        await c.post('/api/live/device/heartbeat',json={'device_id':'test','capabilities':{'haptic':True}})
        assert (await c.post('/api/live/device/next',json={'device_id':'test'})).json()['command'] is None
        await c.post('/api/live/device/heartbeat',json={'device_id':'test','capabilities':{'haptic_pattern':True}})
        command=(await c.post('/api/live/device/next',json={'device_id':'test'})).json()['command']
        assert not command['device_executed']
        assert (await c.post('/api/live/device/next',json={'device_id':'test'})).json()['command'] is None
        r=await c.post('/api/live/device/commands/'+command['id']+'/ack',json={'device_id':'test','executed':True})
        assert r.status_code==200 and api_store.data['commands'][0]['device_executed']


def test_single_static_image_cannot_complete_two_minutes(tmp_path):
    store=Store(tmp_path/'s.db');task=plan(store);s=task['steps'][2]
    completion={'step_id':s['id'],'confidence':.99,'evidence':'文档里有文字'}
    d=Decision(completed=[completion])
    assert not store.apply(d,store.context(),'vision',now())
    assert not s['done']
    t=datetime.fromisoformat(now())
    active=Decision(completed=[completion],activities=[{**completion,'evidence':'当前帧可见实际编辑动作'}])
    for i in range(25): store.apply(active,store.context(),'vision',(t+timedelta(seconds=i*5)).isoformat())
    assert s['done']


def test_recognized_history_does_not_duplicate_saved_reminder(tmp_path):
    s=Store(tmp_path/'s.db')
    original=s.add_item({'title':'喝水','kind':'reminder','date':'2026-09-24','time':'14:00','recurrence':'daily'})
    duplicate=s.add_item({'title':'喝水','kind':'reminder','date':None,'time':None,'recurrence':'daily'})
    assert original['id']==duplicate['id'] and len(s.data['events'])==1
    assert duplicate['time']=='14:00'
