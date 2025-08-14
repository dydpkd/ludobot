#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ludooman Bot — Telegram slot 🎰 tracker
- Silent count of 🎰 spins in groups
- On triple (jackpot) sends a random phrase from a preset list (with 2s delay)
- SQLite stats (persistent with Railway Volume)
- Commands: /mystats, /stats, /help

ENV:
  TG_TOKEN       - required
  DB_PATH        - default ./casino_stats.sqlite3 (use /data/... with Railway Volume)
  WEBHOOK_BASE   - enable webhook (https://YOUR.up.railway.app)
  WEBHOOK_PATH   - optional fixed webhook path
"""
import os, sqlite3, logging, hashlib, random, asyncio
from typing import Tuple
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ludooman")

TOKEN = os.getenv("TG_TOKEN")
DB_PATH = os.getenv("DB_PATH", "casino_stats.sqlite3")
WEBHOOK_BASE = os.getenv("WEBHOOK_BASE")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH")
PORT = int(os.getenv("PORT", "8080"))

# ---- jackpot phrases (sent on triples) ----
JACKPOT_PHRASES = [
    "На нахуй, я богат! Теперь хоть доширак с мясом куплю.",
    "ДА ЛАДНО! Аппарат, ты шо, заболел?",
    "Ёб твою мать… оно реально дало?!",
    "Вишенки мои сладкие, я вас дождался!",
    "А вот и мой билет в мир долгов побольше.",
    "На, сучара, я ж говорил — я твой батя!",
    "Джекпот?! Всё, увольняюсь нахрен… завтра.",
    "Аппарат, ты сегодня добрый, или просто издеваешься?",
    "Ну, ёбаный в рот, вот оно, счастье с процентами.",
    "Да ну, я ж просто мелочь хотел скрутить…",
    "Блядь, теперь точно заберут почку, пока домой дойду.",
    "На, в карму мне плюс, в печень минус.",
    "Ебать, я в плюсе! На целых 5 минут.",
    "ХА! И кто тут везунчик, мать твою!",
    "Аппарат, ты меня что, перепутал?",
    "Джекпот, блядь, а жизнь всё ещё говно.",
    "Ух ты, я теперь почти как миллиардер… только без миллиардов.",
    "Это мне за все ночи, сука!",
    "На, держи, мозг мой, этот дофаминчик.",
    "Сука, я ж знал, что ты любишь меня.",
    "Ну всё, поехали в Вегас… на маршрутке.",
    "Ебать, пошла жара!",
    "Чисто маме на отпуск… на два дня.",
    "Джекпот — и всё равно хата в ипотеке.",
    "Опа, кто сегодня пьёт за мой счёт? Никто, потому что я домой.",
    "Наконец-то! Хоть штаны новые куплю.",
    "Аппарат, ты меня так не балуй, привыкну ведь.",
    "А я уж думал, что ты только жрёшь…",
    "Ну давай, ещё разок, чтоб я поверил.",
    "Ебаный стыд, я аж заикаться начал.",
    "Мать честная, у меня же пульс 200!",
    "Слышь, автомат, ты чё, влюбился?",
    "О, пошла халява — держите меня семеро.",
    "На тебе, бывшая, вот так надо верить в мужика!",
    "И это всё? А чё не миллион?",
    "Ну здравствуй, иллюзия богатства.",
    "Спасибо, автомат, теперь я в нуле.",
    "Да ладно, неужели я в списке счастливчиков?",
    "Твою ж мать, я ж почти ушёл…",
    "Ну хоть не зря печень сегодня травил.",
    "Аппарат, ты что, меня жалеешь?",
    "Ёб твою налево, я аж икать начал.",
    "Опа, вот и моя премия за тупость.",
    "Ну, теперь-то я точно в плюсе… на минуту.",
    "Это как секс без обязательств — быстро и приятно.",
    "Джекпот, сука, я тебя вымолил!",
    "Наконец-то мои молитвы автомату услышаны.",
    "Пошла родная, давай ещё!",
    "Сука, ты это специально сделал, чтоб я не ушёл?",
    "Всё, теперь я могу сдохнуть… но с улыбкой.",
]

# ---- mapping of 1..64 to slot symbols (🍺, 🍇, 🍋, 7️⃣) ----
slot_value = {
    1: ("bar","bar","bar"), 2: ("grape","bar","bar"), 3: ("lemon","bar","bar"), 4: ("seven","bar","bar"),
    5: ("bar","grape","bar"), 6: ("grape","grape","bar"), 7: ("lemon","grape","bar"), 8: ("seven","grape","bar"),
    9: ("bar","lemon","bar"),10: ("grape","lemon","bar"),11: ("lemon","lemon","bar"),12: ("seven","lemon","bar"),
   13: ("bar","seven","bar"),14: ("grape","seven","bar"),15: ("lemon","seven","bar"),16: ("seven","seven","bar"),
   17: ("bar","bar","grape"),18: ("grape","bar","grape"),19: ("lemon","bar","grape"),20: ("seven","bar","grape"),
   21: ("bar","grape","grape"),22: ("grape","grape","grape"),23: ("lemon","grape","grape"),24: ("seven","grape","grape"),
   25: ("bar","lemon","grape"),26: ("grape","lemon","grape"),27: ("lemon","lemon","grape"),28: ("seven","lemon","grape"),
   29: ("bar","seven","grape"),30: ("grape","seven","grape"),31: ("lemon","seven","grape"),32: ("seven","seven","grape"),
   33: ("bar","bar","lemon"),34: ("grape","bar","lemon"),35: ("lemon","bar","lemon"),36: ("seven","bar","lemon"),
   37: ("bar","grape","lemon"),38: ("grape","grape","lemon"),39: ("lemon","grape","lemon"),40: ("seven","grape","lemon"),
   41: ("bar","lemon","lemon"),42: ("grape","lemon","lemon"),43: ("lemon","lemon","lemon"),44: ("seven","lemon","lemon"),
   45: ("bar","seven","lemon"),46: ("grape","seven","lemon"),47: ("lemon","seven","lemon"),48: ("seven","seven","lemon"),
   49: ("bar","bar","seven"),50: ("grape","bar","seven"),51: ("lemon","bar","seven"),52: ("seven","bar","seven"),
   53: ("bar","grape","seven"),54: ("grape","grape","seven"),55: ("lemon","grape","seven"),56: ("seven","grape","seven"),
   57: ("bar","lemon","seven"),58: ("grape","lemon","seven"),59: ("lemon","lemon","seven"),60: ("seven","lemon","seven"),
   61: ("bar","seven","seven"),62: ("grape","seven","seven"),63: ("lemon","seven","seven"),64: ("seven","seven","seven"),
}
EMOJI = {"bar":"🍺", "grape":"🍇", "lemon":"🍋", "seven":"7️⃣"}

# ---- DB with auto-dir creation and fallback ----
_conn = None
def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        db_dir = os.path.dirname(DB_PATH)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        try:
            _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        except sqlite3.OperationalError as e:
            fallback = "/tmp/casino_stats.sqlite3"
            log.warning("DB open failed for %s (%s). Falling back to %s", DB_PATH, e, fallback)
            os.makedirs("/tmp", exist_ok=True)
            _conn = sqlite3.connect(fallback, check_same_thread=False)

        __conn.execute("""
        CREATE TABLE IF NOT EXISTS results(
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT,
            combo TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(chat_id, user_id, combo)
        )""")
        _conn.execute("""
        CREATE TABLE IF NOT EXISTS totals(
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            spins INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(chat_id, user_id)
        )""")
        _conn.commit()
    return _conn

def upsert_result(chat_id:int, user_id:int, username:str, combo:str):
    c = get_conn()
    with c:
        c.execute("""
        INSERT INTO results(chat_id,user_id,username,combo,count)
        VALUES(?,?,?,?,1)
        ON CONFLICT(chat_id,user_id,combo) DO UPDATE SET
           count = count + 1,
           username = excluded.username
        """,(chat_id,user_id,username,combo))
        c.execute("""
        INSERT INTO totals(chat_id,user_id,spins) VALUES(?, ?, 1)
        ON CONFLICT(chat_id,user_id) DO UPDATE SET spins = spins + 1
        """,(chat_id,user_id))

def fetch_user_stats(chat_id:int, user_id:int):
    c = get_conn()
    rows = c.execute("""
      SELECT combo, count FROM results
      WHERE chat_id=? AND user_id=?
      ORDER BY count DESC
    """,(chat_id,user_id)).fetchall()
    t = c.execute("SELECT spins FROM totals WHERE chat_id=? AND user_id=?",(chat_id,user_id)).fetchone()
    return rows, (t[0] if t else 0)

def fetch_leaderboard(chat_id:int, combos:Tuple[str,...]):
    c = get_conn()
    q = ",".join("?"*len(combos))
    return c.execute(f"""
      SELECT username, combo, SUM(count) c
      FROM results
      WHERE chat_id=? AND combo IN ({q})
      GROUP BY username, combo
      ORDER BY combo, c DESC
    """, (chat_id, *combos)).fetchall()

def fetch_spins_by_username(chat_id:int):
    """Map username -> total spins in chat (uses any stored username for user_id)."""
    c = get_conn()
    rows = c.execute("""
      SELECT r.username, t.spins
      FROM totals t
      JOIN (
        SELECT chat_id, user_id, MAX(username) AS username
        FROM results
        WHERE chat_id=?
        GROUP BY chat_id, user_id
      ) r ON r.chat_id=t.chat_id AND r.user_id=t.user_id
      WHERE t.chat_id=?
    """, (chat_id, chat_id)).fetchall()
    return {u: s for (u, s) in rows if u is not None}

# ---- Helpers ----
def _compact_combo(key: str) -> str:
    # "seven|seven|seven" -> "7️⃣7️⃣7️⃣"  (без пробелов)
    return "".join(EMOJI[x] for x in key.split("|"))

# ---- Handlers ----
async def on_dice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = update.effective_message
    d = getattr(m, "dice", None)
    if not d or d.emoji != "🎰":
        return
    # ignore forwards
    if any(getattr(m, a, None) for a in ("forward_origin","forward_from","forward_from_chat","forward_sender_name")) \
       or getattr(m, "is_automatic_forward", False):
        return
    value = int(d.value)
    combo_tuple = slot_value.get(value)
    if not combo_tuple:
        return
    combo_key = "|".join(combo_tuple)
    user = update.effective_user
    username = user.full_name or (user.username and f"@{user.username}") or str(user.id)
    upsert_result(update.effective_chat.id, user.id, username, combo_key)

    # if triple (jackpot) -> 2s delay + random phrase
    if combo_tuple[0] == combo_tuple[1] == combo_tuple[2]:
        try:
            await asyncio.sleep(3)  # неблокирующая задержка
            phrase = random.choice(JACKPOT_PHRASES)
            await m.reply_text(phrase)  # reply to the jackpot message
        except Exception:
            log.exception("Failed to send jackpot phrase")

    # no reply for non-triples

async def cmd_mystats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    rows, total = fetch_user_stats(chat_id, user.id)
    if not rows:
        await update.message.reply_text("No data yet. Send 🎰 and come back.")
        return

    name = user.full_name or (user.username and f"@{user.username}") or str(user.id)
    lines = []
    lines.append(f"<b>Top combos</b> — {name}:")
    for combo, cnt in rows[:15]:
        compact = _compact_combo(combo)
        lines.append(f"{compact} — {cnt}")
    lines.append("")
    lines.append(f"<b>Total spins</b>: {total}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    triples = ("seven|seven|seven","grape|grape|grape","lemon|lemon|lemon","bar|bar|bar")
    board = fetch_leaderboard(chat_id, triples)
    if not board:
        await update.message.reply_text("No data in this chat yet. Spin 🎰!")
        return

    # triples per user
    totals_by_user = {}
    for username, combo, c in board:
        totals_by_user[username] = totals_by_user.get(username, 0) + c
    total_triples = sum(totals_by_user.values())

    # luck list (desc by rate). Format: rate (≈1/N)
    spins_by_user = fetch_spins_by_username(chat_id)
    luck_rows = []
    for u, triples_cnt in totals_by_user.items():
        spins = spins_by_user.get(u, 0)
        if spins > 0 and triples_cnt > 0:
            rate = triples_cnt / spins
            per_n = int(round(spins / triples_cnt))
            luck_rows.append((rate, u, per_n))
    luck_rows.sort(key=lambda x: x[0], reverse=True)

    # per-combo leaders (to number later)
    by = {c:[] for c in triples}  # combo -> list[(username, count)]
    for username, combo, c in board:
        by[combo].append((username, c))

    # output
    lines = []
    lines.append(f"<b>Total Jackpot:</b> {total_triples}")
    lines.append("")  # empty line after Total Jackpot

    lines.append("<b>TheMostLuckyPerson:</b>")
    lines.append("")
    if luck_rows:
        for idx, (rate, u, per_n) in enumerate(luck_rows, start=1):
            lines.append(f"{idx}. {u} — {rate:.3f} (≈1/{per_n})")
    else:
        lines.append("—")

    lines.append("")
    lines.append("<b>Users Total Jackpot:</b>")
    lines.append("")
    top_users = sorted(totals_by_user.items(), key=lambda kv: kv[1], reverse=True)
    if top_users:
        for idx, (u, n) in enumerate(top_users[:10], start=1):
            lines.append(f"{idx}. {u} — {n}")
    else:
        lines.append("—")

    lines.append("")
    lines.append("<b>Total Combination Jackpot:</b>")
    lines.append("")
    for k in triples:
        header = f"{_compact_combo(k)}:"
        vals = by.get(k) or []
        lines.append(header)
        if vals:
            for idx, (u, n) in enumerate(vals[:5], start=1):
                lines.append(f"{idx}. {u} — {n}")
        else:
            lines.append("—")
        lines.append("")

    while lines and lines[-1] == "":
        lines.pop()

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Commands:\n"
        "/mystats — your stats\n"
        "/stats — leaders by triple matches (with totals & luck list)\n"
        "/help — this help\n\n"
        "Send 🎰 in the chat — I count it silently. Triples trigger a random phrase (after 2s) 😉"
    )

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.exception("Error while handling update", exc_info=context.error)

def webhook_path_from_token(token: str) -> str:
    return f"/telegram/{hashlib.sha256(token.encode()).hexdigest()[:16]}"

def build_app() -> Application:
    if not TOKEN:
        raise SystemExit("Set TG_TOKEN env var")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.Dice.SLOT_MACHINE, on_dice))
    app.add_handler(CommandHandler("mystats", cmd_mystats))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_error_handler(on_error)
    return app

def main():
    app = build_app()
    if WEBHOOK_BASE:
        path = WEBHOOK_PATH or webhook_path_from_token(TOKEN)
        url = WEBHOOK_BASE.rstrip('/') + path
        log.info("Starting webhook on %s", url)
        app.run_webhook(listen="0.0.0.0", port=PORT, url_path=path, webhook_url=url, drop_pending_updates=True)
    else:
        log.info("Starting polling (no WEBHOOK_BASE set)")
        app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
