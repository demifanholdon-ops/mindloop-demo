"""Current EvoMap flow, using the same state and step IDs as the App."""
import asyncio
import base64
import os
import tempfile

os.environ.setdefault('MINDLOOP_DB_PATH', tempfile.mktemp(suffix='.sqlite3'))
os.environ.setdefault('LIVE_DB_PATH', tempfile.mktemp(suffix='.sqlite3'))
os.environ['PYTHON_DOTENV_DISABLED']='1'

import httpx
import pytest
import live_app as live
from live_legacy import action_for
from live_models import Decision, NewTask
from live_store import Store, now


@pytest.fixture
def data(tmp_path,monkeypatch):
    store=Store(tmp_path/'state.db')
    monkeypatch.setattr(live,'store',store)
    monkeypatch.setattr(live,'legacy_busy',False)
    monkeypatch.setattr(live,'legacy_frame',None)
    monkeypatch.setattr(live,'legacy_recording_until',0)
    monkeypatch.setattr(live,'continuous_mode',False)
    monkeypatch.setattr(live,'speech_lock',asyncio.Lock())
    return store


def client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=live.app),base_url='http://test')


def seed(store):
    store.apply(Decision(tasks=[{'title':'写报告','steps':[{'title':'打开电脑'},{'title':'打开文档'},{'title':'写两分钟'}]}]),store.context(),'speech',now())
    return store.data['tasks'][-1]


@pytest.mark.parametrize('state,key,gesture,recording,action',[
    ('idle','k1','single',False,'record_start'),('idle','k2','long',False,'resume'),
    ('action_ready','k1','single',True,'record_stop'),('action_ready','k1','double',True,'ignore'),
    ('action_ready','k1','single',False,'done'),('action_ready','k1','double',False,'undo'),
    ('action_ready','k1','long',False,'new'),('action_ready','k2','single',False,'stuck'),
    ('action_ready','k2','double',False,'help'),('completed','k1','single',False,'new'),
    ('completed','k2','single',False,'redo'),('action_ready','k1','triple',False,'ignore')])
def test_evomap_mapping(state,key,gesture,recording,action):
    assert action_for(state,key,gesture,recording)==action


@pytest.mark.asyncio
async def test_shared_app_progress_undo_resume_and_redo(data):
    task=seed(data)
    async with client() as c:
        async def button(event,key='k1',gesture='single'):
            r=await c.post('/api/live/legacy/button',json={'event_id':event,'key':key,'gesture':gesture})
            assert r.status_code==200,r.text
            return r.json()
        await button('one')
        await button('one')  # Duplicate USB delivery cannot complete a second step.
        assert [s['done'] for s in task['steps']]==[True,False,False]
        await button('undo',gesture='double')
        assert not task['steps'][0]['done']
        await button('new',gesture='long')
        assert data.data['active_task_id'] is None and len(data.data['tasks'])==1
        await button('resume','k2','long')
        await c.patch('/api/live/tasks/'+task['id']+'/steps',json={'event_id':'app',
            'updates':[{'step_id':s['id'],'done':True} for s in task['steps']]})
        assert (await c.get('/api/live/state')).json()['session']['state']=='completed'
        await button('redo','k2')
        assert [s['done'] for s in task['steps']]==[True,True,False]


@pytest.mark.asyncio
async def test_capture_once_and_retry_without_duplicate(data,monkeypatch):
    calls=[]
    async def transcribe(wav):
        assert wav.startswith(b'RIFF');calls.append('asr');return '写报告',10
    async def create(goal,image):
        calls.append((goal,image))
        return NewTask(title='写报告',steps=[{'title':'打开文档'}]),'场景描述',20
    monkeypatch.setattr(live.local_asr,'transcribe',transcribe)
    monkeypatch.setattr(live.cloud,'task_from_capture',create)
    body={'event_id':'voice','pcm':base64.b64encode(b'\1\0'*16000).decode()}
    async with client() as c:
        assert (await c.post('/api/live/legacy/task',json=body)).status_code==200
        assert (await c.post('/api/live/legacy/task',json=body)).status_code==200
        state=(await c.get('/api/live/state')).json()
        assert state['interaction_mode']=='evomap' and state['session']['state']=='action_ready'
        assert len(calls)==2 and len(data.data['tasks'])==1
        assert (await c.post('/api/live/camera/start',json={})).status_code==409
        assert not data.data['drifts']


@pytest.mark.asyncio
async def test_invalid_capture_and_provider_failure_leave_task_unchanged(data,monkeypatch):
    task=seed(data)
    async def fail(*args): raise RuntimeError('模型暂时不可用')
    monkeypatch.setattr(live.cloud,'task_from_capture',fail)
    async with client() as c:
        r=await c.post('/api/live/legacy/task',json={'event_id':'bad','text':'写报告','image':'bad'})
        assert r.status_code==422
        r=await c.post('/api/live/legacy/task',json={'event_id':'fail','text':'写报告'})
        assert r.status_code==502 and not live.legacy_busy
        assert data.data['active_task_id']==task['id'] and len(data.data['tasks'])==1


@pytest.mark.asyncio
async def test_k2_revises_same_step_and_manual_change_wins(data,monkeypatch):
    task=seed(data);step=task['steps'][0]
    async def revise(goal,current,action):
        assert action=='help';return '打开已固定的文档快捷方式'
    monkeypatch.setattr(live.cloud,'revise_step',revise)
    async with client() as c:
        r=await c.post('/api/live/legacy/button',json={'event_id':'help','key':'k2','gesture':'double'})
        assert r.status_code==200 and task['steps'][0]['id']==step['id']
        assert step['title']=='打开已固定的文档快捷方式' and not step['done']
        async def racing(*args):
            data.set_steps(task['id'],[{'step_id':step['id'],'done':True}],'app')
            return '迟到的建议'
        monkeypatch.setattr(live.cloud,'revise_step',racing)
        r=await c.post('/api/live/legacy/button',json={'event_id':'race','key':'k2','gesture':'single'})
        assert r.status_code==409 and step['done'] and step['title']!='迟到的建议'


@pytest.mark.asyncio
async def test_usb_record_stop_create_then_complete_same_app_task(data,monkeypatch):
    import sys
    import json
    import queue
    import time
    from pathlib import Path
    from types import SimpleNamespace
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
    import evomap_gateway as gateway

    class EndSimulation(Exception): pass
    class FakeSerial:
        def __init__(self,*args,**kwargs):
            self.lines=queue.Queue();self.started=0;self.initial=False;self.completed=False
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def flush(self): pass
        def emit(self,value): self.lines.put((json.dumps(value)+'\n').encode())
        def write(self,raw):
            command=json.loads(raw)
            if command['cmd']=='hello' and not self.initial:
                self.initial=True
                self.emit({'event':'ready','microphone':True})
                self.emit({'event':'button','key':'k1','gesture':'single'})
            if command.get('action')=='start':
                self.started+=1
                self.emit({'event':'audio_start','sample_rate':16000,'channels':1,'sample_width':2})
                self.emit({'event':'audio_chunk','seq':0,'audio':base64.b64encode(b'\1\0'*16000).decode()})
                self.emit({'event':'audio_stop','dropped':0})
        def readline(self):
            if data.data['tasks']:
                task=data.data['tasks'][-1]
                if task['steps'][0]['done']: raise EndSimulation()
                if not self.completed:
                    self.completed=True
                    self.emit({'event':'button','key':'k1','gesture':'single'})
            try: return self.lines.get(timeout=.02)
            except queue.Empty: return b''
    serial=FakeSerial()
    monkeypatch.setattr(gateway.serial,'Serial',lambda *a,**k:serial)
    original=httpx.AsyncClient
    monkeypatch.setattr(gateway.httpx,'AsyncClient',lambda **kwargs:original(
        transport=httpx.ASGITransport(app=live.app),base_url='http://test'))
    monkeypatch.setattr(live,'device',{'last_seen':0,'device_id':None,'capabilities':{}})
    async def transcribe(wav): return '打开报告',1
    async def create(*args): return NewTask(title='打开报告',steps=[{'title':'打开文档'}]),'',1
    monkeypatch.setattr(live.local_asr,'transcribe',transcribe)
    monkeypatch.setattr(live.cloud,'task_from_capture',create)
    with pytest.raises(EndSimulation):
        await asyncio.wait_for(gateway.run(SimpleNamespace(api='http://test',serial='/dev/test',camera_url=None)),5)
    assert serial.started==1  # No automatic recording restart after audio_stop.
    assert len(data.data['tasks'])==1 and data.data['tasks'][0]['steps'][0]['done']
