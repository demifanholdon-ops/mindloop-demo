"""Explicit USB port / camera URL bridge; no auto-flashing and no fake motor ACKs."""
import argparse
import asyncio
import base64
import json
import time
from datetime import datetime, timezone
from uuid import uuid4

import httpx
import serial
import websockets


async def camera_loop(api, url):
    async with httpx.AsyncClient(base_url=api, timeout=55, trust_env=False) as client:
        response = await client.post('/api/live/camera/start', json={})
        response.raise_for_status(); session = response.json()['session_id']
        queue = asyncio.Queue(maxsize=1)

        async def capture():
            async with httpx.AsyncClient(timeout=4, trust_env=False) as camera_client:
                while True:
                    started = time.monotonic()
                    try:
                        image = await camera_client.get(url)
                        image.raise_for_status()
                        if len(image.content)>1500000: raise ValueError('Camera frame exceeds 1.5 MB')
                        mime = 'image/png' if image.content.startswith(b'\x89PNG') else 'image/jpeg'
                        frame = {'event_id': str(uuid4()), 'session_id': session,
                                 'captured_at': datetime.now(timezone.utc).isoformat(),
                                 'image': f'data:{mime};base64,'+base64.b64encode(image.content).decode()}
                        if queue.full(): queue.get_nowait()
                        queue.put_nowait(frame)
                    except (httpx.HTTPError, ValueError) as exc: print('Camera capture error:', type(exc).__name__, flush=True)
                    await asyncio.sleep(max(0, 5-(time.monotonic()-started)))
        producer = asyncio.create_task(capture())
        try:
            while True:
                frame = await queue.get()
                try:
                    r = await client.post('/api/live/image', json=frame)
                    print('Camera result:', r.status_code, r.json().get('reply', r.json().get('detail')), flush=True)
                except httpx.HTTPError: print('Camera processing connection failed; next frame will retry',flush=True)
        finally:
            producer.cancel();await asyncio.gather(producer,return_exceptions=True)
            await client.post('/api/live/camera/stop', json={'session_id':session})


class CameraControl:
    def __init__(self,api,url): self.api=api;self.url=url;self.task=None
    async def toggle(self):
        if self.task and not self.task.done(): await self.stop()
        elif self.url:
            self.task=asyncio.create_task(camera_loop(self.api,self.url))
            self.task.add_done_callback(lambda t: print('Camera stopped:',str(t.exception()),flush=True) if not t.cancelled() and t.exception() else None)
        else: print('Double click received; configure --camera-url first',flush=True)
    async def stop(self):
        if self.task: self.task.cancel();await asyncio.gather(self.task,return_exceptions=True);self.task=None


async def serial_loop(api,port,camera):
    ws_url=api.replace('http://','ws://').replace('https://','wss://')+'/api/live/audio'
    device_id='usb-'+port.rsplit('/',1)[-1]
    with serial.Serial(port,115200,timeout=.2) as device:
        def send(cmd): device.write((json.dumps(cmd)+'\n').encode());device.flush()
        async with websockets.connect(ws_url,max_size=2000000,proxy=None) as ws, httpx.AsyncClient(base_url=api,timeout=10,trust_env=False) as client:
            acknowledgements=asyncio.Queue();capabilities={};recording=False;keep_recording=True;expected=0
            async def results():
                async for msg in ws:
                    data=json.loads(msg)
                    print('Voice:',data.get('type'),data.get('reply',data.get('message','')),flush=True)
            async def heartbeat():
                while True:
                    send({'cmd':'hello'})
                    r=await client.post('/api/live/device/heartbeat',json={'device_id':device_id,'capabilities':capabilities});r.raise_for_status()
                    await asyncio.sleep(3)
            async def commands():
                while True:
                    await asyncio.sleep(1)
                    r=await client.post('/api/live/device/next',json={'device_id':device_id})
                    if r.status_code==409: continue
                    r.raise_for_status();cmd=r.json().get('command')
                    if not cmd: continue
                    # Only advertised haptic_pattern firmware may receive this command.
                    # The ZIP's short/double_soft patterns do not meet the requested duration.
                    send({'cmd':'haptic_pattern','id':cmd['id'],'pattern_ms':cmd['pattern_ms'],'light':cmd.get('light','off')})
                    deadline=time.monotonic()+20;ack=None
                    while time.monotonic()<deadline:
                        try: candidate=await asyncio.wait_for(acknowledgements.get(),deadline-time.monotonic())
                        except TimeoutError: break
                        if candidate.get('id')==cmd['id']: ack=candidate;break
                    await client.post('/api/live/device/commands/'+cmd['id']+'/ack',json={'device_id':device_id,'executed':bool(ack and ack.get('event')=='haptic_done'),'error':None if ack and ack.get('event')=='haptic_done' else 'No successful device acknowledgement'})
            jobs=[asyncio.create_task(results()),asyncio.create_task(heartbeat()),asyncio.create_task(commands())]
            send({'cmd':'record','action':'start'})
            try:
                while True:
                    for job in jobs:
                        if job.done(): job.result();raise RuntimeError('Gateway connection closed')
                    raw=await asyncio.to_thread(device.readline)
                    if not raw: continue
                    try: event=json.loads(raw)
                    except (ValueError,UnicodeDecodeError): continue
                    kind=event.get('event')
                    if kind=='ready': capabilities.update({k:bool(event.get(k,False)) for k in ('microphone','haptic_pattern','breathing_light')})
                    elif kind in ('haptic_done','haptic_failed'): acknowledgements.put_nowait(event)
                    elif kind=='audio_start':
                        if (event.get('sample_rate'),event.get('channels'),event.get('sample_width'))!=(16000,1,2): raise RuntimeError('Expected 16 kHz mono PCM16')
                        expected=0;recording=True
                    elif kind=='audio_chunk':
                        if event.get('seq')!=expected: raise RuntimeError('Missing audio chunk; restart recording')
                        expected+=1;await ws.send(base64.b64decode(event['audio'],validate=True))
                    elif kind=='audio_stop':
                        recording=False;await ws.send(json.dumps({'type':'flush'}))
                        if event.get('dropped'): raise RuntimeError('Device reported dropped audio')
                        if keep_recording: send({'cmd':'record','action':'start'})
                    elif kind=='button' and event.get('key')=='k1':
                        if event.get('gesture')=='single':
                            keep_recording=not keep_recording
                            send({'cmd':'record','action':'start' if keep_recording else 'stop'})
                        elif event.get('gesture')=='double': await camera.toggle()
                        elif event.get('gesture')=='triple':
                            r=await client.post('/api/live/refocus',json={});r.raise_for_status()
            finally:
                send({'cmd':'record','action':'stop'})
                if not ws.close_code: await ws.send(json.dumps({'type':'stop'}))
                for job in jobs: job.cancel()
                await asyncio.gather(*jobs,return_exceptions=True)
                await camera.stop()


async def main(args):
    camera=CameraControl(args.api,args.camera_url)
    if args.serial: await serial_loop(args.api,args.serial,camera)
    elif args.camera_url: await camera_loop(args.api,args.camera_url)
    else: raise SystemExit('Provide --serial and/or --camera-url')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--api',default='http://127.0.0.1:4173')
    p.add_argument('--serial');p.add_argument('--camera-url')
    try: asyncio.run(main(p.parse_args()))
    except KeyboardInterrupt: pass
