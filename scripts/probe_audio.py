"""Real PCM -> local ASR -> real cloud -> shared state probe, using synthetic speech."""
import asyncio
import json
import time
import wave
from uuid import uuid4
from pathlib import Path
import websockets
import httpx

ROOT=Path(__file__).resolve().parents[1]


async def main():
    with wave.open(str(ROOT/'artifacts/utterance.wav')) as source:
        assert source.getframerate()==16000 and source.getnchannels()==1
        pcm=source.readframes(source.getnframes())
    async with httpx.AsyncClient(trust_env=False) as client:
        state=(await client.get('http://127.0.0.1:4180/api/live/state')).json()
        original_items=len(state['events'])
        task=next(t for group in state['tasks'].values() for t in group if t['title']=='写报告')
        r=await client.patch('http://127.0.0.1:4180/api/live/tasks/'+task['id']+'/steps',json={'event_id':str(uuid4()),'updates':[{'step_id':s['id'],'done':False} for s in task['steps'][:2]]});r.raise_for_status()
    results=[];begin=time.monotonic()
    async with websockets.connect('ws://127.0.0.1:4180/api/live/audio',proxy=None) as ws:
        print(await ws.recv(),flush=True)
        async def receive():
            async for msg in ws:
                obj=json.loads(msg);results.append(obj); print(json.dumps(obj,ensure_ascii=False),flush=True)
        reader=asyncio.create_task(receive())
        for offset in range(0,len(pcm),3200):
            await ws.send(pcm[offset:offset+3200]);await asyncio.sleep(.1)
        for _ in range(10):
            await ws.send(bytes(3200));await asyncio.sleep(.1)
        await ws.send(json.dumps({'type':'stop'}))
        await asyncio.wait_for(reader,90)
    assert any(r['type']=='result' and len(r.get('changed_steps',[]))>=2 for r in results), 'Expected two confirmed steps'
    async with httpx.AsyncClient(trust_env=False) as client:
        state=(await client.get('http://127.0.0.1:4180/api/live/state')).json()
    assert len(state['events'])==original_items, 'Completion speech must not recreate history reminders'
    report={'wall_ms':round((time.monotonic()-begin)*1000),'events':results,'state':state}
    (ROOT/'artifacts/audio-e2e.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))


asyncio.run(main())
