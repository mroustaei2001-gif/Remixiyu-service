import asyncio
import os
import sys
import tempfile
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from reel_maker import (
    CUSTOM_FONT_PATH,
    FONTS_DIR,
    build_synced_reel,
    cut_audio_segment,
    test_voicemaker_transcription,
)

raw_api_id = os.environ.get("TG_API_ID") or os.environ.get("API_ID") or "0"
API_ID = int(str(raw_api_id).strip() or "0")
API_HASH = (os.environ.get("TG_API_HASH") or os.environ.get("API_HASH") or "").strip()
BOT_TOKEN = (os.environ.get("REEL_BOT_TOKEN") or os.environ.get("BOT_TOKEN") or "").strip()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_PATH = os.path.join(BASE_DIR, "reel_bot_session")
BG_VIDEO_PATH = os.path.join(BASE_DIR, "bg.mp4")
MANUAL_TEXT_PATH = os.path.join(BASE_DIR, "manual_lyrics.txt")

client = TelegramClient(SESSION_PATH, API_ID, API_HASH)


def _log(msg: str):
    print(f"[REEL_BOT] {msg}", file=sys.stderr, flush=True)


def _save_manual_text(text: str):
    with open(MANUAL_TEXT_PATH, "w", encoding="utf-8") as f:
        f.write(text.strip())


def _load_manual_text() -> str:
    if os.path.exists(MANUAL_TEXT_PATH):
        try:
            with open(MANUAL_TEXT_PATH, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            return ""
    return ""


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


def _is_font_file(msg) -> bool:
    if not msg or not msg.document:
        return False
    fname = ""
    for attr in msg.document.attributes:
        if hasattr(attr, "file_name") and attr.file_name:
            fname = attr.file_name.lower()
            break
    return fname.endswith((".ttf", ".otf"))


@client.on(events.NewMessage(pattern=r"^/start(?:\s|$)"))
async def handle_start(event):
    await event.reply(
        "ربات آماده است:\n\n"
        "1️⃣ **برش موزیک (تا ۶۰ ثانیه) و تست سایت:**\n"
        "روی موزیک ریپلای کنید: `.cut 00:00 01:00`\n\n"
        "2️⃣ **ثبت بک‌گراند ریلز (ویدئو یا عکس خام):**\n"
        "روی ویدئو/عکس ریپلای کنید: `.setbg`\n\n"
        "3️⃣ **ثبت فونت دلخواه (اختیاری):**\n"
        "روی فایل `.ttf` یا `.otf` ریپلای کنید: `.setfont`\n"
        "(بازگشت به فونت ظریف پیش‌فرض: `.resetfont`)\n\n"
        "4️⃣ **ثبت متن دستی (ساده یا زمان‌بندی‌شده):**\n"
        "`.settext متن خط اول`\n"
        "یا با زمان دقیق:\n"
        "`.settext`\n"
        "`00:02 خط اول`\n"
        "`00:06 خط دوم`\n\n"
        "5️⃣ **ساخت ریلز:**\n"
        "روی موزیک ریپلای کنید: `.reel 00:00 01:00`"
    )


@client.on(events.NewMessage(pattern=r"^\.setfont(?:\s|$)"))
async def handle_setfont(event):
    reply = await event.get_reply_message()
    if not _is_font_file(reply):
        await event.reply("❌ روی یک فایل فونت (`.ttf` یا `.otf`) ریپلای کنید و بنویسید `.setfont`")
        return

    os.makedirs(FONTS_DIR, exist_ok=True)
    if os.path.exists(CUSTOM_FONT_PATH):
        os.remove(CUSTOM_FONT_PATH)

    downloaded = await reply.download_media(file=CUSTOM_FONT_PATH)
    if (
        downloaded
        and os.path.exists(downloaded)
        and os.path.abspath(downloaded) != os.path.abspath(CUSTOM_FONT_PATH)
    ):
        os.replace(downloaded, CUSTOM_FONT_PATH)

    if not os.path.exists(CUSTOM_FONT_PATH) or os.path.getsize(CUSTOM_FONT_PATH) < 5000:
        await event.reply("❌ ذخیره فونت ناموفق بود.")
        return

    await event.reply("✅ فونت دلخواه ثبت شد و با سایز ظریف مینیمال استفاده می‌شود.")


@client.on(events.NewMessage(pattern=r"^\.resetfont(?:\s|$)"))
async def handle_resetfont(event):
    if os.path.exists(CUSTOM_FONT_PATH):
        os.remove(CUSTOM_FONT_PATH)
    await event.reply("✅ فونت به حالت ظریف و مینیمال پیش‌فرض بازگشت.")


@client.on(events.NewMessage(pattern=r"^\.settext(?:\s+([\s\S]+))?$"))
async def handle_settext(event):
    manual_txt = (event.pattern_match.group(1) or "").strip()
    if not manual_txt:
        reply = await event.get_reply_message()
        if reply and getattr(reply, "raw_text", ""):
            manual_txt = reply.raw_text.strip()

    if not manual_txt:
        await event.reply("❌ متن را بعد از `.settext` بنویسید یا روی یک پیام متنی ریپلای کنید.")
        return

    _save_manual_text(manual_txt)
    await event.reply("✅ متن دستی ثبت شد. حالا روی موزیک ریپلای کنید و `.reel 00:00 01:00` بزنید.")


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
    status = await event.reply("✂️ در حال برش موزیک و تست تبدیل متن در سایت...")

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

        site_ok, site_msg = test_voicemaker_transcription(out_audio)
        if site_ok:
            caption = (
                f"🎵 برش {dur:.0f} ثانیه‌ای آماده شد.\n"
                f"✅ متن دریافت‌شده از سایت:\n{site_msg}\n\n"
                f"متن را با `.settext متن` ثبت کنید و بعد `.reel {start_str} {end_str}` بزنید."
            )
        else:
            caption = (
                f"🎵 برش {dur:.0f} ثانیه‌ای آماده شد.\n"
                f"⚠️ تست خودکار سایت نتیجه نداد: {site_msg}\n"
                f"متن را با `.settext متن` ثبت کنید و بعد با:\n"
                f"`.reel {start_str} {end_str}`\n"
                f"ریلز را بسازید."
            )

        await event.respond(file=out_audio, message=caption)
        await status.delete()


@client.on(events.NewMessage(pattern=r"^\.reel(?:\s+([\s\S]+))?$", func=lambda e: bool(e.text)))
async def handle_reel(event):
    reply = await event.get_reply_message()
    if not _is_audio_or_voice(reply):
        await event.reply(
            "❌ روی فایل موزیک ریپلای کنید و بنویسید:\n"
            "`.reel 00:00 01:00` یا `.reel 00:00 01:00 | متن`"
        )
        return

    if not os.path.exists(BG_VIDEO_PATH) or os.path.getsize(BG_VIDEO_PATH) == 0:
        await event.reply("❌ ابتدا یک ویدئو یا عکس خام بدون واترماک بفرستید و با `.setbg` ثبت کنید.")
        return

    raw_arg = (event.pattern_match.group(1) or "").strip()
    if "|" in raw_arg:
        time_part, inline_lyrics = raw_arg.split("|", 1)
        lyrics_text = inline_lyrics.strip()
    else:
        time_part, lyrics_text = raw_arg, _load_manual_text()

    time_tokens = time_part.strip().split()
    if len(time_tokens) < 2:
        await event.reply("❌ زمان شروع و پایان را وارد کنید؛ مثال: `.reel 00:00 01:00`")
        return

    start_str, end_str = time_tokens[0], time_tokens[1]
    status = await event.reply("🎬 در حال ساخت ریلز با فونت ظریف مینیمال و سینک خواننده...")
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
                lyrics_text=lyrics_text,
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
