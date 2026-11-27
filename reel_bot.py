import asyncio
import os
import tempfile
from telethon import TelegramClient, events
from reel_maker import (
    build_synced_reel,
    cut_audio_segment,
    test_voicemaker_transcription,
)

API_ID = int(os.environ.get("TG_API_ID", "0"))
API_HASH = os.environ.get("TG_API_HASH", "")
BOT_TOKEN = os.environ.get("REEL_BOT_TOKEN", "")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_PATH = os.path.join(BASE_DIR, "reel_bot_session")
BG_VIDEO_PATH = os.path.join(BASE_DIR, "bg.mp4")

client = TelegramClient(SESSION_PATH, API_ID, API_HASH)


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
        "1️⃣ **برش موزیک (تا ۶۰ ثانیه) و تست خودکار تبدیل متن:**\n"
        "روی فایل موزیک ریپلای کنید و بنویسید:\n"
        "`.cut 00:20 01:05`\n\n"
        "2️⃣ **ثبت ویدئوی خام بدون واترماک:**\n"
        "روی ویدئو ریپلای کنید و بنویسید:\n"
        "`.setbg`\n\n"
        "3️⃣ **ساخت ریلز نهایی با متن تاییدشده:**\n"
        "روی فایل موزیک ریپلای کنید و بنویسید:\n"
        "`.reel 00:20 01:05 | متن تاییدشده با ایموجی`"
    )


@client.on(events.NewMessage(pattern=r"^\.setbg(?:\s|$)"))
async def handle_setbg(event):
    reply = await event.get_reply_message()
    if not _is_video_or_photo(reply):
        await event.reply("❌ ابتدا یک ویدئو یا عکس بفرستید و روی آن `.setbg` بزنید.")
        return

    status = await event.reply("⏳ در حال ذخیره ویدئوی پس‌زمینه...")
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
        await status.edit("❌ ذخیره ویدئوی پس‌زمینه ناموفق بود.")
        return

    await status.edit("✅ ویدئوی پس‌زمینه ذخیره شد.")


@client.on(events.NewMessage(pattern=r"^\.cut(?:\s+(.+))?$"))
async def handle_cut(event):
    reply = await event.get_reply_message()
    if not _is_audio_or_voice(reply):
        await event.reply("❌ روی یک فایل موزیک ریپلای کنید و بنویسید: `.cut 00:15 00:55`")
        return

    args = (event.pattern_match.group(1) or "").strip().split()
    if len(args) < 2:
        await event.reply("❌ فرمت صحیح: `.cut زمان_شروع زمان_پایان` (مثال: `.cut 00:15 00:55`)")
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
                f"پس از تایید، با `.reel {start_str} {end_str} | متن_تاییدشده` ریلز را بسازید."
            )
        else:
            caption = (
                f"🎵 برش {dur:.0f} ثانیه‌ای آماده شد.\n"
                f"⚠️ تست خودکار سایت نتیجه نداد: {site_msg}\n"
                f"لطفاً فایل را دستی در سایت تبدیل کنید و بعد با:\n"
                f"`.reel {start_str} {end_str} | متن_تاییدشده`\n"
                f"ریلز را بسازید."
            )

        await event.respond(file=out_audio, message=caption)
        await status.delete()


@client.on(events.NewMessage(pattern=r"^\.reel(?:\s+(.+))?$", func=lambda e: bool(e.text)))
async def handle_reel(event):
    reply = await event.get_reply_message()
    if not _is_audio_or_voice(reply):
        await event.reply(
            "❌ روی فایل موزیک ریپلای کنید و بنویسید:\n"
            "`.reel 00:20 00:50 | متن تاییدشده با ایموجی`"
        )
        return

    if not os.path.exists(BG_VIDEO_PATH) or os.path.getsize(BG_VIDEO_PATH) == 0:
        await event.reply("❌ ابتدا یک ویدئوی خام بدون واترماک بفرستید و با `.setbg` ثبت کنید.")
        return

    raw_arg = (event.pattern_match.group(1) or "").strip()
    if "|" in raw_arg:
        time_part, lyrics_text = raw_arg.split("|", 1)
        lyrics_text = lyrics_text.strip()
    else:
        time_part, lyrics_text = raw_arg, ""

    time_tokens = time_part.strip().split()
    if len(time_tokens) < 2:
        await event.reply("❌ زمان شروع و پایان را وارد کنید؛ مثال: `.reel 00:20 00:50 | متن`")
        return

    start_str, end_str = time_tokens[0], time_tokens[1]
    status = await event.reply("🎬 در حال ساخت ریلز با سینک ریتماتیک و واترماک ثابت...")

    with tempfile.TemporaryDirectory() as tmpdir:
        src_audio = os.path.join(tmpdir, "track_audio")
        out_video = os.path.join(tmpdir, "final_reel.mp4")

        downloaded = await reply.download_media(file=src_audio)
        if not downloaded or not os.path.exists(downloaded):
            await status.edit("❌ دانلود موزیک ناموفق بود.")
            return

        ok, info_msg = build_synced_reel(
            video_path=BG_VIDEO_PATH,
            audio_path=downloaded,
            output_path=out_video,
            start_str=start_str,
            end_str=end_str,
            lyrics_text=lyrics_text,
        )
        if not ok:
            await status.edit(f"❌ {info_msg}")
            return

        await event.respond(file=out_video, message=f"✅ {info_msg}")
        await status.delete()


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("REEL_BOT_TOKEN تنظیم نشده است.")
    await client.start(bot_token=BOT_TOKEN)
    print("Reel bot is running...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
