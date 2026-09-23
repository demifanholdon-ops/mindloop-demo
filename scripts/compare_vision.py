import asyncio,base64,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from live_models import Cloud
from live_store import now
async def probe(model):
 c=Cloud();c.vision_model=model
 img='data:image/jpeg;base64,'+base64.b64encode(Path('artifacts/fixture-open-document.jpg').read_bytes()).decode()
 ctx={'now':now(),'tasks':[{'id':'test','steps':[{'id':'s1','title':'打开报告文档','done':False,'revision':0},{'id':'s2','title':'写两分钟','done':False,'revision':0}]}],'recent':[]}
 try:
  d,ms=await c.decide(ctx,images=[{'captured_at':now(),'image':img}]);row={'model':model,'ms':ms,'decision':d.model_dump()}
 except Exception as e: row={'model':model,'error':str(e)}
 print(json.dumps(row,ensure_ascii=False),flush=True);return row
async def main():
 rows=await asyncio.gather(*[probe(m) for m in ['Qwen/Qwen3-VL-32B-Instruct','Qwen/Qwen3-Omni-30B-A3B-Instruct']])
 Path('artifacts/vision-comparison.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
asyncio.run(main())
