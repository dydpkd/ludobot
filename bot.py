#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ludooman Bot — Telegram slot 🎰 tracker
- Listens to 🎰 dice in groups
- Maps value (1..64) to reel symbols
- Stores per-user stats in SQLite
- Commands: /mystats, /stats, /help
Deploy:
- Polling (local) if WEBHOOK_BASE is not set
- Webhook (PaaS) if WEBHOOK_BASE is set
Env:
  TG_TOKEN       - BotFather token (required)
  DB_PATH        - SQLite file path (default: ./casino_stats.sqlite3)
  WEBHOOK_BASE   - Public HTTPS base URL for webhook, e.g. https://your-app.onrender.com
  WEBHOOK_PATH   - Optional fixed webhook path (default: /telegram/<short-hash>)
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
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH")  # optional
PORT = int(os.getenv("PORT", "8080"))

# ---- mapping of 1..64 to slot symbols (BAR, 🍇, 🍋, 7️⃣) ----
slot_value = {
    1: ("bar","bar","bar"), 2: ("grape","bar","bar"), 3: ("lemon","bar","bar"), 4: ("seven","bar","bar"),
    5: ("bar","grape","bar"), 6: ("grape","grape","bar"), 7: ("lemon","grape","bar"), 8: ("seven","grape","bar"),
    9: ("bar","lemon","bar"),10: ("grape","lemon","bar"),11: ("lemon","lemon","bar"),12: ("seven","lemon","bar"),
   13: ("bar","seven","bar"),14: ("grape","seven","bar"),15: ("lemon","seven","bar"),16: ("seven","seven","bar"),
   17: ("bar","bar","grape"),18: ("grape","бар","grape"),19: ("lemon","bar","grape"),20: ("seven","bar","grape"),
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
   61: ("bar","seven","seven"),62: ("grape","seven","seven"),63: ("lemon","seven","seven"),
