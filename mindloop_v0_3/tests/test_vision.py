import base64,io,unittest
from unittest.mock import patch,AsyncMock
from PIL import Image
from fastapi import HTTPException
from mindloop.vision import CameraContext

def frame():
    b=io.BytesIO();Image.new('RGB',(80,80),'red').save(b,format='JPEG')
    return 'data:image/jpeg;base64,'+base64.b64encode(b.getvalue()).decode()

class CameraTests(unittest.TestCase):
    def test_expiration_and_clear(self):
        c=CameraContext()
        with patch('mindloop.vision.time.monotonic',return_value=100):c.update(frame());self.assertIsNotNone(c.snapshot())
        with patch('mindloop.vision.time.monotonic',return_value=109):self.assertIsNone(c.snapshot())
        c.update(frame());c.clear();self.assertIsNone(c.snapshot())
    def test_reject_invalid_images(self):
        with self.assertRaises(HTTPException):CameraContext().update('data:image/jpeg;base64,notvalid')

class CombinedTests(unittest.IsolatedAsyncioTestCase):
    async def test_combines_scene_with_goal_without_storing_image(self):
        import mindloop.app as a
        a.camera_context.update(frame())
        with patch.object(a.agent,'describe_scene',new=AsyncMock(return_value='桌上有一本书')) as vision,patch.object(a.agent,'decompose',new=AsyncMock(return_value=[{'text':'打开书','seconds':60}])) as model,patch('mindloop.app.save_event'):
            result=await a.start(a.StartRequest(goal='开始读书'))
        self.assertIn('桌上有一本书',model.call_args.args[0])
        self.assertEqual(result['goal'],'开始读书')
        self.assertNotIn('data:image',str(result))
        vision.assert_awaited_once();a.camera_context.clear()

    async def test_cloud_failure_releases_generation_guard(self):
        import mindloop.app as a
        from mindloop.agent import ModelError
        a.camera_context.clear()
        with patch.object(a.agent,'decompose',new=AsyncMock(side_effect=ModelError('failure'))):
            with self.assertRaises(ModelError):await a.start(a.StartRequest(goal='test'))
        self.assertFalse(a.generating)

    async def test_busy_rejects_new_task(self):
        import mindloop.app as a
        a.generating=True
        try:
            with self.assertRaises(HTTPException) as err:await a.new_session()
            self.assertEqual(err.exception.status_code,409)
        finally:a.generating=False
