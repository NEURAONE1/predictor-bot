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

CREDITS_NEW_USER    = 7   # 5 + 2 bonus
CREDITS_PER_REFER   = 4
CREDITS_PER_PREDICT = 1
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
            user_id     INTEGER PRIMARY KEY,
            username    TEXT,
            first_name  TEXT,
            joined_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            verified    INTEGER DEFAULT 0,
            credits     INTEGER DEFAULT 0,
            total_refers INTEGER DEFAULT 0,
            referred_by INTEGER DEFAULT NULL
        )
    """)
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def save_user(user, referred_by=None):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    existing = conn.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,)).fetchone()
    if not existing:
        c.execute("""
            INSERT INTO users (user_id, username, first_name, credits, referred_by)
            VALUES (?, ?, ?, ?, ?)
        """, (user.id, user.username, user.first_name, CREDITS_NEW_USER, referred_by))
        # Give referrer credits
        if referred_by:
            c.execute("UPDATE users SET credits=credits+?, total_refers=total_refers+1 WHERE user_id=?",
                      (CREDITS_PER_REFER, referred_by))
    conn.commit()
    conn.close()
    return not existing  # True if new user

def set_verified(user_id):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("UPDATE users SET verified=1 WHERE user_id=?", (user_id,))
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
    c = conn.cursor()
    c.execute("UPDATE users SET credits=credits-1 WHERE user_id=? AND credits>0", (user_id,))
    conn.commit()
    conn.close()

def get_total_users():
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    count = c.fetchone()[0]
    conn.close()
    return count

def get_all_users():
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_refers(user_id):
    conn = sqlite3.connect("bot_users.db")
    c = conn.cursor()
    c.execute("SELECT total_refers FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

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

    big_score = 0
    small_score = 0

    if digit_sum >= 13:      big_score += 2
    elif digit_sum <= 11:    small_score += 2
    else:                    big_score += 1

    if num % 3 == 0 or num % 7 == 0:  big_score += 2
    else:                               small_score += 2

    if even_count >= 2:      big_score += 1
    else:                    small_score += 1

    if digit_range >= 5:     big_score += 1
    else:                    small_score += 1

    if d[2] >= 5:            big_score += 1
    else:                    small_score += 1

    total = big_score + small_score
    if big_score > small_score:
        result = "BIG"
        confidence = round((big_score / total) * 100)
        emoji = "🔴"
    else:
        result = "SMALL"
        confidence = round((small_score / total) * 100)
        emoji = "🟢"

    # Strength level
    if confidence >= 80:    strength = "🔥 VERY STRONG"
    elif confidence >= 65:  strength = "⚡ STRONG"
    elif confidence >= 55:  strength = "✅ MODERATE"
    else:                   strength = "⚠️ WEAK"

    return {
        "error": False,
        "result": result,
        "confidence": confidence,
        "emoji": emoji,
        "strength": strength,
        "digit_sum": digit_sum,
        "big_score": big_score,
        "small_score": small_score,
    }

# ──────────────────────────────────────────────
# CHANNEL CHECK
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

def refer_keyboard(user_id):
    bot_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Share My Refer Link", url=f"https://t.me/share/url?url={bot_link}&text=🎯 Wingo 30 Predictor Bot - Get FREE predictions! Join now!")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_main")],
    ])

def no_credits_keyboard(user_id):
    bot_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Share & Get 4 Credits", url=f"https://t.me/share/url?url={bot_link}&text=🎯 Wingo 30 Predictor Bot - Get FREE predictions!")],
        [InlineKeyboardButton("💬 Loss Recovery Help", url=f"https://t.me/{SUPPORT_USERNAME}")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")],
    ])

# ──────────────────────────────────────────────
# HANDLERS
# ──────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    referred_by = int(args[0]) if args and args[0].isdigit() and int(args[0]) != user.id else None

    is_new = save_user(user, referred_by)
    credits = get_credits(user.id)

    not_joined = await check_all_channels(user.id, context.bot)
    if not_joined:
        text = (
            f"👋 Welcome <b>{user.first_name}</b>!\n\n"
            "🔒 <b>Bot Access Locked</b>\n\n"
            "Pehle sabhi channels join karo:\n\n"
            "⬇️ Join karo phir <b>✅ Verify Now</b> dabao!"
        )
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=join_channels_keyboard())
        return

    set_verified(user.id)

    if is_new:
        welcome_text = (
            f"🎉 <b>Welcome {user.first_name}!</b>\n\n"
            f"{'🎁 Referred by a friend! ' if referred_by else ''}"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>Bonus Credits Credited!</b>\n\n"
            f"  🎟️ Base Credits:    <b>5</b>\n"
            f"  🎁 Welcome Bonus:  <b>+2</b>\n"
            f"  ━━━━━━━━━━━━━\n"
            f"  💎 Total Credits:  <b>7</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔮 <b>Wingo 30 Big/Small Predictor</b>\n"
            f"Refer karo aur aur credits kamao!\n\n"
            f"👇 Prediction lene ke liye:"
        )
    else:
        welcome_text = (
            f"✅ <b>Welcome back {user.first_name}!</b>\n\n"
            f"🎟️ Credits: <b>{credits}</b>\n\n"
            f"👇 Kya karna hai?"
        )

    await update.message.reply_text(welcome_text, parse_mode="HTML", reply_markup=main_keyboard(credits))


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    await query.answer()

    # ── VERIFY ──
    if query.data == "verify":
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

    # ── PREDICT ──
    elif query.data == "predict":
        not_joined = await check_all_channels(user.id, context.bot)
        if not_joined:
            await query.edit_message_text("🔒 Pehle channels join karo!", parse_mode="HTML", reply_markup=join_channels_keyboard())
            return

        credits = get_credits(user.id)
        if credits <= 0:
            await query.edit_message_text(
                "😔 <b>Credits Khatam Ho Gaye!</b>\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "🔗 <b>Refer karo aur 4 FREE credits pao!</b>\n\n"
                "Apna refer link share karo kisi ko bhi:\n"
                "Jab woh bot join kare → tumhe 4 credits!\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "💬 Personal loss recovery ke liye:\n"
                f"DM karo @{SUPPORT_USERNAME}",
                parse_mode="HTML",
                reply_markup=no_credits_keyboard(user.id)
            )
            return

        context.user_data["waiting_for_digits"] = True
        await query.edit_message_text(
            f"🎯 <b>WINGO 30 PREDICTOR</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎟️ Credits remaining: <b>{credits}</b>\n\n"
            f"📝 <b>Last 3 digits enter karo:</b>\n\n"
            f"Example: <code>456</code> ya <code>789</code>\n\n"
            f"⬇️ Neeche type karo:",
            parse_mode="HTML"
        )

    # ── REFER ──
    elif query.data == "refer":
        credits = get_credits(user.id)
        refers = get_refers(user.id)
        bot_link = f"https://t.me/{BOT_USERNAME}?start={user.id}"
        await query.edit_message_text(
            f"👥 <b>Refer & Earn Program</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎟️ Tumhare Credits: <b>{credits}</b>\n"
            f"👥 Total Refers:    <b>{refers}</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>Har refer pe → 4 Credits!</b>\n\n"
            f"🔗 Tera Refer Link:\n"
            f"<code>{bot_link}</code>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📤 Share karo aur credits kamao!",
            parse_mode="HTML",
            reply_markup=refer_keyboard(user.id)
        )

    # ── STATS ──
    elif query.data == "stats":
        credits = get_credits(user.id)
        refers = get_refers(user.id)
        await query.edit_message_text(
            f"📊 <b>Teri Stats</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 Name:           <b>{user.first_name}</b>\n"
            f"🎟️ Credits:        <b>{credits}</b>\n"
            f"👥 Total Refers:   <b>{refers}</b>\n"
            f"💰 Credits Earned: <b>{refers * CREDITS_PER_REFER}</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💬 Loss recovery help:\n"
            f"DM @{SUPPORT_USERNAME}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👥 Refer & Earn", callback_data="refer")],
                [InlineKeyboardButton("🔙 Back", callback_data="back_main")],
            ])
        )

    # ── BACK ──
    elif query.data == "back_main":
        credits = get_credits(user.id)
        await query.edit_message_text(
            f"🎯 <b>Wingo 30 Predictor</b>\n\n"
            f"🎟️ Credits: <b>{credits}</b>\n\n"
            f"👇 Kya karna hai?",
            parse_mode="HTML",
            reply_markup=main_keyboard(credits)
        )


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()

    # Admin commands
    if user.id in ADMIN_IDS:
        if text.startswith("/broadcast "):
            msg = text[len("/broadcast "):]
            users = get_all_users()
            sent, failed = 0, 0
            for uid in users:
                try:
                    await context.bot.send_message(uid, msg, parse_mode="HTML")
                    sent += 1
                except Exception:
                    failed += 1
            await update.message.reply_text(f"📢 Broadcast!\n✅ Sent: {sent}\n❌ Failed: {failed}")
            return

        if text == "/stats":
            total = get_total_users()
            await update.message.reply_text(
                f"📊 <b>Bot Stats</b>\n\n👥 Total Users: <b>{total}</b>",
                parse_mode="HTML"
            )
            return

        if text.startswith("/addcredits "):
            parts = text.split()
            if len(parts) == 3:
                uid, amt = int(parts[1]), int(parts[2])
                conn = sqlite3.connect("bot_users.db")
                conn.execute("UPDATE users SET credits=credits+? WHERE user_id=?", (amt, uid))
                conn.commit()
                conn.close()
                await update.message.reply_text(f"✅ Added {amt} credits to {uid}")
            return

    # Prediction flow
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
                parse_mode="HTML",
                reply_markup=no_credits_keyboard(user.id)
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

        # Big bar for result
        if result["result"] == "BIG":
            big_bar  = "🟥" * filled + "⬛" * (10 - filled)
            sml_bar  = "⬛" * 10
        else:
            big_bar  = "⬛" * 10
            sml_bar  = "🟩" * filled + "⬛" * (10 - filled)

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
            f"🔢 Digit Sum:   <b>{result['digit_sum']}</b>\n"
            f"📈 BIG Score:   <b>{result['big_score']}/8</b>\n"
            f"📉 SMALL Score: <b>{result['small_score']}/8</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎟️ Credits Left: <b>{new_credits}</b>"
            + (f"\n⚠️ <i>Credits kam hain! Refer karo</i>" if new_credits <= 1 else "")
            + f"\n━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ <i>Sirf entertainment ke liye</i>\n"
            f"💬 Loss recovery: @{SUPPORT_USERNAME}"
        )

        kb_buttons = [
            [InlineKeyboardButton("🔄 Predict Again", callback_data="predict")],
        ]
        if new_credits <= 1:
            kb_buttons.append([InlineKeyboardButton("👥 Refer & Get 4 Credits", callback_data="refer")])
        kb_buttons.append([InlineKeyboardButton("🏠 Main Menu", callback_data="back_main")])

        await update.message.reply_text(response, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb_buttons))
    else:
        not_joined = await check_all_channels(user.id, context.bot)
        if not_joined:
            await update.message.reply_text("🔒 Pehle channels join karo!", reply_markup=join_channels_keyboard())
        else:
            credits = get_credits(user.id)
            await update.message.reply_text("👇 Menu:", reply_markup=main_keyboard(credits))


def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    logger.info("✅ Bot started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
