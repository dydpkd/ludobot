#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ludooman Bot — Telegram slot 🎰 tracker
- Silent count of 🎰 spins in groups
- SQLite stats (persistent with Railway Volume)
- Commands: /mystats, /stats, /help

ENV:
  TG_TOKEN       - required
  DB_PATH        - default ./casino_stats.sqlite3 (use /data/... with Railway Volume)
  WEBHOOK_BASE   - enable webhook (https://YOUR.up.railway.app)
  WEBHOOK_PATH   - optional fixed webhook path
"""
import os, sqlite3, logging, hashlib
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

        _conn.execute("""
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
        INSERT INTO totals(chat_id,user_id,spins) VALUES(?,?,1)
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

# ---- Handlers ----
async def on_dice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = update.effective_message
    d = getattr(m, "dice", None)
    if not d or d.emoji != "🎰":
        return
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
    # silent — no reply per spin

async def cmd_mystats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    rows, total = fetch_user_stats(chat_id, user.id)
    if not rows:
        await update.message.reply_text("No data yet. Send 🎰 and come back.")
        return
    lines = []
    for combo, cnt in rows[:15]:
        pretty = " ".join(EMOJI[x] for x in combo.split("|"))
        lines.append(f"{pretty} — {cnt}")
    name = user.full_name or (user.username and f"@{user.username}") or str(user.id)
    await update.message.reply_text(f"Top combos — {name}:\n" + "\n".join(lines) + f"\n\nTotal spins: {total}")

def _compact_combo(key: str) -> str:
    # "seven|seven|seven" -> "7️⃣7️⃣7️⃣"  (без пробелов)
    return "".join(EMOJI[x] for x in key.split("|"))

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    triples = ("seven|seven|seven","grape|grape|grape","lemon|lemon|lemon","bar|bar|bar")
    board = fetch_leaderboard(chat_id, triples)
    if not board:
        await update.message.reply_text("No data in this chat yet. Spin 🎰!")
        return

    # агрегируем сумму тройных по людям
    totals_by_user = {}
    for username, combo, c in board:
        totals_by_user[username] = totals_by_user.get(username, 0) + c
    total_triples = sum(totals_by_user.values())
    top_users = sorted(totals_by_user.items(), key=lambda kv: kv[1], reverse=True)

    # блоки по комбо (оставляем прежнее ограничение top-5 на каждую комбинацию)
    by = {c:[] for c in triples}
    for username, combo, c in board:
        by[combo].append(f"{username} — {c}")

    # строим текст по макету, с жирными заголовками
    lines = []
    lines.append(f"<b>Total Jackpot:</b> {total_triples}")
    lines.append("")  # пустая строка

    lines.append("<b>Users Total Jackpot:</b>")
    lines.append("")  # пустая строка
    if top_users:
        lines.extend(f"{u} — {n}" for u, n in top_users[:10])
    else:
        lines.append("—")

    lines.append("")  # пустая строка
    lines.append("<b>Total Combination Jackpot:</b>")
    lines.append("")  # пустая строка

    for k in triples:
        header = f"{_compact_combo(k)}:"
        vals = by.get(k) or []
        if vals:
            # top-5 как раньше
            block = [header] + vals[:5]
        else:
            block = [header, "—"]
        lines.extend(block)
        lines.append("")  # пустая строка между комбо-блоками

    # уберём последний лишний перенос
    while lines and lines[-1] == "":
        lines.pop()

    text = "\n".join(lines)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Commands:\n"
        "/mystats — your stats\n"
        "/stats — leaders by triple matches (with totals)\n"
        "/help — this help\n\n"
        "Send 🎰 in the chat — I count it silently."
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
