import os
import json
import time
from datetime import datetime
import requests
import telebot

# ================= إعداد التوكنات =================
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN is not set")

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY is not set")

# ================= إعدادات صاحب البوت / الباقات =================
PAYMENT_NUMBER = "01080332776"
BOT_OWNER_USERNAME = "Abdo_Alpatreak"
OWNER_ID = 8095520384

DATA_FILE = "users.json"
CONV_FILE = "conversations.json"

FREE_LIMIT_Q = 30
FREE_LIMIT_IMG = 10

BASIC_LIMIT_Q = 500
BASIC_LIMIT_IMG = 100
BASIC_DAYS = 30

VIP_DAYS = 30

RATE_LIMIT_SECONDS = 2

SYSTEM_PROMPT = """
أنت مساعد دراسي ذكي اسمه "عبدالحميد أحمد".
- تجاوب بالعربية الفصحى المبسطة.
- تشرح للطالب خطوة خطوة لكن بدون إطالة غير ضرورية.
- في الأسئلة الحسابية: اعطِ الناتج النهائي + شرح مختصر (سطر أو سطرين).
- لا تذكر أنك نموذج ذكاء اصطناعي، فقط تحدث كمساعد دراسي.
"""

# ================= دوال مساعدة للملفات =================
def load_users():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_users():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def format_date(ts):
    if not ts:
        return "غير محدد"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")

users = load_users()

# ================= إدارة المستخدمين =================
def get_user_record(user_id, message=None):
    uid = str(user_id)
    if uid not in users:
        users[uid] = {
            "total_questions": 0,
            "free_used": 0,
            "basic_used": 0,
            "vip_used": 0,
            "free_images_used": 0,
            "basic_images_used": 0,
            "vip_images_used": 0,
            "tier": "free",
            "free_until": 0,
            "basic_until": 0,
            "vip_until": 0,
            "points": 0,
            "name": "",
            "username": "",
            "lang": "",
            "joined": 0,
        }

    u = users[uid]

    if message:
        full_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
        if not u.get("name"):
            u["name"] = full_name
        if not u.get("username"):
            u["username"] = message.from_user.username or ""
        if not u.get("lang"):
            u["lang"] = message.from_user.language_code or ""
        if not u.get("joined"):
            u["joined"] = int(time.time())

    save_users()
    return u

def user_tier(user):
    now = time.time()
    if user.get("vip_until", 0) > now:
        return "vip"
    if user.get("basic_until", 0) > now:
        return "basic"
    return "free"

def check_limits(user, kind="text"):
    tier = user_tier(user)

    if kind == "image":
        if tier == "vip":
            return True, "", "vip"
        if tier == "basic":
            if user["basic_images_used"] < BASIC_LIMIT_IMG:
                return True, "", "basic"
        else:
            if user["free_images_used"] < FREE_LIMIT_IMG:
                return True, "", "free"

        msg = (
            "انتهت محاولات الصور في خطتك الحالية.\n"
            f"- Basic (50 جنيه): {BASIC_LIMIT_IMG} صورة.\n"
            f"للاشتراك تواصل على: {PAYMENT_NUMBER}"
        )
        return False, msg, "images_over"

    # ----- أسئلة نصية -----
    if tier == "vip":
        return True, "", "vip"

    if tier == "basic":
        if user["basic_used"] < BASIC_LIMIT_Q:
            return True, "", "basic"
    else:
        if user["free_used"] < FREE_LIMIT_Q:
            return True, "", "free"

    msg = (
        "انتهى عدد الأسئلة المسموح به في خطتك الحالية.\n"
        f"- الخطة المجانية Free: {FREE_LIMIT_Q} سؤال.\n"
        f"- Basic (50 جنيه): {BASIC_LIMIT_Q} سؤال.\n"
        f"للاشتراك تواصل على: {PAYMENT_NUMBER}"
    )
    return False, msg, "free_questions_over"

def log_conv(user_id, kind, text):
    try:
        data = []
        if os.path.exists(CONV_FILE):
            with open(CONV_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        data.append({
            "user_id": user_id,
            "kind": kind,
            "text": text,
            "ts": int(time.time()),
        })
        with open(CONV_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("log_conv error:", e)

# ================= استدعاء OpenRouter =================
def call_openrouter(messages):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://telegram-bot.local",
        "X-Title": "study_boda_123bot",
    }
    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": messages,
        "max_tokens": 800,
        "temperature": 0.4,
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print("OpenRouter request error:", e)
        return None

# ================= إنشاء البوت =================
bot = telebot.TeleBot(TELEGRAM_TOKEN)

def is_owner(message):
    return message.from_user.id == OWNER_ID

# ================= كيبورد رئيسية =================
def main_keyboard():
    kb = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🧠 اسأل سؤال")
    kb.row("📦 الاشتراكات", "📊 حالتي")
    kb.row("☎️ تواصل معنا")
    return kb

# ================= أوامر المالك =================
@bot.message_handler(commands=["setvip"])
def cmd_setvip(message):
    if not is_owner(message):
        bot.reply_to(message, "الأمر ده لصاحب البوت فقط ❌")
        return
    parts = message.text.strip().split()
    if len(parts) < 2:
        bot.reply_to(message, "استخدم الأمر بالشكل ده:\n/setvip <user_id>")
        return
    uid = parts[1]
    u = get_user_record(uid)
    u["vip_until"] = time.time() + VIP_DAYS * 24 * 60 * 60
    u["tier"] = "vip"
    save_users()
    bot.reply_to(message, f"تم تفعيل VIP ✅ للمستخدم {uid}")

@bot.message_handler(commands=["setbasic"])
def cmd_setbasic(message):
    if not is_owner(message):
        bot.reply_to(message, "الأمر ده لصاحب البوت فقط ❌")
        return
    parts = message.text.strip().split()
    if len(parts) < 2:
        bot.reply_to(message, "استخدم الأمر بالشكل ده:\n/setbasic <user_id>")
        return
    uid = parts[1]
    u = get_user_record(uid)
    u["basic_until"] = time.time() + BASIC_DAYS * 24 * 60 * 60
    u["tier"] = "basic"
    save_users()
    bot.reply_to(message, f"تم تفعيل Basic ✅ للمستخدم {uid}")

@bot.message_handler(commands=["setfree"])
def cmd_setfree(message):
    if not is_owner(message):
        bot.reply_to(message, "الأمر ده لصاحب البوت فقط ❌")
        return
    parts = message.text.strip().split()
    if len(parts) < 2:
        bot.reply_to(message, "استخدم الأمر بالشكل ده:\n/setfree <user_id>")
        return
    uid = parts[1]
    u = get_user_record(uid)
    u["tier"] = "free"
    u["vip_until"] = 0
    u["basic_until"] = 0
    save_users()
    bot.reply_to(message, f"تم تحويل {uid} إلى الخطة المجانية ✅")

@bot.message_handler(commands=["myid"])
def cmd_myid(message):
    bot.reply_to(message, f"📌 الـ ID بتاعك هو:\n`{message.from_user.id}`", parse_mode="Markdown")

# ================= /start =================
@bot.message_handler(commands=["start", "help"])
def handle_start(message):
    u = get_user_record(message.from_user.id, message)
    kb = main_keyboard()
    text = (
        "أهلاً بيك 👋\n\n"
        "أنا بوت دراسي أقدر أساعدك في حل الأسئلة وشرح الدروس.\n"
        "- اضغط على *🧠 اسأل سؤال* وابعت سؤالك.\n"
        "- من *📊 حالتي* تقدر تشوف خطتك وعدد الأسئلة اللي استخدمتها.\n"
        "- من *📦 الاشتراكات* تعرف خطط الباقات.\n"
        "- من *☎️ تواصل معنا* تلاقي بيانات التواصل مع صاحب البوت.\n"
    )
    bot.send_message(message.chat.id, text, reply_markup=kb, parse_mode="Markdown")

# ================= زر الاشتراكات =================
@bot.message_handler(func=lambda m: m.text == "📦 الاشتراكات")
def handle_subscriptions(message):
    text = (
        "📦 *الاشتراكات المتاحة في البوت:*\n\n"
        "🆓 *الخطة المجانية Free*\n"
        f"- عدد الأسئلة: {FREE_LIMIT_Q} سؤال لكل مستخدم.\n"
        "- مناسبة للتجربة والاستخدام الخفيف.\n\n"
        "💳 *خطة Basic – 50 جنيه شهريًا*\n"
        f"- عدد الأسئلة: {BASIC_LIMIT_Q} سؤال في الشهر.\n"
        "- مناسبة للطلاب اللي بيذاكروا بشكل مستمر.\n\n"
        "👑 *خطة VIP – 100 جنيه شهريًا*\n"
        "- أسئلة غير محدودة طوال مدة الاشتراك.\n\n"
        "للاشتراك أو الاستفسار ابعتلنا من زر ☎️ تواصل معنا.\n"
        "وإنت بتشترك ابعت الـ ID بتاعك من أمر /myid عشان نفعِّل لك الباقة. 😉"
    )
    bot.reply_to(message, text, parse_mode="Markdown")

# ================= زر تواصل معنا =================

@bot.message_handler(func=lambda m: m.text and "تواصل معنا" in m.text)
def handle_contact(message):
    text = (
        "📞 *التواصل مع صاحب البوت:*\n\n"
        "👤 *AbdoAlpatreak*\n"
        "تيليجرام: *@AbdoAlpatreak*\n"
        "واتساب: *01080332776*\n\n"
        "تقدر تبعت أي مشكلة أو اقتراح في أي وقت 🙌"
    )
    bot.reply_to(message, text, parse_mode="Markdown")

# ================= زر حالتي =================
@bot.message_handler(func=lambda m: m.text == "📊 حالتي")
def handle_status(message):
    user = get_user_record(message.from_user.id, message)
    tier = user_tier(user)

    if tier == "vip":
        plan_name = "👑 VIP (غير محدودة)"
        used = user.get("vip_used", 0)
        limit = "غير محدودة"
        remaining = "غير محدود"
        until = format_date(user.get("vip_until"))
    elif tier == "basic":
        plan_name = "💳 Basic"
        used = user.get("basic_used", 0)
        limit = BASIC_LIMIT_Q
        remaining = max(0, BASIC_LIMIT_Q - used)
        until = format_date(user.get("basic_until"))
    else:
        plan_name = "🆓 Free"
        used = user.get("free_used", 0)
        limit = FREE_LIMIT_Q
        remaining = max(0, FREE_LIMIT_Q - used)
        until = "غير محدد"

    total_q = user.get("total_questions", 0)
    points = user.get("points", 0)

    text = (
        "📊 *حالتك في البوت:*\n\n"
        f"- الخطة الحالية: {plan_name}\n"
        f"- إجمالي الأسئلة التي سألتها: *{total_q}* سؤال.\n"
        f"- عدد النقاط: *{points}* نقطة.\n"
        f"- عدد الأسئلة المستخدمة في خطتك الحالية: *{used}* من *{limit}*.\n"
        f"- المتبقي في خطتك الحالية: *{remaining}* سؤال.\n"
        f"- انتهاء الاشتراك: *{until}*.\n\n"
        "لو حابب تطور خطتك لباقات Basic / VIP تواصل معنا من زر ☎️ تواصل معنا."
    )
    bot.reply_to(message, text, parse_mode="Markdown")

# ================= استقبال الأسئلة =================
@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_question(message):
    # تجاهل أزرار الكيبورد والأوامر
    if message.text in ["🧠 اسأل سؤال", "📦 الاشتراكات", "📊 حالتي", "☎️ تواصل معنا", "تواصل معنا ☎️"]:
        return

    if message.text.startswith("/"):
        return

    user = get_user_record(message.from_user.id, message)

    allowed, info, reason = check_limits(user, kind="text")
    if not allowed:
        bot.reply_to(message, info, parse_mode="Markdown")
        return

    bot.send_chat_action(message.chat.id, "typing")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": message.text},
    ]

    answer = call_openrouter(messages)
    if not answer:
        bot.reply_to(message, "في مشكلة مؤقتة في السيرفر، جرب تاني بعد شوية 🙏")
        return

    # تحديث الإحصائيات
    user["total_questions"] = user.get("total_questions", 0) + 1
    tier = user_tier(user)
    if tier == "vip":
        user["vip_used"] = user.get("vip_used", 0) + 1
    elif tier == "basic":
        user["basic_used"] = user.get("basic_used", 0) + 1
    else:
        user["free_used"] = user.get("free_used", 0) + 1

    user["points"] = user.get("points", 0) + 1
    save_users()

    log_conv(message.from_user.id, "text", message.text)
    bot.reply_to(message, answer)

# ================= تشغيل البوت =================
if __name__ == "__main__":
    print("Bot is running...")
    print(f"Owner (code): {BOT_OWNER_USERNAME}")
    bot.infinity_polling(timeout=60, skip_pending=True)
