#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ludooman Bot — Telegram slot 🎰 tracker
- Слушает 🎰 в группах
- Маппит value (1..64) -> символы барабанов
- Хранит статистику по пользователям в SQLite
- Команды: /mystats, /stats, /help

Запуск:
- Если переменная WEBHOOK_BASE НЕ задана -> long polling (локально)
- Если WEBHOOK_BASE задана -> webhook (PaaS)
Переменные окружения:
  TG_TOKEN     - токен бота (обязательно)
  DB_PATH      - путь к SQLite (по умолчанию ./casino_stats.sqlite3)
  WEBHOOK_BASE - публичный HTTPS (напр. https://your-app.up.railway.app)
  WEBHOOK_PATH - опционально, путь вебхука (по умолчанию /telegram/<hash>)
"""
import os, sqlite3, logging, hashlib
from typing import Tuple
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ludooman")

TOKEN = os.getenv("TG_TOKEN")
DB_PATH = os.getenv("DB_PATH", "casino_stats.sqlite3")
WEBHOOK_BASE = os.getenv("WEBHOOK_BASE")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH")
PORT = int(os.getenv("PORT", "8080"))

# ---- mapping 1..64 -> (bar/grape/lemon/seven) ----
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
   41: ("bar","lemon","lemon"),42: ("grape","lemon","леmon"),43: ("lemon","lemon","lemon"),44: ("seven","lemon","lemon"),
   45: ("bar","seven","lemon"),46: ("grape","seven","lemon"),47: ("lemon","seven","lemon"),48: ("seven","seven","lemon"),
   49: ("bar","bar","seven"),50: ("grape","bar","seven"),51: ("lemon","bar","seven"),52: ("seven","bar","seven"),
   53: ("bar","grape","seven"),54: ("grape","grape","seven"),55: ("lemon","grape","seven"),56: ("seven","grape","seven"),
   57: ("bar","lemon","seven"),58: ("grape","lemon","seven"),59: ("lemon","lemon","seven"),60: ("seven","lemon","seven"),
   61: ("bar","seven","seven"),62: ("grape","seven","seven"),63: ("lemon","seven","seven"),64: ("seven","seven","seven"),
}
EMOJI = {"bar":"BAR", "grape":"🍇", "lemon":"🍋", "seven":"7️⃣"}

_conn = None
def conn():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.execute("""CREATE TABLE IF NOT EXISTS results(
            chat_id INTEGER, user_id INTEGER, username TEXT,
            combo TEXT, count INTEGER DEFAULT 0,
            PRIMARY KEY(chat_id,user_id,combo))""")
        _conn.execute("""CREATE TABLE IF NOT EXISTS totals(
            chat_id INTEGER, user_id INTEGER, spins INTEGER DEFAULT 0,
            PRIMARY KEY(chat_id,user_id))""")
        _conn.commit()
    return _conn

def upsert(chat_id:int, user_id:int, username:str, combo:str):
    c = conn()
    with c:
        c.execute("""INSERT INTO results(chat_id,user_id,username,combo,count)
                     VALUES(?,?,?,?,1)
                     ON CONFLICT(chat_id,user_id,combo) DO UPDATE SET
                     count = count + 1, username = excluded.username""",
                  (chat_id,user_id,username,combo))
        c.execute("""INSERT INTO totals(chat_id,user_id,spins) VALUES(?,?,1)
                     ON CONFLICT(chat_id,user_id) DO UPDATE SET spins = spins + 1""",
                  (chat_id,user_id))

def get_user(chat_id:int, user_id:int):
    c = conn()
    rows = c.execute("""SELECT combo,count FROM results
                        WHERE chat_id=? AND user_id=?
                        ORDER BY count DESC""",(chat_id,user_id)).fetchall()
    t = c.execute("""SELECT spins FROM totals WHERE chat_id=? AND user_id=?""",
                  (chat_id,user_id)).fetchone()
    return rows, (t[0] if t else 0)

def get_leaderboard(chat_id:int, combos:Tuple[str,...]):
    c = conn()
    q = ",".join("?"*len(combos))
    return c.execute(f"""SELECT username, combo, SUM(count) c
                         FROM results
                         WHERE chat_id=? AND combo IN ({q})
                         GROUP BY username, combo
                         ORDER BY combo, c DESC""", (chat_id, *combos)).fetchall()

async def on_dice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = update.effective_message
    d = getattr(m, "dice", None)
    if not d or d.emoji != "🎰": return
    if m.forward_date: return  # игнор пересылок (анти-чит)
    value = int(d.value)
    combo = slot_value.get(value)
    if not combo: return
    combo_key = "|".join(combo)
    user = update.effective_user
    username = user.full_name or (user.username and f"@{user.username}") or str(user.id)
    upsert(update.effective_chat.id, user.id, username, combo_key)
    pretty = " ".join(EMOJI[x] for x in combo)
    await m.reply_text(f"Counted for {username}: {pretty}")

async def cmd_mystats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, user_id = update.effective_chat.id, update.effective_user.id
    rows, total = get_user(chat_id, user_id)
    if not rows:
        await update.message.reply_text("No data yet. Send 🎰 and come back.")
        return
    lines = [f"{' '.join(EMOJI[x] for x in combo.split('|'))} — {cnt}" for combo,cnt in rows[:15]]
    await update.message.reply_text("Your top combos:\n" + "\n".join(lines) + f"\n\nTotal spins: {total}")

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    triples = ("seven|seven|seven","grape|grape|grape","lemon|lemon|lemon","bar|bar|bar")
    board = get_leaderboard(chat_id, triples)
    if not board:
        await update.message.reply_text("No data in this chat yet. Spin 🎰!")
        return
    by = {c:[] for c in triples}
    for username, combo, c in board: by[combo].append(f"{username} — {c}")
    def pc(k): return " ".join(EMOJI[x] for x in k.split("|"))
    text = "Leaders (triple matches):\n\n" + "\n\n".join(
        f"{pc(k)}:\n" + "\n".join(v[:5]) if v else f"{pc(k)}: —" for k,v in by.items()
    )
    await update.message.reply_text(text)

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Commands:\n/mystats — your stats\n/stats — leaders\n/help — this help\n"
        "Just send 🎰 in the chat — I’ll count it."
    )

def webhook_path(token: str)->str:
    return "/telegram/" + hashlib.sha256(token.encode()).hexdigest()[:16]

def app_build():
    if not TOKEN: raise SystemExit("Set TG_TOKEN")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.Dice, on_dice))
    app.add_handler(CommandHandler("mystats", cmd_mystats))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("help", cmd_help))
    return app

if __name__ == "__main__":
    application = app_build()
    if WEBHOOK_BASE:
        path = WEBHOOK_PATH or webhook_path(TOKEN)
        url = WEBHOOK_BASE.rstrip("/") + path
        logging.info("Starting webhook at %s", url)
        application.run_webhook(
            listen="0.0.0.0", port=PORT, url_path=path, webhook_url=url, drop_pending_updates=True
        )
    else:
        logging.info("Starting polling (no WEBHOOK_BASE set)")
        application.run_polling(drop_pending_updates=True)
