import unittest
from unittest.mock import patch
import mindloop.app as app
from mindloop.hardware_bridge import voice_button_action, button_request

class InteractionSafety(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.saved = patch('mindloop.app.save_event').start()
        self.memory = patch('mindloop.app.load_memory', return_value={'events': []}).start()
        app.last_session = None
        app.session.update(state='idle', actions=[], index=0, goal='', current_action=None, history=[])
        self.addCleanup(patch.stopall)

    async def test_unfinished_task_can_resume_exact_step(self):
        await app.start(app.StartRequest(goal='论文'))
        await app.feedback(app.FeedbackRequest(feedback='done'))
        action = app.session['current_action']
        await app.new_session()
        await app.continue_session()
        self.assertEqual(app.session['index'], 1)
        self.assertEqual(app.session['current_action'], action)

    async def test_continue_cannot_replace_active_task(self):
        await app.start(app.StartRequest(goal='旧任务'))
        await app.new_session()
        await app.start(app.StartRequest(goal='新任务'))
        with self.assertRaises(app.HTTPException) as ctx:
            await app.continue_session()
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(app.session['goal'], '新任务')

    def test_transcription_and_stopping_ignore_all_buttons(self):
        for mode in ('transcribing', 'stopping'):
            for key in ('k1','k2'):
                for gesture in ('single','double','long'):
                    self.assertEqual(voice_button_action({'state':'idle'}, mode, key, gesture, 's3'), 'ignore')

    def test_idle_invalid_buttons_do_not_send_feedback(self):
        self.assertEqual(button_request({'state':'idle'}, 'k2','single'), (None,None))

    def test_k2_help_gesture_is_not_duplicated(self):
        self.assertEqual(button_request({'state':'action_ready'}, 'k2','long'), (None,None))

class BridgeRecognitionLock(unittest.IsolatedAsyncioTestCase):
    async def test_real_bridge_does_not_restart_recording_during_transcription(self):
        import argparse, asyncio, httpx
        from mindloop.hardware_bridge import Link, bridge
        commands = []
        class FakeLink(Link):
            async def open(self, args):
                pass
            async def send(self, command):
                commands.append(command['cmd'])
                if command['cmd'] == 'hello':
                    self.queue.put_nowait({'event':'ready','display':True})
                    self.queue.put_nowait({'event':'audio_stop','dropped':0})
                    self.queue.put_nowait({'event':'button','key':'k1','gesture':'single'})
                elif command['cmd'] == 'frame':
                    raise asyncio.CancelledError()
        async def transcribe(*args):
            await asyncio.sleep(30)
        client=httpx.AsyncClient(base_url='http://test',transport=httpx.MockTransport(lambda req: httpx.Response(200,json={'state':'idle'})))
        args=argparse.Namespace(transport='usb',api='http://test',font='/System/Library/Fonts/STHeiti Medium.ttc')
        with patch('mindloop.hardware_bridge.Link',FakeLink), patch('mindloop.hardware_bridge.httpx.AsyncClient',return_value=client), patch('mindloop.hardware_bridge.transcribe_capture',transcribe):
            with self.assertRaises(asyncio.CancelledError):
                await bridge(args)
        self.assertNotIn('record',commands)
