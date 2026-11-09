import os
import asyncio
import random
import json
from datetime import datetime, timezone
from telethon import TelegramClient, events, errors
from telethon.tl.types import InputPeerUser
from telethon.sessions import StringSession

API_ID_STR = os.environ.get("API_ID", "").strip()
API_HASH = os.environ.get("API_HASH", "").strip()
SESSION_STRING = (os.environ.get("RETENTION_SESSION") or os.environ.get("SESSION_STRING", "")).strip()
TARGET_CHANNEL_ID_STR = os.environ.get("TARGET_CHANNEL_ID", "").strip()

API_ID = int(API_ID_STR) if API_ID_STR.isdigit() else 0
TARGET_CHANNEL_ID = int(TARGET_CHANNEL_ID_STR) if TARGET_CHANNEL_ID_STR.lstrip("-").isdigit() else 0

DAILY_SEND_LIMIT = 20
MESSAGES_FILE = "retention_messages.json"

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
failed_count_today = 0
last_error_reason = "بدون خطا"
last_day_reset = datetime.now(timezone.utc).day
currently_processing = None

send_queue = asyncio.Queue()

client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)

async def queue_worker():
    global sent_count_today, failed_count_today, last_error_reason, last_day_reset, currently_processing
    while True:
        item = await send_queue.get()
        user_id = item["user_id"]
        peer = item["peer"]
        currently_processing = user_id
        try:
            current_day = datetime.now(timezone.utc).day
            if current_day != last_day_reset:
                sent_count_today = 0
                failed_count_today = 0
                last_day_reset = current_day

            if sent_count_today >= DAILY_SEND_LIMIT:
                print(f"[Limit] سقف روزانه پر شده است. پیام به {user_id} لغو شد.", flush=True)
                continue

            # تأخیر تصادفی ۲ تا ۴ دقیقه
            delay = random.randint(120, 240)
            print(f"[Worker] کاربر {user_id} در نوبت ارسال. انتظار به مدت {delay} ثانیه...", flush=True)
            await asyncio.sleep(delay)

            msg_text = random.choice(messages_list) if messages_list else random.choice(DEFAULT_MESSAGES)

            try:
                await client.send_message(peer, msg_text)
                sent_count_today += 1
                print(f"[Worker Success] پیام به کاربر {user_id} با موفقیت ارسال شد. ({sent_count_today}/{DAILY_SEND_LIMIT})", flush=True)
            except errors.UserPrivacyRestrictedError:
                failed_count_today += 1
                last_error_reason = f"پی‌وی کاربر {user_id} بسته بود"
                print(f"[Privacy] {last_error_reason}", flush=True)
            except errors.PeerFloodError:
                failed_count_today += 1
                last_error_reason = "محدودیت اسپم تلگرام (PeerFlood)"
                print("[Flood] محدودیت تلگرام! توقف موقت صف به مدت ۴۵ دقیقه...", flush=True)
                await asyncio.sleep(2700)
            except errors.FloodWaitError as e:
                failed_count_today += 1
                last_error_reason = f"محدودیت زمانی ({e.seconds} ثانیه)"
                print(f"[FloodWait] توقف صف برای {e.seconds} ثانیه.", flush=True)
                await asyncio.sleep(e.seconds + 5)
            except Exception as e:
                failed_count_today += 1
                last_error_reason = f"{type(e).__name__}: {str(e)[:40]}"
                print(f"[Send Error] خطا در ارسال به {user_id}: {e}", flush=True)

        finally:
            currently_processing = None
            send_queue.task_done()

# دریافت دقیق لفت‌داده‌ها از Admin Log به همراه Access Hash برای ارسال ۱۰۰٪ تضمینی
async def poll_admin_log():
    global last_error_reason
    print("🔍 اسکنر گزارش خروج کانال (Admin Log) فعال شد...", flush=True)
    last_event_id = 0
    try:
        channel_entity = await client.get_entity(TARGET_CHANNEL_ID)
        async for event in client.iter_admin_log(channel_entity, limit=1, leave=True):
            last_event_id = event.id
            print(f"[AdminLog] نقطه شروع ثبت شد (آخرین آیدی رویداد: {last_event_id})", flush=True)
    except Exception as e:
        last_error_reason = f"خطای دسترسی به کانال: {str(e)[:30]}"
        print(f"[AdminLog Init Error] {e}", flush=True)

    while True:
        await asyncio.sleep(25)
        try:
            channel_entity = await client.get_entity(TARGET_CHANNEL_ID)
            new_events = []
            async for event in client.iter_admin_log(channel_entity, limit=25, leave=True):
                if last_event_id != 0 and event.id <= last_event_id:
                    break
                new_events.append(event)

            if new_events:
                last_event_id = max(e.id for e in new_events)
                for ev in reversed(new_events):
                    user_id = ev.user_id
                    if user_id and user_id not in processed_users:
                        processed_users.add(user_id)
                        # ساخت InputPeerUser با access_hash مستقیم از لاگ کانال
                        if ev.user and getattr(ev.user, 'access_hash', None) is not None:
                            peer = InputPeerUser(ev.user.id, ev.user.access_hash)
                        elif ev.user:
                            peer = ev.user
                        else:
                            peer = user_id

                        print(f"[Detect] خروج کاربر {user_id} ثبت شد! افزودن به صف...", flush=True)
                        await send_queue.put({"user_id": user_id, "peer": peer})
        except Exception as e:
            print(f"[AdminLog Poll Error] {e}", flush=True)

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
            "▫️ `.status` : وضعیت صف، ارسال‌ها و خطاها"
        )
        await event.edit(help_msg)

    elif text == ".resetall":
        messages_list = []
        save_messages(messages_list)
        await event.edit("🗑 **تمام متن‌های قبلی پاک شدند!** حالا متن جدید رو با `.addmsg` اضافه کن.")

    elif text.startswith(".addmsg "):
        new_msg = text[8:].strip()
        if new_msg:
            messages_list.append(new_msg)
            save_messages(messages_list)
            await event.edit(f"✅ پیام جدید اضافه شد!\nتعداد کل پیام‌ها: {len(messages_list)}")

    elif text == ".listmsg":
        if not messages_list:
            await event.edit("⚠️ لیست پیام‌ها خالی است! با `.addmsg` پیام اضافه کنید یا `.clearmsg` بزنید.")
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
        in_timer = f"کاربر {currently_processing} (در تایمر ۲ تا ۴ دقیقه)" if currently_processing else "۰ نفر"
        status_text = (
            f"📊 **وضعیت ربات بازگشت ممبر:**\n\n"
            f"⏳ در حال انتظار تایمر: `{in_timer}`\n"
            f"▫️ نفرات بعدی در صف: `{send_queue.qsize()}`\n"
            f"✅ ارسال‌های موفق امروز: `{sent_count_today} / {DAILY_SEND_LIMIT}`\n"
            f"❌ ارسال‌های ناموفق: `{failed_count_today}`\n"
            f"⚠️ آخرین خطا: `{last_error_reason}`\n"
            f"📝 تعداد متون فعال: `{len(messages_list)}`"
        )
        await event.edit(status_text)

async def main():
    if not API_ID or not API_HASH:
        print("[CRITICAL] متغیرهای API_ID یا API_HASH تعریف نشده‌اند!", flush=True)
        return

    if not SESSION_STRING:
        print("[CRITICAL] متغیر RETENTION_SESSION خالی است!", flush=True)
        return

    print("در حال برقراری ارتباط ربات Retention با تلگرام...", flush=True)
    await client.connect()

    if not await client.is_user_authorized():
        print("[CRITICAL] سشن نامعتبر یا منقضی شده است!", flush=True)
        return

    print("🚀 ربات Channel-Retention با موفقیت متصل و آنلاین شد!", flush=True)
    asyncio.create_task(queue_worker())
    asyncio.create_task(poll_admin_log())
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
