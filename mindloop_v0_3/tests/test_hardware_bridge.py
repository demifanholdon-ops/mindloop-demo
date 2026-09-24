import unittest
from mindloop.hardware_bridge import Link, button_request, is_recoverable_device_error, render_frame, screen_copy, voice_button_action

FONT = '/System/Library/Fonts/STHeiti Medium.ttc'

class Frames(unittest.TestCase):
    def test_chinese_actions_produce_distinct_full_screen_frames(self):
        a = render_frame({'current_action': '打开昨天的 PPT'}, FONT)
        b = render_frame({'current_action': '把手放到触控板上'}, FONT)
        self.assertEqual(len(bytes.fromhex(a)), 1600)
        self.assertNotEqual(a, b)
        self.assertTrue(any(bytes.fromhex(a)))

    def test_long_action_paginates_instead_of_disappearing(self):
        state = {'current_action': '先打开电脑上的项目文件夹，然后找到昨天修改的文档，只写下一个标题，再按完成继续下一步。'}
        self.assertNotEqual(render_frame(state, FONT, 0), render_frame(state, FONT, 1))

    def test_completed_screen_explains_both_choices(self):
        text, footer = screen_copy({'state': 'completed'})
        self.assertEqual(text, '任务完成')
        self.assertEqual(footer, 'K1 新任务 K2 重做末步')

    def test_idle_screen_explains_voice_input(self):
        text, footer = screen_copy({'state': 'idle'})
        self.assertEqual(text, '按 K1 开始语音输入')
        self.assertEqual(footer, '再按 K1 结束并创建任务')


class ButtonRouting(unittest.TestCase):
    def test_idle_k1_single_toggles_onboard_voice_recording(self):
        idle = {'state': 'idle'}
        self.assertEqual(voice_button_action(idle, False, 'k1', 'single', 'usb'), 'start')
        self.assertEqual(voice_button_action(idle, True, 'k1', 'single', 'usb'), 'stop')

    def test_voice_recording_uses_direct_wearable_usb_in_s3_mode(self):
        self.assertEqual(voice_button_action({'state': 'idle'}, False, 'k1', 'single', 's3'), 'start')

    def test_voice_recording_requires_usb(self):
        self.assertEqual(voice_button_action({'state': 'idle'}, False, 'k1', 'single', 'ble'), 'usb_only')

    def test_other_gestures_do_not_interrupt_voice_recording(self):
        self.assertEqual(voice_button_action({'state': 'idle'}, True, 'k1', 'double', 's3'), 'ignore')
        self.assertEqual(voice_button_action({'state': 'idle'}, True, 'k2', 'single', 's3'), 'ignore')

    def test_completed_state_only_accepts_single_click_navigation(self):
        self.assertEqual(button_request({'state': 'completed'}, 'k1', 'long'), (None, None))
        self.assertEqual(button_request({'state': 'completed'}, 'k2', 'double'), (None, None))

    def test_active_task_reuses_two_keys_for_six_actions(self):
        state = {'state': 'action_ready'}
        expected = {
            ('k1', 'single'): ('/api/feedback', {'feedback': 'done'}),
            ('k1', 'double'): ('/api/session/undo', None),
            ('k1', 'long'): ('/api/session/new', None),
            ('k2', 'single'): ('/api/feedback', {'feedback': 'stuck'}),
            ('k2', 'double'): ('/api/feedback', {'feedback': 'help'}),
            ('k2', 'long'): (None, None),
        }
        for gesture, request in expected.items():
            with self.subTest(gesture=gesture):
                self.assertEqual(button_request(state, *gesture), request)

    def test_idle_long_k2_preserves_resume_navigation(self):
        self.assertEqual(button_request({'state': 'idle'}, 'k2', 'long'), ('/api/session/continue', None))

    def test_completed_done_starts_new_task(self):
        self.assertEqual(
            button_request({'state': 'completed'}, 'k1', 'single'),
            ('/api/session/new', None),
        )

    def test_completed_stuck_continues_task(self):
        self.assertEqual(
            button_request({'state': 'completed'}, 'k2', 'single'),
            ('/api/session/continue', None),
        )

class Protocol(unittest.IsolatedAsyncioTestCase):
    async def test_fragmented_and_combined_notifications(self):
        link = Link()
        link.receive(b'{"event":"but')
        self.assertTrue(link.queue.empty())
        link.receive(b'ton","value":"done"}\n{"event":"displayed","id":4}\n')
        self.assertEqual((await link.queue.get())['value'], 'done')
        self.assertEqual((await link.queue.get())['id'], 4)

    async def test_non_protocol_output_does_not_break_reader(self):
        link = Link()
        link.receive(b'booting\n{"event":"ready"}\n')
        self.assertEqual((await link.queue.get())['event'], 'ready')


class BridgeFlow(unittest.IsolatedAsyncioTestCase):
    async def test_buttons_reach_agent_and_updated_actions_reach_display(self):
        import argparse
        import asyncio
        import json
        from unittest.mock import patch
        import httpx
        from mindloop.hardware_bridge import bridge
        state = {'current_action': '打开昨天的 PPT', 'progress': {'done': 0, 'total': 3}}
        feedbacks, frames = [], []
        class FakeLink(Link):
            async def open(self, args):
                pass
            async def send(self, command):
                if command['cmd'] == 'hello':
                    self.queue.put_nowait({'event': 'ready', 'display': True})
                else:
                    frames.append(command['hex'])
                    self.queue.put_nowait({'event': 'displayed', 'id': command['id']})
                    if len(frames) <= 2:
                        self.queue.put_nowait({'event': 'button', 'value': ['done', 'stuck'][len(frames)-1]})
                    else:
                        raise asyncio.CancelledError()
        def handle(request):
            if request.url.path == '/api/feedback':
                value = json.loads(request.content)['feedback']
                feedbacks.append(value)
                state['current_action'] = '只写一个标题' if value == 'done' else '把手放到键盘上'
            return httpx.Response(200, json=state)
        client = httpx.AsyncClient(transport=httpx.MockTransport(handle), base_url='http://test')
        args = argparse.Namespace(api='http://test', font=FONT)
        with patch('mindloop.hardware_bridge.Link', FakeLink), patch(
            'mindloop.hardware_bridge.httpx.AsyncClient', return_value=client
        ) as client_factory:
            with self.assertRaises(asyncio.CancelledError):
                await bridge(args)
        self.assertFalse(client_factory.call_args.kwargs['trust_env'])
        self.assertEqual(feedbacks, ['done', 'stuck'])
        self.assertEqual(len(set(frames)), 3)


class S3Protocol(unittest.IsolatedAsyncioTestCase):
    async def test_s3_voice_usb_ignores_duplicate_button_events(self):
        link = Link()
        link.transport = 's3'
        link.receive(b'{"event":"button","key":"k1","gesture":"single"}\n', voice=True)
        self.assertTrue(link.queue.empty())
        link.receive(b'{"event":"audio_start","sample_rate":16000,"channels":1,"sample_width":2}\n', voice=True)
        self.assertEqual((await link.queue.get())['event'], 'audio_start')

    async def test_reconnect_invalid_json_is_classified_as_recoverable(self):
        # The nRF may answer invalid_json to the deliberate resync newline after reconnect.
        self.assertTrue(is_recoverable_device_error("invalid_json"))
        self.assertFalse(is_recoverable_device_error("haptic_unavailable"))

    async def test_s3_envelopes_survive_fragmentation_and_surface_disconnect(self):
        link = Link()
        link.transport = 's3'
        link.receive(b'{"event":"ble_connecting"}\n{"event":"wear')
        link.receive(b'able","payload":{"event":"button","key":"k2","gesture":"long"}}\n')
        self.assertEqual(await link.queue.get(), {'event': 'button', 'key': 'k2', 'gesture': 'long'})
        self.assertTrue(link.queue.empty())
        link.receive(b'{"event":"ble_disconnected"}\n')
        self.assertEqual(await link.queue.get(), {'event': 'wearable_link', 'connected': False})
        link.receive(b'{"event":"ble_connected"}\n')
        self.assertEqual(await link.queue.get(), {'event': 'wearable_link', 'connected': True})
        link.receive(b'{"event":"heartbeat","seq":1}\n')
        self.assertEqual(await link.queue.get(), {'event': 's3_status', 'payload': {'event': 'heartbeat', 'seq': 1}})

    async def test_s3_buttons_drive_agent_and_frames_use_wire_envelope(self):
        import argparse
        import asyncio
        import json
        from unittest.mock import patch
        import httpx
        from mindloop.hardware_bridge import bridge
        state = {'state': 'action_ready', 'current_action': '打开文档'}
        feedbacks, frames, writes = [], [], []
        class Serial:
            def write(self, data):
                writes.append(json.loads(data))
                return len(data)
            def close(self):
                pass
        class S3Link(Link):
            async def open(self, args):
                self.transport = 's3'
                self.serial = Serial()
            async def send(self, command):
                await super().send(command)
                wire = writes[-1]
                if wire['cmd'] != 'ble_send':
                    raise AssertionError(wire)
                payload = wire['payload']
                if payload['cmd'] == 'hello':
                    event = {'event': 'ready', 'display': True}
                else:
                    frames.append(payload['hex'])
                    event = {'event': 'displayed', 'id': payload['id']}
                self.receive((json.dumps({'event': 'wearable', 'payload': event})+'\n').encode())
                if payload['cmd'] == 'frame':
                    if len(frames) == 4:
                        raise asyncio.CancelledError()
                    key, gesture = [('k1', 'single'), ('k2', 'single'), ('k2', 'double')][len(frames)-1]
                    self.receive((json.dumps({'event': 'wearable', 'payload': {'event': 'button', 'key': key, 'gesture': gesture}})+'\n').encode())
        def handle(request):
            if request.url.path == '/api/feedback':
                feedbacks.append(json.loads(request.content)['feedback'])
                state['current_action'] = ['写标题', '只写一字', '先口述一句'][len(feedbacks)-1]
            return httpx.Response(200, json=state)
        client = httpx.AsyncClient(transport=httpx.MockTransport(handle), base_url='http://test')
        args = argparse.Namespace(api='http://test', font=FONT, transport='s3')
        with patch('mindloop.hardware_bridge.Link', S3Link), patch('mindloop.hardware_bridge.httpx.AsyncClient', return_value=client):
            with self.assertRaises(asyncio.CancelledError):
                await bridge(args)
        self.assertEqual(feedbacks, ['done', 'stuck', 'help'])
        self.assertEqual(len(set(frames)), 4)

if __name__ == '__main__':
    unittest.main()
