import asyncio
import importlib
import os
import sys
from types import SimpleNamespace

sys.path.append(os.path.dirname(os.path.dirname(__file__)))


def test_jackpot_delay_env(monkeypatch):
    monkeypatch.setenv("JACKPOT_DELAY", "2.5")
    import bot
    importlib.reload(bot)

    class DummyMessage:
        def __init__(self):
            self.dice = SimpleNamespace(emoji="🎰", value=64)
        async def reply_text(self, text):
            pass

    update = SimpleNamespace(
        effective_message=DummyMessage(),
        effective_user=SimpleNamespace(id=1, full_name="User", username="user"),
        effective_chat=SimpleNamespace(id=1),
    )
    context = SimpleNamespace()

    captured = {}

    async def fake_sleep(delay):
        captured['delay'] = delay

    orig_sleep = asyncio.sleep
    asyncio.sleep = fake_sleep
    try:
        asyncio.run(bot.on_dice(update, context))
    finally:
        asyncio.sleep = orig_sleep
        monkeypatch.delenv("JACKPOT_DELAY", raising=False)
        importlib.reload(bot)

    assert captured['delay'] == 2.5
