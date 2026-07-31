import os
import time
import random
import sqlite3
import hashlib
import hmac
import urllib.parse
import threading
import requests
from datetime import datetime
from urllib.parse import quote
from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# ====== الإعدادات الرئيسية ======
BOT_TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_TELEGRAM_BOT_TOKEN_HERE')
ADMIN_ID = 6697645974  # ID الخاص بك إدريس
CHANNEL_USERNAME = "@kdkpoints" 
SECRET_KEY = "KINGDOM_SECRET_2026"

ADSTERRA_SMARTLINK = "https://www.effectivecpmnetwork.com/c14nhbifa?key=36ca7b8acf50e1c9bb4d72d7d8012858"
OMG10_LINK = "https://omg10.com/4/11455415"

RECHARGE_PRICE = 10000     # 10,000 نقطة تعبئة = 50 درهم
REFERRAL_POINTS = 100      # +100 نقطة تعبئة لكل دعوة صديق
REQUIRED_REFERRALS = 10    # شرط 10 إحالات للسحب

# ====== قاعدة البيانات ======
def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, 
            recharge_points INTEGER DEFAULT 0,
            tap_points INTEGER DEFAULT 0,
            keys INTEGER DEFAULT 0,
            gems INTEGER DEFAULT 0,
            referrals_count INTEGER DEFAULT 0,
            is_vip INTEGER DEFAULT 0,
            referred_by INTEGER, 
            link_token TEXT DEFAULT NULL,
            phone_number TEXT DEFAULT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            phone TEXT,
            amount INTEGER,
            timestamp REAL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_cipher (
            date_str TEXT PRIMARY KEY,
            code_number TEXT,
            created_at REAL
        )
    ''')
    conn.commit()
    conn.close()

def db_get_user(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT recharge_points, tap_points, keys, gems, referrals_count, is_vip, link_token, phone_number FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def db_add_user(user_id, referred_by=None):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id, recharge_points, tap_points, keys, gems, referrals_count, is_vip, referred_by) VALUES (?, 0, 0, 0, 0, 0, 0, ?)', (user_id, referred_by))
    if cursor.rowcount > 0 and referred_by:
        cursor.execute('UPDATE users SET recharge_points = recharge_points + ?, referrals_count = referrals_count + 1 WHERE user_id = ?', (REFERRAL_POINTS, referred_by))
    conn.commit()
    conn.close()

def db_update_recharge_points(user_id, points_change):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET recharge_points = recharge_points + ? WHERE user_id = ?', (points_change, user_id))
    conn.commit()
    conn.close()

def db_set_token(token, user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET link_token = ? WHERE user_id = ?', (token, user_id))
    conn.commit()
    conn.close()

def db_save_phone(user_id, phone):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET phone_number = ? WHERE user_id = ?', (phone, user_id))
    conn.commit()
    conn.close()

def db_log_withdrawal(user_id, phone, amount):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO withdrawals (user_id, phone, amount, timestamp) VALUES (?, ?, ?, ?)', (user_id, phone, amount, time.time()))
    conn.commit()
    conn.close()

def db_get_user_by_token(token):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, recharge_points FROM users WHERE link_token = ?', (token,))
    row = cursor.fetchone()
    conn.close()
    return row

def db_get_stats():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM users WHERE phone_number IS NOT NULL')
    phones_count = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM withdrawals')
    total_withdrawals = cursor.fetchone()[0]
    conn.close()
    return total_users, phones_count, total_withdrawals

# ====== دوال الشفرة اليومية ======
def db_get_today_cipher():
    today = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT code_number FROM daily_cipher WHERE date_str = ?', (today,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def db_generate_new_cipher():
    today = datetime.now().strftime("%Y-%m-%d")
    new_code = str(random.randint(10000, 99999))
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO daily_cipher (date_str, code_number, created_at) VALUES (?, ?, ?)', (today, new_code, time.time()))
    conn.commit()
    conn.close()
    return new_code, today

def send_telegram_admin_notification(msg_text):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {"chat_id": ADMIN_ID, "text": msg_text, "parse_mode": "Markdown"}
        response = requests.post(url, json=payload, timeout=5)
        print("إشعار الأدمن:", response.text)
    except Exception as e:
        print("خطأ إشعار الأدمن:", e)

def daily_cipher_auto_cron():
    time.sleep(10)
    while True:
        try:
            today_code = db_get_today_cipher()
            if not today_code:
                new_code, today_date = db_generate_new_cipher()
                admin_msg = (
                    f"🔑 **تم تحديث الشفرة اليومية بنجاح!**\n\n"
                    f"🎲 **الكود الجديد (5 أرقام):** `{new_code}`\n"
                    f"📅 **تاريخ الإصدار:** {today_date}\n\n"
                    f"📢 يمكنك الآن نشر هذا الكود في قناة التلغرام {CHANNEL_USERNAME}!"
                )
                send_telegram_admin_notification(admin_msg)
        except Exception as err:
            print("خطأ الشفرة:", err)
        time.sleep(1800)

def hourly_status_cron():
    time.sleep(60)
    while True:
        try:
            total_users, phones_count, total_withdrawals = db_get_stats()
            msg = (
                f"⏰ **تحديث الحالة الساعية (KDK Bot):**\n\n"
                f"👥 إجمالي المستخدمين: `{total_users}`\n"
                f"📱 أرقام الهواتف المسجلة: `{phones_count}`\n"
                f"💸 إجمالي سحوبات 50DH: `{total_withdrawals}`\n"
                f"🟢 السيرفر شغال وفي أمان تاماً!"
            )
            send_telegram_admin_notification(msg)
        except Exception as err:
            print("خطأ التحديث الساعي:", err)
        time.sleep(3600)

def verify_telegram_data(init_data: str) -> bool:
    if not init_data or not BOT_TOKEN:
        return True
    try:
        parsed_data = dict(urllib.parse.parse_qsl(init_data))
        if "hash" not in parsed_data:
            return False
        hash_check = parsed_data.pop("hash")
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(calculated_hash, hash_check)
    except Exception:
        return False

flask_app = Flask(__name__)
CORS(flask_app)

@flask_app.route('/', methods=['GET'])
def home_ping():
    return "KDK Bot Server is Alive!", 200

@flask_app.route('/sync_points', methods=['GET', 'POST'])
def sync_points():
    token = request.args.get('token') or request.form.get('token')
    init_data = request.args.get('initData') or request.form.get('initData')
    amount = int(request.args.get('amount', 0) or request.form.get('amount', 0))

    if init_data and not verify_telegram_data(init_data):
        return jsonify({"status": "error", "message": "Unauthorized Telegram Data"}), 403

    user_data = db_get_user_by_token(token)
    if user_data:
        user_id, current_recharge = user_data
        if amount > 0:
            db_update_recharge_points(user_id, amount)
            current_recharge += amount
        return jsonify({"status": "success", "new_points": current_recharge})

    return jsonify({"status": "error", "message": "Invalid token"}), 400

@flask_app.route('/get_cipher', methods=['GET'])
def get_cipher():
    code = db_get_today_cipher()
    if not code:
        code, _ = db_generate_new_cipher()
    return jsonify({"status": "success", "code": code})

def run_flask():
    flask_app.run(host='0.0.0.0', port=8080)

def get_main_keyboard(): 
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 دخول اللعبة (Netlify App)", callback_data='play_game')],
        [InlineKeyboardButton("👑 ترقية للحساب VIP (50DH)", callback_data='vip_info')],
        [InlineKeyboardButton("🎬 مشاهدة إعلان مباشر +10", callback_data='earn')],
        [InlineKeyboardButton("👥 دعوة أصدقاء (+100 نقطة)", callback_data='referral')],
        [InlineKeyboardButton("💳 رصيدي ومعلوماتي", callback_data='balance')],
        [InlineKeyboardButton("📲 سحب تعبئة 50 درهم", callback_data='withdraw_recharge')]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    user_id = user.id
    args = context.args
    referred_by = int(args[0]) if args and args[0].isdigit() and int(args[0]) != user_id else None

    if not db_get_user(user_id):
        db_add_user(user_id, referred_by)
        if referred_by: 
            try:
                await context.bot.send_message(
                    chat_id=referred_by,
                    text=f"🎉 **صديق جديد انضم عبر رابطك!**\nحصلت على **+{REFERRAL_POINTS} نقطة تعبئة** وزادت إحالاتك +1 🚀"
                )
            except Exception:
                pass

    user_info = db_get_user(user_id)
    recharge_pts = user_info[0] if user_info else 0
    ref_count = user_info[4] if user_info else 0
    is_vip = "👑 VIP" if (user_info and user_info[5] == 1) else "عادي"

    msg_text = (
        f"🎯 مرحبا بك {user.first_name} في بوت **KDK Point**\n\n"
        f"👑 نوع الحساب: **{is_vip}**\n"
        f"📲 رصيد التعبئة: **{recharge_pts} / 10,000** نقطة\n"
        f"👥 الإحالات المكتملة: **{ref_count} / {REQUIRED_REFERRALS}** صديق\n\n"
        f"تفرج ف الإعلانات ودير الإحالات لجمع 10,000 نقطة واستبدالها بـ **تعبئة 50 درهم** 📱👇"
    )
    if update.message:
        await update.message.reply_text(msg_text, reply_markup=get_main_keyboard(), parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.edit_message_text(msg_text, reply_markup=get_main_keyboard(), parse_mode="Markdown")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or user.id != ADMIN_ID:
        if update.callback_query:
            await update.callback_query.answer("⚠️ هذا الأمر خاص بالأدمن فقط!", show_alert=True)
        return

    total_users, phones_count, total_withdrawals = db_get_stats()
    admin_text = (
        f"🛠️ **لوحة تحكم الأدمن (الإدارة):**\n\n"
        f"👥 إجمالي المستخدمين: `{total_users}`\n"
        f"📱 الأرقام المسجلة: `{phones_count}`\n"
        f"💸 عمليات السحب المنفذة: `{total_withdrawals}`\n"
        f"🟢 حالة السيرفر: شغال 100%"
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data='main_menu')]])

    if update.message:
        await update.message.reply_text(admin_text, reply_markup=keyboard, parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(admin_text, reply_markup=keyboard, parse_mode="Markdown")

async def play_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.from_user:
        return
    await query.answer()
    user_id = query.from_user.id

    token = hashlib.md5(f"{user_id}{SECRET_KEY}{time.time()}".encode()).hexdigest()[:12]
    db_set_token(token, user_id)

    # تم تصحيح الرابط هنا ليوجه مباشرة إلى موقعك بدون طلب تسجيل دخول في Netlify
    web_app_url = f"https://lambent-axolotl-3691d8.netlify.app/?token={token}"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 الدخول للعبة KDK Point", url=web_app_url)],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data='main_menu')]
    ])

    await query.edit_message_text(
        f"👑 **مملكة KDK Point الملكية**\n\n"
        f"اضغط على الزر أسفله للعب، مشاهدة الإعلانات، وجمع نقاط التعبئة 50DH! 🚀",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

async def vip_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    msg = (
        f"👑 **مميزات الاشتراك الملكي (VIP Pass - 50DH):**\n\n"
        f"✨ **مضاعفة النقاط:** كل إعلان ونقرة كتاخد عليها الدوبل.\n"
        f"⚡ **طاقة سريعة:** شحن الطاقة كيكون أسرع.\n"
        f"🚀 **سحب أولوية:** طلبات التعبئة ديالك كتقدّم فـ الحين.\n\n"
        f"💳 **طريقة التفعيل:** تحويل 50 درهم وإرسال الوصل هنا!"
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 القائمة", callback_data='main_menu')]])
    await query.edit_message_text(msg, reply_markup=keyboard, parse_mode="Markdown")

async def earn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()
    selected_ad = random.choice([ADSTERRA_SMARTLINK, OMG10_LINK])

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥 اضغط هنا لمشاهدة الإعلان", url=selected_ad)],
        [InlineKeyboardButton("🔙 القائمة", callback_data='main_menu')]
    ])

    await query.edit_message_text(
        f"✅ **اضغط على الزر أسفله لفتح الإعلان في المتصفح الخارجي:**\n\n⏳ شاهد الإعلان لمدة 15 ثانية ثم عود للبوت لاستكمال نقاطك!",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

async def withdraw_recharge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.from_user:
        return
    user_id = query.from_user.id
    user_data = db_get_user(user_id)
    recharge_pts = user_data[0] if user_data else 0
    ref_count = user_data[4] if user_data else 0

    if recharge_pts < RECHARGE_PRICE:
        await query.answer(f"❌ رصيدك غير كافي! تحتاج 10,000 نقطة.", show_alert=True)
        return

    if ref_count < REQUIRED_REFERRALS:
        await query.answer(f"⚠️ باقي لك إحالات لتفعيل السحب! (لديك {ref_count}/10)", show_alert=True)
        return

    await query.answer()
    contact_keyboard = ReplyKeyboardMarkup([[KeyboardButton("📱 إرسال رقم الهاتف تلقائياً", request_contact=True)]], resize_keyboard=True, one_time_keyboard=True)
    await context.bot.send_message(chat_id=user_id, text="📱 **تأكيد عملية السحب (50 درهم):**\n\nاضغط على الزر أسفله لمشاركة رقم هاتفك:", reply_markup=contact_keyboard, parse_mode="Markdown")

async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id
    contact = update.message.contact

    if contact and contact.user_id == user_id:
        phone = contact.phone_number
        db_save_phone(user_id, phone)
        db_update_recharge_points(user_id, -RECHARGE_PRICE)
        db_log_withdrawal(user_id, phone, 50)

        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID, 
                text=f"🚨 **طلب تعبئة جديد!**\n🆔 ID: `{user_id}`\n👤 الاسم: {update.effective_user.first_name}\n📞 هاتف: `{phone}`", 
                parse_mode="Markdown"
            )
        except Exception as e:
            print("خطأ إرسال الطلب للأدمن:", e)

        await update.message.reply_text("🎉 **تم استقبال طلبك بنجاح!** سيتم إرسال التعبئة قريباً.", reply_markup=ReplyKeyboardRemove(), parse_mode="Markdown")
        await context.bot.send_message(chat_id=user_id, text="🎯 القائمة الرئيسية:", reply_markup=get_main_keyboard())

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.from_user:
        return
    user_id = query.from_user.id
    user_data = db_get_user(user_id)
    ref_count = user_data[4] if user_data else 0
    bot = await context.bot.get_me()

    ref_link = f"https://t.me/{bot.username}?start={user_id}"
    raw_text = f"🎁 أجي تلعب معايا فـ KDK Point واجمع نقاط واستبدلها بـ تعبئة 50DH!\n{ref_link}"
    encoded_text = quote(raw_text)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📲 مشاركة WhatsApp", url=f"https://api.whatsapp.com/send?text={encoded_text}")],
        [InlineKeyboardButton("✈️ مشاركة Telegram", url=f"https://t.me/share/url?url={ref_link}&text=🎁 أجي تلعب معايا فـ KDK Point!")],
        [InlineKeyboardButton("🔙 القائمة", callback_data='main_menu')]
    ])

    await query.edit_message_text(f"👥 **دعوة الأصدقاء**\n\n🔗 رابطك:\n`{ref_link}`", reply_markup=keyboard, parse_mode="Markdown")

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.from_user:
        return
    user_data = db_get_user(query.from_user.id)
    recharge_pts = user_data[0] if user_data else 0
    ref_count = user_data[4] if user_data else 0
    phone = user_data[7] if user_data and user_data[7] else "غير مسجل"

    await query.edit_message_text(f"💳 **معلومات الحساب**\n\n🆔 المعرف: `{query.from_user.id}`\n📱 الهاتف: `{phone}`\n📲 التعبئة: **{recharge_pts}/10,000**\n👥 الإحالات: **{ref_count}/10**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 القائمة", callback_data='main_menu')]]), parse_mode="Markdown")

def main():
    init_db()
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=daily_cipher_auto_cron, daemon=True).start()
    threading.Thread(target=hourly_status_cron, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(play_game, pattern='^play_game$'))
    app.add_handler(CallbackQueryHandler(vip_info, pattern='^vip_info$'))
    app.add_handler(CallbackQueryHandler(earn, pattern='^earn$'))
    app.add_handler(CallbackQueryHandler(referral, pattern='^referral$'))
    app.add_handler(CallbackQueryHandler(balance, pattern='^balance$'))
    app.add_handler(CallbackQueryHandler(withdraw_recharge, pattern='^withdraw_recharge$'))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern='^admin$'))
    app.add_handler(CallbackQueryHandler(start, pattern='^main_menu$'))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))

    print("Bot is running successfully!")
    app.run_polling()

if __name__ == '__main__': 
    main()
