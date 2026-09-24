import unittest

from mindloop.agent import Agent


class MockShrinkTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_stuck_does_not_nest_instruction(self):
        agent = Agent()
        agent.provider = "mock"
        action = "只写这一页标题"

        for _ in range(4):
            action = (await agent.shrink("准备汇报", action))["text"]

        self.assertEqual(action, "只输入标题的第一个字")
        self.assertNotIn("只做“只做", action)


if __name__ == "__main__":
    unittest.main()

class CloudAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_cloud_failure_does_not_return_template(self):
        from unittest.mock import AsyncMock, patch
        from mindloop.agent import ModelError
        agent = Agent()
        agent.provider = 'openai_compatible'
        with patch.object(agent, '_chat', new=AsyncMock(side_effect=ModelError('unavailable'))):
            with self.assertRaises(ModelError):
                await agent.decompose('准备汇报')

    async def test_alternative_uses_cloud(self):
        from unittest.mock import AsyncMock, patch
        agent = Agent()
        agent.provider = 'openai_compatible'
        with patch.object(agent, '_chat', new=AsyncMock(return_value='先口述一个汇报要点')) as chat:
            result = await agent.alternative('准备汇报', '打开PPT')
        chat.assert_awaited_once()
        self.assertEqual(result['text'], '先口述一个汇报要点')
