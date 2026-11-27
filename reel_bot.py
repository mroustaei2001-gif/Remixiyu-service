import os
import asyncio
import tempfile
from telethon import TelegramClient, events
from reel_maker import build_reel_video

API_ID_STR = os.environ.get("API_ID", "").strip()
API_HASH = os.environ.get("API_HASH", "").strip()
REEL_BOT_TOKEN = os.environ.get("REEL_BOT_TOKEN", "").strip()
ADMIN_USER_ID_STR = os.environ.get("ADMIN_USER_ID", "").strip()

API_ID = int(API_ID_STR) if API_ID_STR.isdigit() else 0
ADMIN_USER_ID = int(ADMIN_USER_ID_STR) if ADMIN_USER_ID_STR.isdigit() else 0

BG_VIDEO_PATH = "bg.mp4"


def is_authorized(sender_id: int) -> bool:
    if ADMIN_USER_ID == 0:
        return True
    return sender_id == ADMIN_USER_ID


async def main():
    if not API_ID or not API_HASH or not REEL_BOT_TOKEN:
        print("[ReelBot] متغیر REEL_BOT_TOKEN تنظیم نشده است؛ این ماژول غیرفعال ماند.", flush=True)
        while True:
            await asyncio.sleep(3600)

    bot = TelegramClient("reel_bot_session", API_ID, API_HASH)
    await bot.start(bot_token=REEL_BOT_TOKEN)
    print("🎬 ربات مستقل سازنده ریلز (ReelBot) آنلاین شد!", flush=True)

    @bot.on(events.NewMessage(pattern=r"^/start$"))
    async def start_handler(event):
        if not is_authorized(event.sender_id):
            return
        await event.reply(
            "🎬 **ربات سازنده ریلز اینستاگرام (`1080x1920`) آماده است!**\n\n"
            "1️⃣ فایل موزیک یا ریمیکس را بفرستید.\n"
            "2️⃣ روی آن ریپلای کنید و بازه زمانی (حداکثر ۶۰ ثانیه) را بنویسید:\n"
            "`.reel 00:35 01:20`\n\n"
            "3️⃣ برای تغییر ویدئوی پس‌زمینه، یک ویدئوی کوتاه بفرستید و روی آن ریپلای کنید:\n"
            "`.setbg`"
        )

    @bot.on(events.NewMessage(pattern=r"^\.setbg$"))
    async def set_bg_handler(event):
        if not is_authorized(event.sender_id):
            return
        reply = await event.get_reply_message()
        if not reply or not reply.media:
            await event.reply("⚠️ روی یک فایل ویدئو یا عکس ریپلای کنید و `.setbg` بزنید.")
            return
        status = await event.reply("⏳ در حال ذخیره پس‌زمینه جدید...")
        await reply.download_media(file=BG_VIDEO_PATH)
        await status.edit("✅ پس‌زمینه ریلز با موفقیت به‌روز شد!")

    @bot.on(events.NewMessage(pattern=r"^\.reel\s+(.+)$"))
    async def make_reel_handler(event):
        if not is_authorized(event.sender_id):
            return

        reply = await event.get_reply_message()
        if not reply or not reply.media:
            await event.reply("⚠️ لطفاً روی فایل موزیک ریپلای کنید. مثال:\n`.reel 00:30 01:15`")
            return

        raw_args = event.pattern_match.group(1).strip()
        hook_text = ""
        if "|" in raw_args:
            time_part, hook_text = raw_args.split("|", 1)
        else:
            time_part = raw_args

        times = time_part.strip().split()
        if len(times) != 2:
            await event.reply("⚠️ فرمت دستور اشتباه است. مثال درست:\n`.reel 00:30 01:15`")
            return

        start_str, end_str = times[0], times[1]
        status_msg = await event.reply("⏳ در حال برش موزیک و ساخت ویدئوی ریلز (`1080x1920`)...")

        with tempfile.TemporaryDirectory() as tmpdir:
            audio_file = os.path.join(tmpdir, "input_audio.mp3")
            out_video = os.path.join(tmpdir, "remixiyu_reel.mp4")

            try:
                await reply.download_media(file=audio_file)
                ok, info = await asyncio.to_thread(
                    build_reel_video,
                    audio_file,
                    out_video,
                    start_str,
                    end_str,
                    BG_VIDEO_PATH,
                    hook_text,
                )

                if not ok:
                    await status_msg.edit(f"❌ {info}")
                    return

                await bot.send_file(
                    event.chat_id,
                    out_video,
                    caption=(
                        f"✅ **{info}**\n"
                        f"⏱ بازه: `{start_str}` تا `{end_str}`\n"
                        f"📌 آماده برای بررسی و انتشار در اینستاگرام"
                    ),
                    supports_streaming=True,
                )
                await status_msg.delete()
            except Exception as e:
                await status_msg.edit(f"❌ خطا در پردازش: `{str(e)[:120]}`")

    await bot.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
