import os
import asyncio
import random
import json
from datetime import datetime, timezone
from telethon import TelegramClient, events, errors
from telethon.tl.types import UpdateChannelParticipant, ChannelParticipantLeft
from telethon.sessions import StringSession

# متغیرها از تنظیمات ریل‌وی خوانده می‌شوند
API_ID_STR = os.environ.get("API_ID", "").strip()
API_HASH = os.environ.get("API_HASH", "").strip()
SESSION_STRING = (os.environ.get("RETENTION_SESSION") or os.environ.get("SESSION_STRING", "")).strip()
TARGET_CHANNEL_ID_STR = os.environ.get("TARGET_CHANNEL_ID", "").strip()

# اعتبارسنجی اولیه متغیرها
API_ID = int(API_ID_STR) if API_ID_STR.isdigit() else 0
TARGET_CHANNEL_ID = int(TARGET_CHANNEL_ID_STR) if TARGET_CHANNEL_ID_STR.lstrip("-").isdigit() else 0

# سقف روزانه و فایل ذخیره پیام‌ها
DAILY_SEND_LIMIT = 20
MESSAGES_FILE = "retention_messages.json"

# متن اختصاصی شما به همراه دو لحن مشابه برای جلوگیری از اسپم شدن اکانت
DEFAULT_MESSAGES = [
    "سلام خوبی بیزحمت بلاک نکن ❤️\nادمین کانال (ریمیکسی یو) هستم\nدیدم لفت دادید خواستم انتقاد، پیشنهاد و علت اینکه رفتید رو بهم بگید\nدمت هم گرم\nاگر باز دوس داشتی کنارمون باشی و حمایتمون کنی بیا قدمت رو چشم❤️♠️\nJoin us:\n🆔️ @remixiyu",
    "سلام وقتت بخیر بیزحمت بلاک نکنید 🤍\nادمین چنل (ریمیکسی یو) هستم\nمتوجه شدم از کانال خارج شدید، می‌خواستم دلیل رفتنتون یا انتقادی اگر هست رو بشنوم تا بهتر بشیم\nدمت گرم\nاگر مایل بودید باز هم کنارمون باشید قدمتون روی چشم 🌱❤️\nJoin us:\n🆔️ @remixiyu",
    "درود دوست عزیز، بیزحمت بلاک نکن 🌹\nادمین کانال (ریمیکسی یو) هستم\nدیدم لفت دادید، خوشحال میشم انتقاد، پیشنهاد یا علت رفتنتون رو بهم بگید\nدمت هم گرم\nاگه باز دوست داشتی حمایتمون کنی بیا قدمت رو چشم ❤️♠️\nJoin us:\n🆔️ @remixiyu"
]

def load_messages():
    if os.path.exists(MESSAGES_FILE):
        try:
            with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data:
                    return data
        except Exception:
            pass
    return DEFAULT_MESSAGES.copy()

def save_messages(msgs):
    try:
        with open(MESSAGES_FILE, "w", encoding="utf-8") as f:
            json.dump(msgs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Error saving messages] {e}", flush=True)

messages_list = load_messages()
processed_users = set()
sent_count_today = 0
last_day_reset = datetime.now(timezone.utc).day

# صف پردازش ناهمگام
send_queue = asyncio.Queue()

# ساخت نمونه کلاینت
client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

async def queue_worker():
    global sent_count_today, last_day_reset
    while True:
        user_id = await send_queue.get()
        try:
            current_day = datetime.now(timezone.utc).day
            if current_day != last_day_reset:
                sent_count_today = 0
                last_day_reset = current_day

            if sent_count_today >= DAILY_SEND_LIMIT:
                print(f"[Limit] سقف روزانه ({DAILY_SEND_LIMIT}) پر شده است. پیام به {user_id} ارسال نمی‌شود.", flush=True)
                continue

            # تأخیر تصادفی ۲ تا ۵ دقیقه بین هر ارسال برای رعایت الگوریتم‌های تلگرام
            delay = random.randint(120, 300)
            print(f"[Worker] آماده‌سازی ارسال به {user_id}. در حال انتظار برای {delay} ثانیه...", flush=True)
            await asyncio.sleep(delay)

            msg_text = random.choice(messages_list) if messages_list else random.choice(DEFAULT_MESSAGES)

            try:
                # شناسایی کاربر برای ارسال مستقیم به پی‌وی بدون نیاز به چت قبلی
                try:
                    entity = await client.get_entity(user_id)
                except ValueError:
                    await client.get_participants(TARGET_CHANNEL_ID, limit=100)
                    entity = await client.get_entity(user_id)

                await client.send_message(entity, msg_text)
                sent_count_today += 1
                print(f"[Worker Success] پیام به کاربر {user_id} با موفقیت ارسال شد. (مجموع امروز: {sent_count_today}/{DAILY_SEND_LIMIT})", flush=True)
            except errors.UserPrivacyRestrictedError:
                print(f"[Privacy] پی‌وی کاربر {user_id} بسته است.", flush=True)
            except errors.PeerFloodError:
                print("[Flood] تلگرام هشدار محدودیت داد! توقف موقت صف به مدت ۴۵ دقیقه...", flush=True)
                await asyncio.sleep(2700)
            except errors.FloodWaitError as e:
                print(f"[FloodWait] توقف صف برای {e.seconds} ثانیه.", flush=True)
                await asyncio.sleep(e.seconds + 5)
            except Exception as e:
                print(f"[Send Error] خطا در ارسال به {user_id}: {e}", flush=True)

        finally:
            send_queue.task_done()

@client.on(events.Raw(UpdateChannelParticipant))
async def on_user_left(event):
    try:
        raw_channel_id = int(f"-100{event.channel_id}")
        if raw_channel_id != TARGET_CHANNEL_ID:
            return

        if isinstance(event.new_participant, ChannelParticipantLeft):
            user_id = event.user_id
            if user_id in processed_users:
                return

            processed_users.add(user_id)
            print(f"[Detect] کاربر {user_id} از کانال خارج شد. اضافه شد به صف ارسال.", flush=True)
            await send_queue.put(user_id)

    except Exception as e:
        print(f"[Event Error] {e}", flush=True)

@client.on(events.NewMessage(outgoing=True))
async def handle_saved_commands(event):
    global messages_list
    if not event.is_private:
        return

    me = await client.get_me()
    if event.chat_id != me.id:
        return

    text = event.raw_text.strip()

    if text in [".help", "/help"]:
        help_msg = (
            "⚙️ **راهنمای مدیریت ربات بازگشت ممبر:**\n\n"
            "▫️ `.addmsg متن شما` : اضافه کردن پیام جدید\n"
            "▫️ `.listmsg` : نمایش لیست پیام‌های فعال\n"
            "▫️ `.resetall` : حذف تمام متن‌ها و خالی کردن لیست\n"
            "▫️ `.clearmsg` : بازگشت به متن‌های پیش‌فرض شما\n"
            "▫️ `.status` : وضعیت صف و سقف روزانه"
        )
        await event.edit(help_msg)

    elif text == ".resetall":
        messages_list = []
        save_messages(messages_list)
        await event.edit("🗑 **تمام متن‌های قبلی پاک شدند!** حالا متن‌های جدید رو با `.addmsg` اضافه کن.")

    elif text.startswith(".addmsg "):
        new_msg = text[8:].strip()
        if new_msg:
            messages_list.append(new_msg)
            save_messages(messages_list)
            await event.edit(f"✅ پیام جدید اضافه شد!\nتعداد کل پیام‌ها: {len(messages_list)}")

    elif text == ".listmsg":
        if not messages_list:
            await event.edit("⚠️ لیست پیام‌ها خالی است! لطفاً با `.addmsg` پیام اضافه کنید یا `.clearmsg` بزنید.")
            return
        out = "📋 **لیست پیام‌های فعال:**\n\n"
        for i, m in enumerate(messages_list, 1):
            out += f"**{i}.**\n{m}\n{'-'*20}\n"
        await event.edit(out)

    elif text == ".clearmsg":
        messages_list = DEFAULT_MESSAGES.copy()
        save_messages(messages_list)
        await event.edit("🔄 متن‌ها به حالت پیش‌فرض اختصاصی شما برگشتند.")

    elif text == ".status":
        status_text = (
            f"📊 **وضعیت ربات بازگشت ممبر:**\n\n"
            f"▫️ کاربران در صف: `{send_queue.qsize()}`\n"
            f"▫️ ارسال‌های موفق امروز: `{sent_count_today} / {DAILY_SEND_LIMIT}`\n"
            f"▫️ تعداد متون فعال: `{len(messages_list)}`"
        )
        await event.edit(status_text)

async def main():
    if not API_ID or not API_HASH:
        print("[CRITICAL] متغیرهای API_ID یا API_HASH تعریف نشده‌اند!", flush=True)
        return

    if not SESSION_STRING:
        print("[CRITICAL] متغیر RETENTION_SESSION خالی است! لطفاً رشته سشن را در Variables ریل‌وی وارد کنید.", flush=True)
        return

    print("در حال برقراری ارتباط ربات Retention با تلگرام...", flush=True)
    await client.connect()

    if not await client.is_user_authorized():
        print("[CRITICAL] سشن نامعتبر یا منقضی شده است! لطفاً سشن جدید بسازید.", flush=True)
        return

    # شناسایی اولیه کانال در کش تلگرام برای دریافت مطمئن رویدادهای خروج
    try:
        await client.get_entity(TARGET_CHANNEL_ID)
    except Exception as e:
        print(f"[Warning] خطا در شناسایی اولیه کانال: {e}", flush=True)

    print("🚀 ربات Channel-Retention با موفقیت متصل و آنلاین شد!", flush=True)
    asyncio.create_task(queue_worker())
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
