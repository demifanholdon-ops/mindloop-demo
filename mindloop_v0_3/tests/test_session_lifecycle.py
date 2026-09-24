import unittest
from unittest.mock import patch

import httpx

import mindloop.app as app_module


class CompletedSessionTests(unittest.IsolatedAsyncioTestCase):
    def seed_completed(self):
        app_module.session.update({
            "goal": "准备汇报",
            "state": "completed",
            "actions": [
                {"text": "打开 PPT", "seconds": 30},
                {"text": "写标题", "seconds": 30},
            ],
            "index": 1,
            "current_action": None,
            "intervention": {"channel": "haptic", "pattern": "success"},
            "history": [],
        })

    async def request(self, path):
        transport = httpx.ASGITransport(app=app_module.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(path)

    async def test_new_task_returns_to_idle(self):
        self.seed_completed()
        with patch("mindloop.app.save_event"):
            response = await self.request("/api/session/new")
        self.assertEqual(response.status_code, 200)
        state = response.json()
        self.assertEqual(state["state"], "idle")
        self.assertEqual(state["goal"], "")
        self.assertEqual(state["actions"], [])
        self.assertIsNone(state["current_action"])

    async def test_continue_reopens_last_action(self):
        self.seed_completed()
        with patch("mindloop.app.save_event"):
            response = await self.request("/api/session/continue")
        self.assertEqual(response.status_code, 200)
        state = response.json()
        self.assertEqual(state["state"], "action_ready")
        self.assertEqual(state["index"], 1)
        self.assertEqual(state["current_action"], "写标题")
        self.assertEqual(state["progress"]["done"], 1)

    async def test_undo_reopens_previous_action(self):
        app_module.session.update({
            "goal": "准备汇报",
            "state": "action_ready",
            "actions": [
                {"text": "打开 PPT", "seconds": 30},
                {"text": "写标题", "seconds": 30},
            ],
            "index": 1,
            "current_action": "写标题",
            "intervention": {"channel": "haptic", "pattern": "short"},
            "history": [],
        })
        with patch("mindloop.app.save_event"):
            response = await self.request("/api/session/undo")
        self.assertEqual(response.status_code, 200)
        state = response.json()
        self.assertEqual(state["index"], 0)
        self.assertEqual(state["current_action"], "打开 PPT")
        self.assertEqual(state["progress"]["done"], 0)

    async def test_continue_restores_last_task_after_new_task_reset(self):
        self.seed_completed()
        with patch("mindloop.app.save_event"):
            reset = await self.request("/api/session/new")
            resumed = await self.request("/api/session/continue")
        self.assertEqual(reset.status_code, 200)
        self.assertEqual(resumed.status_code, 200)
        state = resumed.json()
        self.assertEqual(state["goal"], "准备汇报")
        self.assertEqual(state["current_action"], "写标题")


if __name__ == "__main__":
    unittest.main()
