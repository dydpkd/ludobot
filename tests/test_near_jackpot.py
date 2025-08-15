import asyncio
import os
import random
import sys
import importlib
from types import SimpleNamespace

sys.path.append(os.path.dirname(os.path.dirname(__file__)))


def test_near_jackpot_delay_range():
    import bot
    importlib.reload(bot)
    class DummyMessage:
        def __init__(self):
            self.dice = SimpleNamespace(emoji="🎰", value=2)  # two-of-a-kind
        async def reply_text(self, text):
            pass

    update = SimpleNamespace(
        effective_message=DummyMessage(),
        effective_user=SimpleNamespace(id=1, full_name="User", username="user"),
        effective_chat=SimpleNamespace(id=1),
    )
    context = SimpleNamespace()

    captured = {}

    def fake_uniform(a, b):
        captured['range'] = (a, b)
        return 5.5

    async def fake_sleep(delay):
        captured['delay'] = delay

    orig_uniform = random.uniform
    orig_sleep = asyncio.sleep
    orig_randint = random.randint
    random.uniform = fake_uniform
    asyncio.sleep = fake_sleep
    random.randint = lambda a, b: 1
    try:
        asyncio.run(bot.on_dice(update, context))
    finally:
        random.uniform = orig_uniform
        asyncio.sleep = orig_sleep
        random.randint = orig_randint

    assert captured['range'] == (bot.NEAR_JACKPOT_DELAY_MIN, bot.NEAR_JACKPOT_DELAY_MAX)
    assert bot.NEAR_JACKPOT_DELAY_MIN <= captured['delay'] <= bot.NEAR_JACKPOT_DELAY_MAX
