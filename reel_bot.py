import asyncio
import os
import sys
import tempfile
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from reel_maker import build_synced_reel, cut_audio_segment

raw_api_id = os.environ.get("TG_API_ID") or os.environ.get("API_ID") or "0"
API_ID = int(str(raw_api_id).strip() or "0")
API_HASH = (os.environ.get("TG_API_HASH") or os.environ.get("API_HASH") or "").strip()
BOT_TOKEN = (os.environ.get("REEL_BOT_TOKEN") or os.environ.get("BOT_TOKEN") or "").strip()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_PATH = os.path.join(BASE_DIR, "reel_bot_session")
BG_VIDEO_PATH = os.path.join(BASE_DIR, "bg.mp4")

client = TelegramClient(SESSION_PATH, API_ID, API_HASH)


def _log(msg: str):
    print(f"[REEL_BOT] {msg}", file=sys.stderr, flush=True)


def _is_audio_or_voice(msg) -> bool:
    if not msg:
        return False
    if msg.audio or msg.voice:
        return True
    if msg.document and msg.document.mime_type:
        return msg.document.mime_type.startswith("audio/")
    return False


def _is_video_or_photo(msg) -> bool:
    if not msg:
        return False
    if msg.video or msg.photo:
        return True
    if msg.document and msg.document.mime_type:
        return msg.document.mime_type.startswith(("video/", "image/"))
    return False


@client.on(events.NewMessage(pattern=r"^/start(?:\s|$)"))
async def handle_start(event):
    await event.reply(
        "ربات آماده است:\n\n"
        "1️⃣ **برش موزیک (تا ۶۰ ثانیه):**\n"
        "روی موزیک ریپلای کنید: `.cut 00:00 01:00`\n\n"
        "2️⃣ **ثبت بک‌گراند ریلز (ویدئو یا عکس خام):**\n"
        "روی ویدئو/عکس ریپلای کنید: `.setbg`\n\n"
        "3️⃣ **ساخت ریلز با اکولایزر:**\n"
        "روی موزیک ریپلای کنید: `.reel 00:00 01:00`"
    )


@client.on(events.NewMessage(pattern=r"^\.setbg(?:\s|$)"))
async def handle_setbg(event):
    reply = await event.get_reply_message()
    if not _is_video_or_photo(reply):
        await event.reply("❌ ابتدا یک ویدئو یا عکس بفرستید و روی آن `.setbg` بزنید.")
        return

    status = await event.reply("⏳ در حال ذخیره بک‌گراند ریلز...")
    if os.path.exists(BG_VIDEO_PATH):
        os.remove(BG_VIDEO_PATH)

    downloaded = await reply.download_media(file=BG_VIDEO_PATH)
    if (
        downloaded
        and os.path.exists(downloaded)
        and os.path.abspath(downloaded) != os.path.abspath(BG_VIDEO_PATH)
    ):
        os.replace(downloaded, BG_VIDEO_PATH)

    if not os.path.exists(BG_VIDEO_PATH) or os.path.getsize(BG_VIDEO_PATH) == 0:
        await status.edit("❌ ذخیره بک‌گراند ناموفق بود.")
        return

    _log(f"بک‌گراند ذخیره شد: {BG_VIDEO_PATH} ({os.path.getsize(BG_VIDEO_PATH)} bytes)")
    await status.edit("✅ بک‌گراند ریلز ذخیره شد.")


@client.on(events.NewMessage(pattern=r"^\.cut(?:\s+(.+))?$"))
async def handle_cut(event):
    reply = await event.get_reply_message()
    if not _is_audio_or_voice(reply):
        await event.reply("❌ روی یک فایل موزیک ریپلای کنید و بنویسید: `.cut 00:00 01:00`")
        return

    args = (event.pattern_match.group(1) or "").strip().split()
    if len(args) < 2:
        await event.reply("❌ فرمت صحیح: `.cut زمان_شروع زمان_پایان` (مثال: `.cut 00:00 01:00`)")
        return

    start_str, end_str = args[0], args[1]
    status = await event.reply("✂️ در حال برش موزیک...")

    with tempfile.TemporaryDirectory() as tmpdir:
        src_audio = os.path.join(tmpdir, "source_audio")
        out_audio = os.path.join(tmpdir, "cut_segment.mp3")

        downloaded = await reply.download_media(file=src_audio)
        if not downloaded or not os.path.exists(downloaded):
            await status.edit("❌ دانلود فایل موزیک انجام نشد.")
            return

        ok, dur, msg = cut_audio_segment(downloaded, out_audio, start_str, end_str)
        if not ok:
            await status.edit(f"❌ {msg}")
            return

        await event.respond(file=out_audio, message=f"🎵 {msg}")
        await status.delete()


@client.on(events.NewMessage(pattern=r"^\.reel(?:\s+([\s\S]+))?$", func=lambda e: bool(e.text)))
async def handle_reel(event):
    reply = await event.get_reply_message()
    if not _is_audio_or_voice(reply):
        await event.reply("❌ روی فایل موزیک ریپلای کنید و بنویسید: `.reel 00:00 01:00`")
        return

    if not os.path.exists(BG_VIDEO_PATH) or os.path.getsize(BG_VIDEO_PATH) == 0:
        await event.reply("❌ ابتدا یک ویدئو یا عکس خام بدون واترماک بفرستید و با `.setbg` ثبت کنید.")
        return

    raw_arg = (event.pattern_match.group(1) or "").strip()
    time_tokens = raw_arg.split()
    if len(time_tokens) < 2:
        await event.reply("❌ زمان شروع و پایان را وارد کنید؛ مثال: `.reel 00:00 01:00`")
        return

    start_str, end_str = time_tokens[0], time_tokens[1]
    status = await event.reply("🎬 در حال ساخت ریلز با اکولایزر...")
    _log(f"درخواست ساخت ریلز دریافت شد: {start_str} تا {end_str}")

    with tempfile.TemporaryDirectory() as tmpdir:
        src_audio = os.path.join(tmpdir, "track_audio")
        out_video = os.path.join(tmpdir, "final_reel.mp4")

        downloaded = await reply.download_media(file=src_audio)
        if not downloaded or not os.path.exists(downloaded):
            await status.edit("❌ دانلود موزیک ناموفق بود.")
            return

        loop = asyncio.get_running_loop()
        ok, info_msg = await loop.run_in_executor(
            None,
            lambda: build_synced_reel(
                video_path=BG_VIDEO_PATH,
                audio_path=downloaded,
                output_path=out_video,
                start_str=start_str,
                end_str=end_str,
                lyrics_text="",
            ),
        )
        if not ok:
            await status.edit(f"❌ {info_msg}")
            return

        await event.respond(file=out_video, message=f"✅ {info_msg}")
        await status.delete()


async def start_bot_with_flood_retry():
    if not BOT_TOKEN:
        raise RuntimeError("REEL_BOT_TOKEN یا BOT_TOKEN تنظیم نشده است.")

    while True:
        try:
            await client.start(bot_token=BOT_TOKEN)
            _log("Reel bot is running...")
            return
        except FloodWaitError as e:
            wait_sec = int(getattr(e, "seconds", 60)) + 2
            _log(f"FloodWaitError هنگام استارت ربات؛ انتظار به مدت {wait_sec} ثانیه...")
            await asyncio.sleep(wait_sec)


async def main():
    await start_bot_with_flood_retry()
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
