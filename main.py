import logging
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

# ============================================================
BOT_TOKEN = "8846798377:AAG9FJNmKDcf3zoQvIOWLSth6tkxEVaMqBs"
BOT_USERNAME = "predictor_bot"
ADMIN_IDS = [6896407205]
SUPPORT_USERNAME = "Predictorisdope"

CHANNELS = [
    {"name": "🔥 Main Channel",       "username": None,                 "invite_link": "https://t.me/+geNHq7jKIiAyYjJl", "id": -1001813666985},
    {"name": "📈 Trade With Sniper",  "username": "snipertradingshort", "invite_link": None,                              "id": -1003750001776},
    {"name": "💎 Premium Group",      "username": None,                 "invite_link": "https://t.me/+i1aDUi_W8bE3ZTVl",  "id": -1003765229156},
    {"name": "💬 Discussions On Top", "username": "disscussionbfx",     "invite_link": None,                              "id": -1003999268364},
]

CREDITS_NEW_USER    = 7
CREDITS_PER_REFER   = 4
# ============================================================

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# DATABASE
# ──────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id       INTEGER PRIMARY KEY,
            username      TEXT,
            first_name    TEXT,
            joined_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            verified      INTEGER DEFAULT 0,
            credits       INTEGER DEFAULT 0,
            total_refers  INTEGER DEFAULT 0,
            referred_by   INTEGER DEFAULT NULL,
            is_banned     INTEGER DEFAULT 0,
            total_predictions INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect("bot_users.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def save_user(user, referred_by=None):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    existing = conn.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,)).fetchone()
    if not existing:
        c.execute("""INSERT INTO users (user_id, username, first_name, credits, referred_by)
                     VALUES (?, ?, ?, ?, ?)""",
                  (user.id, user.username, user.first_name, CREDITS_NEW_USER, referred_by))
        if referred_by:
            c.execute("UPDATE users SET credits=credits+?, total_refers=total_refers+1 WHERE user_id=?",
                      (CREDITS_PER_REFER, referred_by))
    else:
        c.execute("UPDATE users SET username=?, first_name=? WHERE user_id=?",
                  (user.username, user.first_name, user.id))
    conn.commit()
    conn.close()
    return not existing

def set_verified(user_id):
    conn = sqlite3.connect("bot_users.db")
    conn.execute("UPDATE users SET verified=1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def get_credits(user_id):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("SELECT credits FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def deduct_credit(user_id):
    conn = sqlite3.connect("bot_users.db")
    conn.execute("UPDATE users SET credits=credits-1, total_predictions=total_predictions+1 WHERE user_id=? AND credits>0", (user_id,))
    conn.commit()
    conn.close()

def add_credits(user_id, amount):
    conn = sqlite3.connect("bot_users.db")
    conn.execute("UPDATE users SET credits=credits+? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()

def remove_credits(user_id, amount):
    conn = sqlite3.connect("bot_users.db")
    conn.execute("UPDATE users SET credits=MAX(0, credits-?) WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()

def set_credits(user_id, amount):
    conn = sqlite3.connect("bot_users.db")
    conn.execute("UPDATE users SET credits=? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()

def ban_user(user_id):
    conn = sqlite3.connect("bot_users.db")
    conn.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def unban_user(user_id):
    conn = sqlite3.connect("bot_users.db")
    conn.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def is_banned(user_id):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("SELECT is_banned FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return bool(row[0]) if row else False

def get_all_users():
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE is_banned=0")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_stats():
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE is_banned=1")
    banned = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE verified=1")
    verified = c.fetchone()[0]
    c.execute("SELECT SUM(total_predictions) FROM users")
    preds = c.fetchone()[0] or 0
    c.execute("SELECT SUM(credits) FROM users")
    total_credits = c.fetchone()[0] or 0
    conn.close()
    return {"total": total, "banned": banned, "verified": verified, "predictions": preds, "total_credits": total_credits}

# ──────────────────────────────────────────────
# PREDICTION ALGORITHM
# ──────────────────────────────────────────────
def predict_wingo(digits: str) -> dict:
    if len(digits) != 3 or not digits.isdigit():
        return {"error": True}
    d = [int(x) for x in digits]
    num = int(digits)
    digit_sum   = sum(d)
    digit_range = max(d) - min(d)
    even_count  = sum(1 for x in d if x % 2 == 0)
    big_score = 0; small_score = 0

    if digit_sum >= 13:      big_score += 2
    elif digit_sum <= 11:    small_score += 2
    else:                    big_score += 1

    if num % 3 == 0 or num % 7 == 0:  big_score += 2
    else:                               small_score += 2

    if even_count >= 2:  big_score += 1
    else:                small_score += 1

    if digit_range >= 5: big_score += 1
    else:                small_score += 1

    if d[2] >= 5:        big_score += 1
    else:                small_score += 1

    total = big_score + small_score
    if big_score > small_score:
        result = "BIG"; confidence = round((big_score / total) * 100); emoji = "🔴"
    else:
        result = "SMALL"; confidence = round((small_score / total) * 100); emoji = "🟢"

    if confidence >= 80:    strength = "🔥 VERY STRONG"
    elif confidence >= 65:  strength = "⚡ STRONG"
    elif confidence >= 55:  strength = "✅ MODERATE"
    else:                   strength = "⚠️ WEAK"

    return {"error": False, "result": result, "confidence": confidence,
            "emoji": emoji, "strength": strength, "digit_sum": digit_sum,
            "big_score": big_score, "small_score": small_score}

# ──────────────────────────────────────────────
# KEYBOARDS
# ──────────────────────────────────────────────
async def check_all_channels(user_id, bot):
    not_joined = []
    for ch in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=ch["id"], user_id=user_id)
            if member.status in ["left", "kicked", "banned"]:
                not_joined.append(ch)
        except Exception:
            not_joined.append(ch)
    return not_joined

def join_channels_keyboard():
    buttons = []
    for ch in CHANNELS:
        link = ch["invite_link"] if ch.get("invite_link") else f"https://t.me/{ch['username']}"
        buttons.append([InlineKeyboardButton(f"📢 {ch['name']}", url=link)])
    buttons.append([InlineKeyboardButton("✅ Verify Now", callback_data="verify")])
    return InlineKeyboardMarkup(buttons)

def main_keyboard(credits):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🎯 Get Prediction  |  🎟️ {credits} Credits", callback_data="predict")],
        [InlineKeyboardButton("👥 Refer & Earn Credits", callback_data="refer")],
        [InlineKeyboardButton("📊 My Stats", callback_data="stats")],
        [InlineKeyboardButton("💬 Loss Recovery Help", url=f"https://t.me/{SUPPORT_USERNAME}")],
    ])

def admin_panel_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Bot Stats",        callback_data="adm_stats")],
        [InlineKeyboardButton("➕ Add Credits",      callback_data="adm_addcr"),
         InlineKeyboardButton("➖ Remove Credits",   callback_data="adm_remcr")],
        [InlineKeyboardButton("🎯 Set Credits",      callback_data="adm_setcr")],
        [InlineKeyboardButton("🚫 Ban User",         callback_data="adm_ban"),
         InlineKeyboardButton("✅ Unban User",       callback_data="adm_unban")],
        [InlineKeyboardButton("👤 User Info",        callback_data="adm_userinfo")],
        [InlineKeyboardButton("📢 Broadcast",        callback_data="adm_broadcast")],
        [InlineKeyboardButton("🔙 Close",            callback_data="adm_close")],
    ])

def refer_keyboard(user_id):
    bot_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Share My Refer Link",
         url=f"https://t.me/share/url?url={bot_link}&text=🎯 Wingo 30 Predictor - FREE predictions! Join now!")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_main")],
    ])

def no_credits_keyboard(user_id):
    bot_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Refer & Get 4 Credits",
         url=f"https://t.me/share/url?url={bot_link}&text=🎯 Wingo 30 Predictor - FREE predictions!")],
        [InlineKeyboardButton("💬 Loss Recovery Help", url=f"https://t.me/{SUPPORT_USERNAME}")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")],
    ])

# ──────────────────────────────────────────────
# HANDLERS
# ──────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_banned(user.id):
        await update.message.reply_text("🚫 You are banned from using this bot.")
        return

    args = context.args
    referred_by = int(args[0]) if args and args[0].isdigit() and int(args[0]) != user.id else None
    is_new = save_user(user, referred_by)
    credits = get_credits(user.id)

    not_joined = await check_all_channels(user.id, context.bot)
    if not_joined:
        await update.message.reply_text(
            f"👋 Welcome <b>{user.first_name}</b>!\n\n"
            "🔒 <b>Bot Access Locked</b>\n\n"
            "Pehle sabhi channels join karo:\n\n"
            "⬇️ Join karo phir <b>✅ Verify Now</b> dabao!",
            parse_mode="HTML", reply_markup=join_channels_keyboard()
        )
        return

    set_verified(user.id)

    if is_new:
        text = (
            f"🎉 <b>Welcome {user.first_name}!</b>\n\n"
            f"{'🎁 <b>Referred!</b> Bonus applied!\n\n' if referred_by else ''}"
            f"╔══════════════════════╗\n"
            f"║   🎟️ CREDITS CREDITED  ║\n"
            f"╚══════════════════════╝\n\n"
            f"  🎯 Base Credits:    <b>5</b>\n"
            f"  🎁 Welcome Bonus:  <b>+2</b>\n"
            f"  ━━━━━━━━━━━━━━━\n"
            f"  💎 Total:          <b>7 Credits</b>\n\n"
            f"Refer karo aur aur credits kamao!\n"
            f"👇 Kya karna hai?"
        )
    else:
        text = (
            f"✅ <b>Welcome back {user.first_name}!</b>\n\n"
            f"🎟️ Credits: <b>{credits}</b>\n\n"
            f"👇 Kya karna hai?"
        )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=main_keyboard(credits))


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Access Denied!")
        return
    await update.message.reply_text(
        "👑 <b>ADMIN PANEL</b>\n\n"
        "Select an option below:",
        parse_mode="HTML",
        reply_markup=admin_panel_keyboard()
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    await query.answer()
    data = query.data

    # ════════════════════════════════
    # ADMIN PANEL BUTTONS
    # ════════════════════════════════
    if data.startswith("adm_") and user.id in ADMIN_IDS:

        if data == "adm_close":
            await query.edit_message_text("✅ Admin panel closed.")
            return

        if data == "adm_stats":
            s = get_stats()
            await query.edit_message_text(
                f"📊 <b>BOT STATISTICS</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"👥 Total Users:       <b>{s['total']}</b>\n"
                f"✅ Verified Users:    <b>{s['verified']}</b>\n"
                f"🚫 Banned Users:     <b>{s['banned']}</b>\n"
                f"🎯 Total Predictions: <b>{s['predictions']}</b>\n"
                f"🎟️ Total Credits:     <b>{s['total_credits']}</b>\n\n"
                f"━━━━━━━━━━━━━━━━━━━━",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="adm_back")]])
            )

        elif data == "adm_addcr":
            context.user_data["admin_action"] = "add_credits"
            await query.edit_message_text(
                "➕ <b>Add Credits</b>\n\n"
                "Format: <code>USER_ID AMOUNT</code>\n"
                "Example: <code>123456789 50</code>",
                parse_mode="HTML"
            )

        elif data == "adm_remcr":
            context.user_data["admin_action"] = "remove_credits"
            await query.edit_message_text(
                "➖ <b>Remove Credits</b>\n\n"
                "Format: <code>USER_ID AMOUNT</code>\n"
                "Example: <code>123456789 10</code>",
                parse_mode="HTML"
            )

        elif data == "adm_setcr":
            context.user_data["admin_action"] = "set_credits"
            await query.edit_message_text(
                "🎯 <b>Set Credits</b>\n\n"
                "Format: <code>USER_ID AMOUNT</code>\n"
                "Example: <code>123456789 100</code>",
                parse_mode="HTML"
            )

        elif data == "adm_ban":
            context.user_data["admin_action"] = "ban"
            await query.edit_message_text(
                "🚫 <b>Ban User</b>\n\n"
                "User ka ID bhejo:\n"
                "Example: <code>123456789</code>",
                parse_mode="HTML"
            )

        elif data == "adm_unban":
            context.user_data["admin_action"] = "unban"
            await query.edit_message_text(
                "✅ <b>Unban User</b>\n\n"
                "User ka ID bhejo:\n"
                "Example: <code>123456789</code>",
                parse_mode="HTML"
            )

        elif data == "adm_userinfo":
            context.user_data["admin_action"] = "userinfo"
            await query.edit_message_text(
                "👤 <b>User Info</b>\n\n"
                "User ka ID bhejo:\n"
                "Example: <code>123456789</code>",
                parse_mode="HTML"
            )

        elif data == "adm_broadcast":
            context.user_data["admin_action"] = "broadcast"
            await query.edit_message_text(
                "📢 <b>Broadcast Message</b>\n\n"
                "Jo message bhejni hai woh type karo\n"
                "(HTML formatting supported):",
                parse_mode="HTML"
            )

        elif data == "adm_back":
            await query.edit_message_text(
                "👑 <b>ADMIN PANEL</b>\n\nSelect an option:",
                parse_mode="HTML",
                reply_markup=admin_panel_keyboard()
            )
        return

    # ════════════════════════════════
    # USER BUTTONS
    # ════════════════════════════════
    if is_banned(user.id):
        await query.edit_message_text("🚫 You are banned.")
        return

    if data == "verify":
        not_joined = await check_all_channels(user.id, context.bot)
        if not_joined:
            names = "\n".join([f"❌ {ch['name']}" for ch in not_joined])
            await query.edit_message_text(
                f"⚠️ <b>Abhi bhi join nahi kiya:</b>\n\n{names}\n\nSabhi join karo phir verify karo! 👆",
                parse_mode="HTML", reply_markup=join_channels_keyboard()
            )
        else:
            set_verified(user.id)
            credits = get_credits(user.id)
            await query.edit_message_text(
                f"🎉 <b>Verified! Welcome {user.first_name}!</b>\n\n"
                f"🎟️ Credits: <b>{credits}</b>\n\n👇 Kya karna hai?",
                parse_mode="HTML", reply_markup=main_keyboard(credits)
            )

    elif data == "predict":
        not_joined = await check_all_channels(user.id, context.bot)
        if not_joined:
            await query.edit_message_text("🔒 Pehle channels join karo!", reply_markup=join_channels_keyboard())
            return
        credits = get_credits(user.id)
        if credits <= 0:
            await query.edit_message_text(
                "😔 <b>Credits Khatam Ho Gaye!</b>\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "🔗 <b>Refer karo → 4 FREE credits pao!</b>\n\n"
                "Apna refer link share karo:\n"
                "Jab woh join kare → tumhe 4 credits!\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"💬 Personal loss recovery:\nDM @{SUPPORT_USERNAME}",
                parse_mode="HTML", reply_markup=no_credits_keyboard(user.id)
            )
            return
        context.user_data["waiting_for_digits"] = True
        await query.edit_message_text(
            f"🎯 <b>WINGO 30 PREDICTOR</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎟️ Credits: <b>{credits}</b>\n\n"
            f"📝 <b>Last 3 digits enter karo:</b>\n"
            f"Example: <code>456</code>\n\n"
            f"⬇️ Type karo:",
            parse_mode="HTML"
        )

    elif data == "refer":
        credits = get_credits(user.id)
        u = get_user(user.id)
        refers = u["total_refers"] if u else 0
        bot_link = f"https://t.me/{BOT_USERNAME}?start={user.id}"
        await query.edit_message_text(
            f"👥 <b>Refer & Earn Program</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎟️ Tumhare Credits: <b>{credits}</b>\n"
            f"👥 Total Refers:    <b>{refers}</b>\n"
            f"💰 Credits Earned:  <b>{refers * CREDITS_PER_REFER}</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎁 <b>Har refer pe → 4 Credits!</b>\n\n"
            f"🔗 Tera Refer Link:\n"
            f"<code>{bot_link}</code>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📤 Share karo aur credits kamao!",
            parse_mode="HTML", reply_markup=refer_keyboard(user.id)
        )

    elif data == "stats":
        u = get_user(user.id)
        credits = u["credits"] if u else 0
        refers = u["total_refers"] if u else 0
        preds = u["total_predictions"] if u else 0
        await query.edit_message_text(
            f"📊 <b>Teri Stats</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 Name:              <b>{user.first_name}</b>\n"
            f"🎟️ Credits:           <b>{credits}</b>\n"
            f"🎯 Total Predictions: <b>{preds}</b>\n"
            f"👥 Total Refers:      <b>{refers}</b>\n"
            f"💰 Credits Earned:    <b>{refers * CREDITS_PER_REFER}</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💬 Loss recovery help:\nDM @{SUPPORT_USERNAME}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👥 Refer & Earn", callback_data="refer")],
                [InlineKeyboardButton("🔙 Back", callback_data="back_main")],
            ])
        )

    elif data == "back_main":
        credits = get_credits(user.id)
        await query.edit_message_text(
            f"🎯 <b>Wingo 30 Predictor</b>\n\n"
            f"🎟️ Credits: <b>{credits}</b>\n\n"
            f"👇 Kya karna hai?",
            parse_mode="HTML", reply_markup=main_keyboard(credits)
        )


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()

    if is_banned(user.id):
        await update.message.reply_text("🚫 You are banned from this bot.")
        return

    # ── ADMIN ACTIONS ──
    if user.id in ADMIN_IDS:
        action = context.user_data.get("admin_action")

        if action == "broadcast":
            users = get_all_users()
            sent, failed = 0, 0
            for uid in users:
                try:
                    await context.bot.send_message(uid, text, parse_mode="HTML")
                    sent += 1
                except Exception:
                    failed += 1
            context.user_data.pop("admin_action", None)
            await update.message.reply_text(
                f"📢 <b>Broadcast Done!</b>\n\n✅ Sent: <b>{sent}</b>\n❌ Failed: <b>{failed}</b>",
                parse_mode="HTML", reply_markup=admin_panel_keyboard()
            )
            return

        if action in ["add_credits", "remove_credits", "set_credits"]:
            parts = text.split()
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                uid, amt = int(parts[0]), int(parts[1])
                target = get_user(uid)
                if not target:
                    await update.message.reply_text("❌ User not found!")
                    context.user_data.pop("admin_action", None)
                    return
                if action == "add_credits":
                    add_credits(uid, amt)
                    msg = f"➕ Added <b>{amt}</b> credits to user <b>{uid}</b>"
                elif action == "remove_credits":
                    remove_credits(uid, amt)
                    msg = f"➖ Removed <b>{amt}</b> credits from user <b>{uid}</b>"
                else:
                    set_credits(uid, amt)
                    msg = f"🎯 Set credits to <b>{amt}</b> for user <b>{uid}</b>"
                new_cr = get_credits(uid)
                context.user_data.pop("admin_action", None)
                await update.message.reply_text(
                    f"✅ {msg}\n🎟️ New Balance: <b>{new_cr}</b>",
                    parse_mode="HTML", reply_markup=admin_panel_keyboard()
                )
                # Notify user
                try:
                    await context.bot.send_message(uid,
                        f"🎟️ <b>Credits Update!</b>\n\n{msg}\n💎 Balance: <b>{new_cr}</b>",
                        parse_mode="HTML")
                except Exception:
                    pass
            else:
                await update.message.reply_text("⚠️ Format: <code>USER_ID AMOUNT</code>", parse_mode="HTML")
            return

        if action == "ban":
            if text.isdigit():
                uid = int(text)
                ban_user(uid)
                context.user_data.pop("admin_action", None)
                await update.message.reply_text(
                    f"🚫 User <b>{uid}</b> banned!",
                    parse_mode="HTML", reply_markup=admin_panel_keyboard()
                )
                try:
                    await context.bot.send_message(uid, "🚫 You have been banned from this bot.")
                except Exception:
                    pass
            else:
                await update.message.reply_text("⚠️ Sirf User ID bhejo.")
            return

        if action == "unban":
            if text.isdigit():
                uid = int(text)
                unban_user(uid)
                context.user_data.pop("admin_action", None)
                await update.message.reply_text(
                    f"✅ User <b>{uid}</b> unbanned!",
                    parse_mode="HTML", reply_markup=admin_panel_keyboard()
                )
                try:
                    await context.bot.send_message(uid, "✅ You have been unbanned! Use /start to continue.")
                except Exception:
                    pass
            else:
                await update.message.reply_text("⚠️ Sirf User ID bhejo.")
            return

        if action == "userinfo":
            if text.isdigit():
                uid = int(text)
                u = get_user(uid)
                context.user_data.pop("admin_action", None)
                if not u:
                    await update.message.reply_text("❌ User not found!", reply_markup=admin_panel_keyboard())
                else:
                    await update.message.reply_text(
                        f"👤 <b>User Info</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"🆔 ID:          <code>{u['user_id']}</code>\n"
                        f"👤 Name:        <b>{u['first_name']}</b>\n"
                        f"📛 Username:    @{u['username'] or 'N/A'}\n"
                        f"🎟️ Credits:     <b>{u['credits']}</b>\n"
                        f"🎯 Predictions: <b>{u['total_predictions']}</b>\n"
                        f"👥 Refers:      <b>{u['total_refers']}</b>\n"
                        f"✅ Verified:    <b>{'Yes' if u['verified'] else 'No'}</b>\n"
                        f"🚫 Banned:      <b>{'Yes' if u['is_banned'] else 'No'}</b>\n"
                        f"📅 Joined:      <b>{u['joined_at']}</b>",
                        parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("➕ Add Credits", callback_data="adm_addcr"),
                             InlineKeyboardButton("🚫 Ban", callback_data="adm_ban")],
                            [InlineKeyboardButton("🔙 Back", callback_data="adm_back")]
                        ])
                    )
            else:
                await update.message.reply_text("⚠️ Sirf User ID bhejo.")
            return

    # ── PREDICTION FLOW ──
    if context.user_data.get("waiting_for_digits"):
        not_joined = await check_all_channels(user.id, context.bot)
        if not_joined:
            context.user_data["waiting_for_digits"] = False
            await update.message.reply_text("🔒 Pehle channels join karo!", reply_markup=join_channels_keyboard())
            return

        credits = get_credits(user.id)
        if credits <= 0:
            context.user_data["waiting_for_digits"] = False
            await update.message.reply_text(
                "😔 <b>Credits khatam!</b>\n\nRefer karo aur 4 credits pao!",
                parse_mode="HTML", reply_markup=no_credits_keyboard(user.id)
            )
            return

        digits = text.replace(" ", "")
        result = predict_wingo(digits)

        if result.get("error"):
            await update.message.reply_text(
                "⚠️ <b>Invalid!</b>\n\nSirf 3 digits enter karo.\nExample: <code>456</code>",
                parse_mode="HTML"
            )
            return

        context.user_data["waiting_for_digits"] = False
        deduct_credit(user.id)
        new_credits = get_credits(user.id)

        conf = result["confidence"]
        filled = int(conf / 10)
        bar = "█" * filled + "░" * (10 - filled)

        if result["result"] == "BIG":
            big_bar = "🟥" * filled + "⬛" * (10 - filled)
            sml_bar = "⬛" * 10
        else:
            big_bar = "⬛" * 10
            sml_bar = "🟩" * filled + "⬛" * (10 - filled)

        response = (
            f"╔══════════════════════╗\n"
            f"║  🎯 WINGO 30 RESULT  ║\n"
            f"╚══════════════════════╝\n\n"
            f"📥 Input: <code>{digits}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"  🔴 BIG   {big_bar}\n"
            f"  🟢 SMALL {sml_bar}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔮 Prediction: <b>{result['emoji']} {result['result']}</b>\n"
            f"📊 Confidence: <b>{conf}%</b>  {result['strength']}\n"
            f"[{bar}]\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔢 Digit Sum:    <b>{result['digit_sum']}</b>\n"
            f"📈 BIG Score:    <b>{result['big_score']}/8</b>\n"
            f"📉 SMALL Score:  <b>{result['small_score']}/8</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎟️ Credits Left: <b>{new_credits}</b>"
            + (f"\n⚠️ <i>Credits kam hain! Refer karo</i>" if new_credits <= 1 else "")
            + f"\n━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ <i>Sirf entertainment ke liye</i>\n"
            f"💬 Loss recovery: @{SUPPORT_USERNAME}"
        )

        kb = [[InlineKeyboardButton("🔄 Predict Again", callback_data="predict")]]
        if new_credits <= 1:
            kb.append([InlineKeyboardButton("👥 Refer & Get 4 Credits", callback_data="refer")])
        kb.append([InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")])

        await update.message.reply_text(response, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
    else:
        credits = get_credits(user.id)
        not_joined = await check_all_channels(user.id, context.bot)
        if not_joined:
            await update.message.reply_text("🔒 Pehle channels join karo!", reply_markup=join_channels_keyboard())
        else:
            await update.message.reply_text("👇 Menu:", reply_markup=main_keyboard(credits))


def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    logger.info("✅ Bot started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
