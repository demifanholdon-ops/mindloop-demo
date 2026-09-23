"""Small real API latency sample using only a synthetic image and synthetic text."""
import asyncio
import base64
import io
import json
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from live_models import Cloud
from live_store import now


async def main():
    cloud = Cloud()
    picture = Image.new("RGB", (960,540), "#ededed")
    d = ImageDraw.Draw(picture)
    d.rectangle((50,40,910,440), fill="white", outline="black", width=3)
    font = ImageFont.truetype("/System/Library/Fonts/STHeiti Medium.ttc", 30)
    d.text((90,90), "项目报告", fill="black", font=font)
    d.text((90,145), "今天完成了第一段内容。", fill="black", font=font)
    d.text((90,220), "合成测试画面，不是摄像头实拍", fill="#555555", font=font)
    buf = io.BytesIO(); picture.save(buf, format="JPEG")
    (ROOT / "artifacts/fixture-document.jpg").write_bytes(buf.getvalue())
    frame = {"captured_at": now(), "image": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()}
    ctx = {"now": now(), "tasks": [{"id":"task_test", "title":"写报告", "steps":[{"id":"step_test", "title":"打开报告文档", "done":False, "revision":0}]}], "recent":[]}
    results=[]
    for mode in ["text", "vision", "vision", "vision"]:
        try:
            decision, ms = await cloud.decide(ctx, text="我已经打开报告文档了。" if mode=="text" else None, images=[frame] if mode=="vision" else None)
            row={"mode":mode,"ms":ms,"result":decision.model_dump()}
        except Exception as exc: row={"mode":mode,"error":str(exc)}
        results.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
    (ROOT/"artifacts/model-latency.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf8")

asyncio.run(main())
