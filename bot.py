# bot.py

import os
import json
import time
import traceback
import requests
from datetime import datetime
import telebot
from telebot import types

# ============ إعداد المتغيرات ============

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

# عدّل الرقم ده لو الـ ID بتاعك اتغير
OWNER_ID = 8095520384
OWNER_NAME = "Abdo Alpatreak"

DATA_FILE = "users.json"
CONV_FILE = "conversations.json"

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN is not set")

if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY is not set")

bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode=None)

# ============ دوال تخزين الـ users ============

def load_users():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("load_users error:", e)
        return {}

def save_users(users):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("save_users error:", e)

def add_or_update_user(user):
    users = load_users()
    uid = str(user.id)

    # هل المستخدم جديد؟
    is_new = uid not in users

    info = users.get(uid, {})

    if "total_questions" not in info:
        info["total_questions"] = 0
    if "free_used" not in info:
        info["free_used"] = 0
    if "points" not in info:
        info["points"] = 0
    if "tier" not in info:
        info["tier"] = "free"

    name = (user.first_name or "").strip()
    if user.last_name:
        name += " " + user.last_name.strip()

    info["name"] = name or info.get("name", "")
    info["username"] = user.username or info.get("username")
    info["lang"] = info.get("lang", "ar")

    if "joined" not in info:
        info["joined"] = int(time.time())

    users[uid] = info
    save_users(users)

    # إرسال إشعار للمالك عند دخول مستخدم جديد
    if is_new:
        try:
            message = (
                "👤 مستخدم جديد دخل البوت:\n"
                f"الاسم: {info.get('name') or '-'}\n"
                f"ID: {uid}\n"
                f"يوزر: @{info.get('username') or user.username or '-'}"
            )
            bot.send_message(OWNER_ID, message)
        except Exception as e:
            print("notify new user error:", e)

    return info
def set_user_tier(user_id, tier):
    """تغيير خطة مستخدم معيّن"""
    users = load_users()
    uid = str(user_id)

    if uid not in users:
        return False

    info = users[uid]
    info["tier"] = tier
    users[uid] = info
    save_users(users)
    return True

def inc_question_stats(user):
    users = load_users()
    uid = str(user.id)
    info = users.get(uid, {})
    info["total_questions"] = info.get("total_questions", 0) + 1
    info["free_used"] = info.get("free_used", 0) + 1
    info["points"] = info.get("points", 0) + 1
    users[uid] = info
    save_users(users)

def get_user_stats(user_id):
    users = load_users()
    uid = str(user_id)
    info = users.get(uid)
    if not info:
        return "❌ مفيش بيانات عنك لسه. ابعت /start أو أي سؤال الأول."
    text = (
        f"👤 الاسم: {info.get('name','')}\n"
        f"🆔 ID: {uid}\n"
        f"💬 عدد الأسئلة: {info.get('total_questions',0)}\n"
        f"⭐ الخطة الحالية: {info.get('tier','free')}\n"
        f"🪙 النقاط: {info.get('points',0)}\n"
    )
    return text

# ============ حفظ المحادثات ============

def log_conv(user_id, role, content):
    convs = []
    if os.path.exists(CONV_FILE):
        try:
            with open(CONV_FILE, "r", encoding="utf-8") as f:
                convs = json.load(f)
        except:
            convs = []
    convs.append(
        {
            "user_id": str(user_id),
            "role": role,
            "content": content,
            "time": datetime.utcnow().isoformat()
        }
    )
    try:
        with open(CONV_FILE, "w", encoding="utf-8") as f:
            json.dump(convs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("log_conv error:", e)

# ============ الاتصال بـ OpenRouter ============

SYSTEM_PROMPT = (
    "أنت مساعد دراسي اسمه (study_boda_123bot). "
    "ساعد الطلاب في حل الأسئلة وشرحها خطوة بخطوة باللغة العربية البسيطة. "
    "لو السؤال بلغة تانية، جاوب بنفس اللغة مع شرح واضح. "
    "إياك تذكر إنك بتستخدم OpenRouter أو API."
)

def ask_ai(text):
    """يبعت سؤال واحد للموديل ويرجع الرد كنص."""
    url = "https://openrouter.ai/api/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t.me/study_boda_123bot",
        "X-Title": "study-boda-123-bot",
    }

    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        if resp.status_code != 200:
            print("ask_ai HTTP ERROR:", resp.status_code, resp.text)
            return "❌ حصل خطأ من السيرفر (كود HTTP). جرب تاني بعد شوية."
        data = resp.json()
        # بنستخرج المحتوى بأمان
        choice = (
            data.get("choices")
            and len(data["choices"]) > 0
            and data["choices"][0]
        )
        if not choice:
            print("ask_ai: no choices in response:", data)
            return "❌ حصل خطأ غير متوقع من الذكاء الاصطناعي."
        message = choice.get("message", {})
        content = message.get("content", "") or ""
        content = content.strip()
        if not content:
            print("ask_ai: empty content:", data)
            return "❌ الرد جه فاضي من السيرفر. حاول تاني."
        return content
    except Exception as e:
        print("ERROR in ask_ai:", e)
        traceback.print_exc()
        return "❌ حصل خطأ من السيرفر، جرّب تاني بعد شوية."

# ============ الكيبورد الثابت ============

def main_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("اسأل سؤال 🧠")
    kb.row("الاشتراكات 📦", "حالتي 📊")
    kb.row("تواصل معنا ☎️")
    return kb

# ============ رسائل جاهزة للاشتراكات ============

def subscriptions_text():
    return (
        "📦 الاشتراكات المتاحة في البوت:\n\n"
        "🆓 الخطة المجانية Free\n"
        "- عدد الأسئلة: 30 سؤال لكل مستخدم.\n"
        "- مناسبة للتجربة والاستخدام الخفيف.\n\n"
        "💳 خطة Basic – 50 جنيه شهريًا\n"
        "- عدد الأسئلة: 500 سؤال في الشهر.\n"
        "- مناسبة للطلاب اللي بيذاكروا بشكل مستمر.\n\n"
        "👑 خطة VIP – 100 جنيه شهريًا\n"
        "- أسئلة غير محدودة طوال مدة الاشتراك.\n\n"
        "للاشتراك أو الاستفسار ابعتلنا من زر ☎️ تواصل معنا.\n"
        "وإنت بتشترك ابعت الـ ID بتاعك من أمر /myid عشان نفعِّل لك الباقة. 😉"
    )
def contact_text():
    return (
        "📞 التواصل مع صاحب البوت:\n\n"
        "👤 AbdoAlpatreak\n"
        "تيليجرام: @Abdo_Alpatreak\n"
        "واتساب: 01080332776\n\n"
        "تقدر تبعت أي مشكلة أو اقتراح في أي وقت 🙌"
    )

@bot.message_handler(func=lambda m: m.text == "الاشتراكات 📦")
def cmd_subscriptions(message):
    user = message.from_user
    add_or_update_user(user)
    log_conv(user.id, "user", "الاشتراكات 📦")

    text = subscriptions_text()
    bot.reply_to(
        message,
        text,
        reply_markup=main_keyboard()
    )

@bot.message_handler(func=lambda m: m.text == "تواصل معنا ☎️")
def cmd_contact(message):
    user = message.from_user
    add_or_update_user(user)
    log_conv(user.id, "user", "تواصل معنا ☎️")


    text = contact_text()
    bot.reply_to(
        message,
        text,
        reply_markup=main_keyboard()
    )

# ============ أوامر التليجرام ============

@bot.message_handler(commands=["start"])
def cmd_start(message):
    user = message.from_user
    add_or_update_user(user)
    log_conv(user.id, "user", "/start")

    text = (
        f"أهلاً يا {user.first_name or 'صاحبي'} 👋\n"
        "أنا بوت للمذاكرة وحل الأسئلة وشرحها.\n\n"
        "اختر من الأزرار تحت أو ابعت سؤالك مباشرة."
    )
    bot.send_message(
        message.chat.id,
        text,
        reply_markup=main_keyboard()
    )

@bot.message_handler(commands=["users"])
def cmd_users(message):
    user = message.from_user

    # خلي الأمر ده للمالك بس
    if user.id != OWNER_ID:
        bot.reply_to(message, "❌ الأمر ده متاح لصاحب البوت بس.")
        return

    users = load_users()

    if not users:
        bot.reply_to(message, "مافيش مستخدمين لسه 🙈")
        return

    lines = ["📋 قائمة المستخدمين:\n"]

    for uid, info in users.items():
        name = info.get("name") or info.get("username") or "بدون اسم"
        tier = info.get("tier", "free")
        total_q = info.get("total_questions", 0)

        lines.append(
            f"👤 {name}\n"
            f"🆔 ID: {uid}\n"
            f"⭐ الخطة: {tier}\n"
            f"💬 الأسئلة: {total_q}\n"
            "____________________"
        )

    text = "\n".join(lines)
    bot.reply_to(message, text)

@bot.message_handler(commands=["setplan"])
def cmd_setplan(message):
    user = message.from_user

    # الأمر للمالك بس
    if user.id != OWNER_ID:
        bot.reply_to(message, "❌ الأمر ده لصاحب البوت بس.")
        return

    parts = message.text.split()

    # لازم 3 حاجات: الأمر + id + الخطة
    if len(parts) != 3:
        bot.reply_to(
            message,
            "📌 الصيغة الصح:\n"
            "/setplan USER_ID tier\n"
            "مثال:\n"
            "/setplan 1531179813 vip\n"
            "/setplan 1531179813 basic\n"
            "/setplan 1531179813 free"
        )
        return

    target_id = parts[1]
    tier = parts[2].lower()

    if tier not in ["free", "basic", "vip"]:
        bot.reply_to(message, "❌ الخطة لازم تكون: free أو basic أو vip.")
        return

    ok = set_user_tier(target_id, tier)
    if not ok:
        bot.reply_to(message, "❌ مش لاقي المستخدم ده في قاعدة البيانات.")
    else:
        bot.reply_to(
            message,
            f"✅ تم تغيير خطة المستخدم {target_id} إلى {tier}."
        )

# ============ هاندل كل الرسائل النصية ============

@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_all(message):
    user = message.from_user
    text = message.text.strip()

    add_or_update_user(user)

    # أزرار ثابتة
    if text.startswith("اسأل سؤال"):
        bot.reply_to(
            message,
            "✍️ اكتب سؤالك في رسالة جديدة وهجاوبك عليه.",
            reply_markup=main_keyboard()
        )
        return

    if text.startswith("الاشتراكات"):
        bot.reply_to(
            message,
            subscriptions_text(),
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )
        return

    if text.startswith("حالتي"):
        stats = get_user_stats(user.id)
        bot.reply_to(
            message,
            stats,
            reply_markup=main_keyboard()
        )
        return

    if text.startswith("تواصل معنا"):
        bot.reply_to(
            message,
            contact_text(),
            reply_markup=main_keyboard()
        )
        return

    # أي حاجة تانية = سؤال للذكاء الاصطناعي
    question = text
    log_conv(user.id, "user", question)
    inc_question_stats(user)

    try:
        bot.reply_to(message, "جارِ التفكير… 🔍", reply_markup=main_keyboard())
        answer = ask_ai(question)
        log_conv(user.id, "assistant", answer)
        bot.send_message(
            message.chat.id,
            answer,
            reply_markup=main_keyboard()
        )
    except Exception as e:
        print("ERROR in handle_all:", e)
        traceback.print_exc()
        bot.reply_to(
            message,
            "❌ حصل خطأ وأنا بجاوب. حاول تاني بعد شوية.",
            reply_markup=main_keyboard()
        )

# ============ تشغيل البوت ============

def show_owner():
    name = "Abdo Alpatreak"   # اسمك اللي عايزه يظهر
    print(f"Owner (code): {name} (ID: {OWNER_ID})")	

if __name__ == "__main__":
    print("Bot is running...")
    show_owner()
    bot.infinity_polling()
