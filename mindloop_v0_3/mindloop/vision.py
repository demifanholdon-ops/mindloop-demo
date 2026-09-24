"""Opt-in, short-lived camera context. Raw frames never enter event storage."""
import base64
import io
import time
from PIL import Image
from fastapi import HTTPException

class CameraContext:
    def __init__(self):
        self.clear()

    def clear(self):
        self.image = None
        self.received = 0.0

    def update(self, image):
        if not image.startswith('data:image/jpeg;base64,') or len(image) > 1500000:
            raise HTTPException(400, '图片必须为小于1MB的JPEG')
        try:
            raw = base64.b64decode(image.split(',',1)[1], validate=True)
            with Image.open(io.BytesIO(raw)) as pic:
                if pic.format != 'JPEG' or max(pic.size)>1280:
                    raise ValueError()
                pic.verify()
        except Exception:
            raise HTTPException(400, '图片无效或尺寸超过1280') from None
        self.image, self.received = image, time.monotonic()

    def snapshot(self):
        if time.monotonic()-self.received > 8:
            self.clear()
        return self.image
