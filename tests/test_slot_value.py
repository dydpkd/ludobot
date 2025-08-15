import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import bot


def test_slot_value_symbols_exist():
    symbols = {symbol for combo in bot.slot_value.values() for symbol in combo}
    assert symbols <= set(bot.EMOJI)


def test_get_next_jackpot_phrase_cycle():
    bot._jackpot_cycle_remaining = []
    bot._jackpot_cycle_lock = None

    async def collect():
        phrases = set()
        for _ in range(len(bot.JACKPOT_PHRASES)):
            phrase = await bot.get_next_jackpot_phrase()
            assert phrase not in phrases
            phrases.add(phrase)
        return phrases

    collected = asyncio.run(collect())
    assert collected == set(bot.JACKPOT_PHRASES)
