"""Real vision API replay with a synthetic document fixture, not a physical camera test."""
import asyncio
import base64
import io
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import httpx
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]


async def main():
    img=Image.new('RGB',(960,540),'#151820');d=ImageDraw.Draw(img)
    f=ImageFont.truetype('/System/Library/Fonts/STHeiti Medium.ttc',24)
    d.rectangle((20,20,940,500),fill='#f8f8f8');d.rectangle((20,20,940,70),fill='#e0e1e4')
    d.text((45,32),'项目报告.md — 文档编辑器',fill='black',font=f)
    d.text((50,82),'文件    编辑    查看    保存',fill='black',font=f)
    d.rectangle((160,120,800,480),fill='white',outline='#bbb')
    d.text((205,155),'项目报告',fill='black',font=f)
    d.text((205,220),'一、今天的进展',fill='black',font=f)
    d.text((205,265),'我已经写下报告的第一段。',fill='black',font=f)
    buf=io.BytesIO();img.save(buf,format='JPEG');(ROOT/'artifacts/fixture-open-document.jpg').write_bytes(buf.getvalue())
    async with httpx.AsyncClient(base_url='http://127.0.0.1:4180',timeout=65,trust_env=False) as c:
        state=(await c.get('/api/live/state')).json()
        task=next(t for group in state['tasks'].values() for t in group if t['title']=='写报告')
        r=await c.patch('/api/live/tasks/'+task['id']+'/steps',json={'event_id':str(uuid4()),'updates':[{'step_id':s['id'],'done':False} for s in task['steps']]});r.raise_for_status()
        s=await c.post('/api/live/camera/start');s.raise_for_status();session=s.json()['session_id']
        try:
            t=time.monotonic()
            r=await c.post('/api/live/image',json={'event_id':str(uuid4()),'session_id':session,'captured_at':datetime.now(timezone.utc).isoformat(),'image':'data:image/jpeg;base64,'+base64.b64encode(buf.getvalue()).decode()})
            r.raise_for_status();result=r.json();result['http_roundtrip_ms']=round((time.monotonic()-t)*1000)
            print(json.dumps(result,ensure_ascii=False),flush=True)
            state=(await c.get('/api/live/state')).json()
            (ROOT/'artifacts/vision-e2e.json').write_text(json.dumps({'fixture':'synthetic document UI, not physical camera','result':result,'state':state},ensure_ascii=False,indent=2))
            after=next(t for group in state['tasks'].values() for t in group if t['id']==task['id'])
            assert not after['steps'][2]['done'], 'A static picture cannot prove two minutes of writing'
            assert result['changed_steps'], 'Expected visible document step to be confirmed'
        finally: await c.post('/api/live/camera/stop',json={'session_id':session})


asyncio.run(main())
