"""USB adapter for EvoMap K1/K2 and stop-then-transcribe task creation."""
import asyncio
import base64
import json
import time
from uuid import uuid4

import httpx
import serial


async def run(args):
    if not args.serial:
        raise SystemExit('当前 EvoMap 模式需要 --serial；USB摄像头也可在粉色App选择')
    with serial.Serial(args.serial, 115200, timeout=.2) as device:
        def send(body):
            device.write((json.dumps(body)+'\n').encode())
            device.flush()
        async with httpx.AsyncClient(base_url=args.api, timeout=100, trust_env=False) as client:
            device_id='usb-'+args.serial.rsplit('/',1)[-1]
            capabilities={}
            recording=False
            audio=bytearray()
            expected=0
            started=0
            stopping=False
            handling=False
            events=asyncio.Queue(maxsize=16)
            acks=asyncio.Queue()

            async def post(path, body):
                r=await client.post('/api/live'+path, json=body)
                if not r.is_success:
                    raise RuntimeError(str(r.json().get('detail',r.status_code)))
                return r.json()

            async def heartbeat():
                while True:
                    send({'cmd':'hello'})
                    await post('/device/heartbeat',{'device_id':device_id,'capabilities':capabilities})
                    await asyncio.sleep(3)

            async def worker():
                nonlocal stopping,handling
                while True:
                    kind,payload=await events.get()
                    handling=True
                    try:
                        if kind=='button':
                            result=await post('/legacy/button',{'event_id':str(uuid4()),**payload})
                            if result['action']=='record_start':
                                send({'cmd':'record','action':'start'})
                            elif result['action']=='record_stop':
                                stopping=True
                                send({'cmd':'record','action':'stop'})
                            print('Button:',result.get('reply') or result['action'],flush=True)
                        elif kind=='recording':
                            await post('/legacy/recording',{'recording':True})
                        else:
                            # Stop capture before any cloud request. No auto-restart at 15 seconds.
                            await post('/legacy/recording',{'recording':False})
                            image=None
                            if args.camera_url:
                                r=await client.get(args.camera_url,timeout=5)
                                r.raise_for_status()
                                if len(r.content)>1000000: raise RuntimeError('JPEG画面超过1MB')
                                image='data:image/jpeg;base64,'+base64.b64encode(r.content).decode()
                            result=await post('/legacy/task',{'event_id':str(uuid4()),
                                'pcm':base64.b64encode(payload).decode(),'image':image,'use_camera':True})
                            print('Task:',result['reply'],flush=True)
                    except (RuntimeError,httpx.HTTPError) as exc:
                        print('请求失败：',str(exc),flush=True)
                    finally:
                        handling=False
                        events.task_done()

            async def commands():
                while True:
                    await asyncio.sleep(1)
                    result=await post('/device/next',{'device_id':device_id})
                    command=result.get('command')
                    if not command: continue
                    send({'cmd':'haptic_pattern','id':command['id'],'pattern_ms':command['pattern_ms'],'light':command.get('light','off')})
                    deadline=time.monotonic()+20;ack=None
                    while time.monotonic()<deadline:
                        try: candidate=await asyncio.wait_for(acks.get(),deadline-time.monotonic())
                        except TimeoutError: break
                        if candidate.get('id')==command['id']: ack=candidate;break
                    executed=bool(ack and ack.get('event')=='haptic_done')
                    await post('/device/commands/'+command['id']+'/ack',{'device_id':device_id,
                        'executed':executed,'error':None if executed else '没有收到整组震动成功回执'})

            jobs=[asyncio.create_task(heartbeat()),asyncio.create_task(worker()),asyncio.create_task(commands())]
            print('EvoMap模式：待机单击K1录音，最长15秒，停止后创建；K1/K2操作同步粉色App。',flush=True)
            try:
                while True:
                    for job in jobs:
                        if job.done(): job.result();raise RuntimeError('网关后台任务已停止')
                    if recording and not stopping and time.monotonic()-started>=15:
                        stopping=True;send({'cmd':'record','action':'stop'})
                    raw=await asyncio.to_thread(device.readline)
                    if not raw: continue
                    try: event=json.loads(raw)
                    except (ValueError,UnicodeDecodeError): continue
                    kind=event.get('event')
                    if kind=='ready':
                        capabilities.update({k:bool(event.get(k,False)) for k in ('microphone','haptic_pattern','breathing_light')})
                    elif kind in ('haptic_done','haptic_failed'): acks.put_nowait(event)
                    elif kind=='audio_start':
                        if (event.get('sample_rate'),event.get('channels'),event.get('sample_width'))!=(16000,1,2):
                            raise RuntimeError('需要16kHz单声道PCM16')
                        audio.clear();expected=0;recording=True;stopping=False;started=time.monotonic()
                        events.put_nowait(('recording',None))
                    elif kind=='audio_chunk':
                        if not recording or event.get('seq')!=expected: raise RuntimeError('音频不连续，请重新录音')
                        expected+=1;chunk=base64.b64decode(event['audio'],validate=True)
                        audio.extend(chunk[:max(0,480000-len(audio))])
                    elif kind=='audio_stop':
                        if not recording: continue
                        recording=False;stopping=False
                        if event.get('dropped'): raise RuntimeError('设备音频丢帧，请重新录音')
                        events.put_nowait(('capture',bytes(audio)))
                    elif kind=='button' and event.get('key') in {'k1','k2'} and event.get('gesture') in {'single','double','long'}:
                        if not handling and not stopping:
                            events.put_nowait(('button',{'key':event['key'],'gesture':event['gesture'],'recording':recording}))
            finally:
                send({'cmd':'record','action':'stop'})
                for job in jobs: job.cancel()
                await asyncio.gather(*jobs,return_exceptions=True)
                await post('/legacy/recording',{'recording':False})
