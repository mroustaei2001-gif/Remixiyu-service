import os
import sys
import json
import base64
import asyncio
import re
import io
import random
import subprocess
from datetime import datetime, timezone, timedelta
import aiohttp
from aiohttp import web
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import DocumentAttributeAudio, InputMediaUploadedPhoto
from telethon.tl.functions.messages import SendMediaRequest
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, COMM, APIC
from PIL import Image

IRAN_TZ = timezone(timedelta(hours=3, minutes=30))


def log(msg):
    now_str = datetime.now(IRAN_TZ).strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{now_str}] {msg}", flush=True)


log("Starting remix-poster script...")

API_ID = int(os.getenv('API_ID', '2040'))
API_HASH = os.getenv('API_HASH', 'b18441a1ff607e10a989891a5462e627')
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
STRING_SESSION = os.getenv('STRING_SESSION', '')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '').strip()

# ==========================================
# تنظیمات حالت تست (پس از اتمام تست در Railway مقدار TEST_MODE را false بگذارید)
# ==========================================
TEST_MODE = os.getenv('TEST_MODE', 'true').lower() == 'true'
TEST_CHANNEL = '@xibopay'
MAIN_CHANNEL = os.getenv('TARGET_CHANNEL', '@remixiyu')

TARGET_CHANNEL = TEST_CHANNEL if TEST_MODE else MAIN_CHANNEL
PROXY_CHANNEL = 'iRoProxy'

log(f"Mode: {'TEST' if TEST_MODE else 'PRODUCTION'} | Target Channel: {TARGET_CHANNEL}")

# جدول زمان‌بندی:
SCHEDULE_CONFIG = {
    (10, 0): True,    # ۱۰:۰۰ صبح -> عکس + ۲ دمو و ۲ موزیک کامل
    (14, 0): False,   # ۱۴:۰۰ ظهر -> فقط ۲ دمو و ۲ موزیک کامل
    (18, 0): True,    # ۱۸:۰۰ عصر -> عکس + ۲ دمو و ۲ موزیک کامل
    (22, 0): True,    # ۲۲:۰۰ شب -> عکس + ۲ دمو و ۲ موزیک کامل
    (1, 30): False    # ۰۱:۳۰ بامداد -> فقط ۲ دمو و ۲ موزیک کامل
}

# لیست جدید کانال‌های موزیک
SOURCE_MUSIC_CHANNELS = [
    'ReMiXeQofli',
    'urap_ufarsi',
    'melody9',
    'resanejavon',
    'RiMixaM',
    'Remix',
    'PLAYVIBES'
]
FOREIGN_MUSIC_CHANNEL = 'DEEPHOUSEMUZIX'

# لیست جدید کانال‌های عکس‌دار
SOURCE_PHOTO_CHANNELS = [
    'ahnGamw',
    'PLAYVIBES'
]

# جملات جایگزین مینیمال و خنثی (در صورت نبود کلید AI یا عدم اطمینان)
FALLBACK_MUSIC_CAPTIONS = [
    "یه ریمیکس انتخابی و خوش‌ساخت برای پلی‌لیستت 🎶✨",
    "ترک منتخب این باکس؛ آماده برای پلی کردن 🎧🖤",
    "یه ریمیکس شنیدنی که تکرارش می‌چسبه 🎵✨",
    "انتخاب ویژه این ساعت؛ گوش بده و لذت ببر 🎧🔥"
]

COVER_PATH = "cover.png"
SEEN_FILE = "seen_tracks.txt"
SEEN_PHOTOS_FILE = "seen_photos.txt"
LAST_SLOT_FILE = "last_slot.txt"

user_client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)
bot_client = TelegramClient('bot_session', API_ID, API_HASH)

MUSIC_QUEUE = []
PHOTO_QUEUE = []
SEEN_TRACKS = set()
SEEN_PHOTOS = set()
CACHED_GEMINI_MODEL = None

if os.path.exists(SEEN_FILE):
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            SEEN_TRACKS = set(line.strip() for line in f if line.strip())
        log(f"Loaded {len(SEEN_TRACKS)} tracks from history.")
    except Exception as e:
        log(f"Storage Music Error: {e}")

if os.path.exists(SEEN_PHOTOS_FILE):
    try:
        with open(SEEN_PHOTOS_FILE, "r", encoding="utf-8") as f:
            SEEN_PHOTOS = set(line.strip() for line in f if line.strip())
        log(f"Loaded {len(SEEN_PHOTOS)} photos from history.")
    except Exception as e:
        log(f"Storage Photo Error: {e}")


def save_seen_track(track_key: str):
    SEEN_TRACKS.add(track_key)
    if TEST_MODE:
        return
    try:
        with open(SEEN_FILE, "a", encoding="utf-8") as f:
            f.write(f"{track_key}\n")
    except Exception as e:
        log(f"Save Music Key Error: {e}")


def save_seen_photo(photo_key: str):
    SEEN_PHOTOS.add(photo_key)
    if TEST_MODE:
        return
    try:
        with open(SEEN_PHOTOS_FILE, "a", encoding="utf-8") as f:
            f.write(f"{photo_key}\n")
    except Exception as e:
        log(f"Save Photo Key Error: {e}")


def get_last_processed_slot():
    if os.path.exists(LAST_SLOT_FILE):
        try:
            with open(LAST_SLOT_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass
    return ""


def set_last_processed_slot(slot_key: str):
    if TEST_MODE:
        return
    try:
        with open(LAST_SLOT_FILE, "w", encoding="utf-8") as f:
            f.write(slot_key)
    except Exception as e:
        log(f"Save Slot Error: {e}")


def clean_track_name(title):
    if not title:
        return "Remix"
    title = re.sub(r'@[A-Za-z0-9_]+', '', title)
    title = re.sub(r'https?://\S+', '', title)
    title = re.sub(r'[\(\[\{].*?[\)\]\}]', '', title)
    return title.strip() or "Remix"


def is_promotional_tag(text: str) -> bool:
    if not text:
        return True
    promo_pattern = r'(?:https?://|t\.me/|telegram\.me/|@|www\.|\.(?:com|org|net|ir|me|co)|کانال|channel|remix|ریمیکس)'
    return bool(re.search(promo_pattern, text, re.IGNORECASE))


def get_clean_artist(performer: str) -> str:
    if not performer or is_promotional_tag(performer):
        return ""
    cleaned = re.sub(r'@[A-Za-z0-9_]+', '', performer)
    cleaned = re.sub(r'https?://\S+', '', cleaned)
    cleaned = cleaned.strip()
    return "" if is_promotional_tag(cleaned) else cleaned


async def get_candidate_gemini_models(session: aiohttp.ClientSession) -> list:
    if CACHED_GEMINI_MODEL:
        return [CACHED_GEMINI_MODEL]

    list_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
    candidates = []
    try:
        async with session.get(list_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                data = await resp.json()
                models = data.get("models") or []
                valid_names = [
                    m.get("name", "").replace("models/", "")
                    for m in models
                    if "generateContent" in (m.get("supportedGenerationMethods") or [])
                ]
                flash_models = [n for n in valid_names if "flash" in n.lower()]
                flash_models.sort(key=lambda x: (
                    0 if "latest" in x else (1 if "3" in x else (2 if "2.5" in x else 3)),
                    x
                ))
                candidates = flash_models + [n for n in valid_names if n not in flash_models]
    except Exception as e:
        log(f"List Models Exception: {e}")

    return candidates or ["gemini-flash-latest", "gemini-2.5-flash-lite"]


async def generate_ai_music_description(audio_file_path: str, track_name: str, artist_name: str) -> str:
    """ارسال فایل صوتی به Gemini با تست خودکار مدل‌های فعال و تحلیل JSON."""
    global CACHED_GEMINI_MODEL

    if not GEMINI_API_KEY or not os.path.exists(audio_file_path):
        return random.choice(FALLBACK_MUSIC_CAPTIONS)

    file_size = os.path.getsize(audio_file_path)
    if file_size <= 0 or file_size > 15 * 1024 * 1024:
        return random.choice(FALLBACK_MUSIC_CAPTIONS)

    ext = os.path.splitext(audio_file_path)[1].lower()
    mime_map = {
        ".mp3": "audio/mp3",
        ".ogg": "audio/ogg",
        ".opus": "audio/ogg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
    }
    mime_type = mime_map.get(ext, "audio/mpeg")

    try:
        with open(audio_file_path, "rb") as f:
            b64_audio = base64.b64encode(f.read()).decode("ascii")

        prompt = (
            f"این فایل صوتی یک ریمیکس/آهنگ با عنوان «{track_name}»"
            f"{f' و هنرمند «{artist_name}»' if artist_name else ''} است.\n"
            "ملاک اصلی تو فقط خودِ صدا، لحن خواننده، متن شعر و فضای بیت در فایل صوتی است (نه صرفاً اسم فایل).\n"
            "خروجی را دقیقاً به صورت یک JSON معتبر با این فیلدها برگردان:\n"
            '{\n'
            '  "mood": "حس اصلی صدا (مثلاً nostalgic, happy, dark, romantic, energetic, chill)",\n'
            '  "confidence": "high یا low",\n'
            '  "caption": "یک جمله کوتاه، مینیمال، حسی و خودمانی به زبان فارسی با ۱ یا ۲ ایموجی"\n'
            '}\n\n'
            "قوانین بسیار مهم برای caption:\n"
            "- سبک نقد موسیقی یا گزارش‌گونه ننویس.\n"
            "- از برچسب‌های کلیشه‌ای مثل «فاز سنگین»، «فاز دور دور» و هشتگ اصلاً استفاده نکن.\n"
            "- مثال‌های خوب:\n"
            "  * نوستالژی: یه ریمیکس نوستالژی که می‌برتت تو خاطرات قدیم 📼✨\n"
            "  * شاد: این ریمیکس برای عوض کردن حال‌و‌هوا و انرژی گرفتن عالیه 💃🔥\n"
            "  * دپ/شبونه: این موزیک قفلی برای روزای تنهایی 🎧🌙\n"
            "  * پرانرژی/رپ شبونه: این موزیک برای شب‌های بی‌خوابی حسابی می‌چسبه 🌙🔥\n"
            "- اگر از حس آهنگ مطمئن نبودی، confidence را low بگذار و یک جمله خنثی و مینیمال بنویس."
        )

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": b64_audio,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.55,
                "maxOutputTokens": 200,
                "responseMimeType": "application/json",
            },
        }

        async with aiohttp.ClientSession() as session:
            models_to_try = await get_candidate_gemini_models(session)
            data = None

            for model_name in models_to_try[:6]:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=40)) as resp:
                    if resp.status == 200:
                        CACHED_GEMINI_MODEL = model_name
                        log(f"Working Gemini model locked: {model_name}")
                        data = await resp.json()
                        break
                    else:
                        err_body = await resp.text()
                        log(f"AI HTTP {resp.status} ({model_name}): {err_body[:180]}")

        if not data:
            return random.choice(FALLBACK_MUSIC_CAPTIONS)

        candidates = data.get("candidates") or []
        if candidates:
            parts = ((candidates[0].get("content") or {}).get("parts")) or []
            raw_text = " ".join(p.get("text", "") for p in parts if isinstance(p, dict) and p.get("text")).strip()
            if raw_text:
                raw_text = re.sub(r'^```(?:json)?\s*', '', raw_text)
                raw_text = re.sub(r'\s*```$', '', raw_text)
                parsed = json.loads(raw_text)
                confidence = str(parsed.get("confidence", "high")).lower()
                caption = str(parsed.get("caption", "")).strip()
                mood = str(parsed.get("mood", "")).strip()
                log(f"AI Vibe Analysis -> mood: {mood}, confidence: {confidence}, caption: {caption}")

                if confidence != "low" and caption:
                    first_line = next((ln.strip() for ln in caption.splitlines() if ln.strip()), "")
                    if first_line:
                        return first_line
    except Exception as e:
        log(f"AI Music Description Error: {e}")

    return random.choice(FALLBACK_MUSIC_CAPTIONS)


async def ensure_connection():
    if not user_client.is_connected():
        try:
            await user_client.connect()
        except Exception as e:
            log(f"Reconnect Error: {e}")


async def load_history_from_target():
    global SEEN_TRACKS, SEEN_PHOTOS
    blocked_keywords = [
        "halet khobe",
        "khodam miam mibaramet",
        "ghatle amd",
        "ghahvei",
        "khakestari",
        "sekte",
        "afserdegi",
        "adam barfi",
        "akharin shab"
    ]
    for b in blocked_keywords:
        SEEN_TRACKS.add(b)

    if TEST_MODE:
        log("TEST_MODE active: skipping target channel history sync for faster test.")
        return

    try:
        log(f"Syncing recent tracks & photos from destination channel {TARGET_CHANNEL}...")
        t_count = 0
        p_count = 0
        async for msg in user_client.iter_messages(TARGET_CHANNEL, limit=120):
            if msg.audio:
                for attr in msg.audio.attributes:
                    if isinstance(attr, DocumentAttributeAudio):
                        t = clean_track_name(attr.title or "").lower()
                        if t:
                            SEEN_TRACKS.add(t)
                            SEEN_TRACKS.add(f"{t}_{attr.duration or 0}")
                            t_count += 1
            if msg.text:
                for line in msg.text.splitlines():
                    if "name:" in line.lower():
                        cleaned_line = clean_track_name(line.split(":")[-1]).lower()
                        if cleaned_line:
                            SEEN_TRACKS.add(cleaned_line)
                            t_count += 1

            if msg.photo:
                SEEN_PHOTOS.add(f"photo_id_{msg.photo.id}")
                p_count += 1
            elif msg.media and hasattr(msg.media, 'photo') and msg.media.photo:
                SEEN_PHOTOS.add(f"photo_id_{msg.media.photo.id}")
                p_count += 1

        log(f"Successfully locked {t_count} tracks and {p_count} photos from channel history.")
    except Exception as e:
        log(f"Target History Sync Error: {e}")


async def get_latest_proxy():
    try:
        await ensure_connection()
        async for msg in user_client.iter_messages(PROXY_CHANNEL, limit=5):
            if msg.buttons:
                for row in msg.buttons:
                    for btn in row:
                        if btn.url and ('proxy?' in btn.url):
                            link = btn.url
                            if link.startswith('https://t.me/proxy?'):
                                link = link.replace('https://t.me/proxy?', 'tg://proxy?')
                            return link

            if msg.entities:
                for ent, text in msg.get_entities_text():
                    if hasattr(ent, 'url') and ent.url and ('proxy?' in ent.url):
                        link = ent.url
                        if link.startswith('https://t.me/proxy?'):
                            link = link.replace('https://t.me/proxy?', 'tg://proxy?')
                        return link

            if msg.text:
                found = re.findall(r'(?:https?://t\.me/proxy\?|tg://proxy\?)[^\s<>"\'`]+', msg.text)
                if found:
                    link = found[0]
                    if link.startswith('https://t.me/proxy?'):
                        link = link.replace('https://t.me/proxy?', 'tg://proxy?')
                    return link
    except Exception as e:
        log(f"Proxy Fetch Error: {e}")

    return "https://t.me/iRoProxy"


def update_metadata_and_cover(file_path, title, artist, cover_file):
    try:
        fixed_path = file_path + ".fixed.mp3"
        repair_cmd = [
            "ffmpeg", "-y", "-i", file_path,
            "-codec:a", "copy",
            "-map_metadata", "-1",
            fixed_path
        ]
        res = subprocess.run(repair_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if res.returncode == 0 and os.path.exists(fixed_path):
            os.replace(fixed_path, file_path)

        try:
            audio = MP3(file_path, ID3=ID3)
        except Exception:
            audio = MP3(file_path)
            audio.add_tags()

        if audio.tags is None:
            audio.add_tags()

        audio.tags.delall('APIC')
        clean_channel = TARGET_CHANNEL.replace('@', '').replace('https://t.me/', '')
        audio.tags.add(TIT2(encoding=3, text=title))
        audio.tags.add(TPE1(encoding=3, text=artist))
        audio.tags.add(COMM(encoding=3, lang='eng', desc='', text=f'https://t.me/{clean_channel}'))

        if os.path.exists(cover_file):
            with Image.open(cover_file) as img:
                img = img.convert('RGB')
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='JPEG', quality=95)
                img_data = img_byte_arr.getvalue()

            audio.tags.add(APIC(
                encoding=3,
                mime='image/jpeg',
                type=3,
                desc='Cover',
                data=img_data
            ))
        audio.save(v2_version=3)
    except Exception as e:
        log(f"Tag Error: {e}")


def create_demo_voice_ffmpeg(input_path, output_path, start_sec=40, duration_sec=40):
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start_sec),
        "-t", str(duration_sec),
        "-i", input_path,
        "-vn",
        "-c:a", "libopus",
        "-b:a", "48k",
        "-ar", "48000",
        "-ac", "1",
        "-application", "voip",
        "-af", "afade=t=in:ss=0:d=1,afade=t=out:st=38:d=2",
        output_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return start_sec


async def scan_photos_cycle():
    while True:
        try:
            await ensure_connection()
            if len(PHOTO_QUEUE) < 6:
                sources = list(SOURCE_PHOTO_CHANNELS)
                random.shuffle(sources)

                for ch in sources:
                    if len(PHOTO_QUEUE) >= 6:
                        break
                    try:
                        count = 0
                        async for msg in user_client.iter_messages(ch, limit=300):
                            count += 1
                            if count % 30 == 0:
                                await asyncio.sleep(0.05)

                            photo_obj = None
                            if msg.photo:
                                photo_obj = msg.photo
                            elif msg.media and hasattr(msg.media, 'photo') and msg.media.photo:
                                photo_obj = msg.media.photo

                            if not photo_obj:
                                continue

                            caption = (msg.text or "").strip()
                            check_text = caption
                            if ch.lower() == 'playvibes':
                                check_text = re.sub(r'https?://(?:t\.me|telegram\.me)/(?:c/)?PLAYVIBES(?:/\d+)?', '', check_text, flags=re.IGNORECASE)
                                check_text = re.sub(r't\.me/PLAYVIBES(?:/\d+)?', '', check_text, flags=re.IGNORECASE)
                                check_text = re.sub(r'@PLAYVIBES', '', check_text, flags=re.IGNORECASE)

                            if re.search(r'(https?://|t\.me/|joinchat)', check_text, re.IGNORECASE):
                                continue

                            photo_id_key = f"photo_id_{photo_obj.id}"
                            photo_msg_key = f"photo_{msg.chat_id}_{msg.id}"

                            if photo_id_key in SEEN_PHOTOS or photo_msg_key in SEEN_PHOTOS:
                                continue

                            save_seen_photo(photo_id_key)
                            save_seen_photo(photo_msg_key)

                            PHOTO_QUEUE.append({
                                'chat': ch,
                                'id': msg.id,
                                'key': photo_id_key
                            })
                            log(f"Photo Queued from {ch} (Total: {len(PHOTO_QUEUE)})")

                            if len(PHOTO_QUEUE) >= 6:
                                break
                    except Exception as err:
                        log(f"Photo Channel Error on {ch}: {err}")
        except Exception as e:
            log(f"Photo Cycle Error: {e}")

        await asyncio.sleep(60)


async def scan_music_cycle():
    while True:
        try:
            await ensure_connection()
            if len(MUSIC_QUEUE) < 8:
                all_channels = list(SOURCE_MUSIC_CHANNELS)
                if FOREIGN_MUSIC_CHANNEL not in all_channels:
                    all_channels.append(FOREIGN_MUSIC_CHANNEL)

                collected_candidates = []

                for ch in all_channels:
                    try:
                        async for msg in user_client.iter_messages(ch, limit=15):
                            if not msg.audio:
                                continue

                            duration = 0
                            raw_title = ""
                            raw_performer = ""
                            for attr in msg.audio.attributes:
                                if isinstance(attr, DocumentAttributeAudio):
                                    duration = attr.duration or 0
                                    raw_title = attr.title or ""
                                    raw_performer = attr.performer or ""

                            if duration < 100 or duration > 600:
                                continue

                            if any(w in raw_title.lower() for w in ['demo', 'دمو', 'preview']):
                                continue

                            clean_title = clean_track_name(raw_title).lower()
                            track_key = f"{clean_title}_{duration}"

                            is_duplicate = False
                            if track_key in SEEN_TRACKS or clean_title in SEEN_TRACKS:
                                is_duplicate = True
                            else:
                                for seen in list(SEEN_TRACKS):
                                    if len(seen) > 4 and (seen in clean_title or clean_title in seen):
                                        is_duplicate = True
                                        break

                            if is_duplicate:
                                continue

                            is_foreign = (ch == FOREIGN_MUSIC_CHANNEL)
                            collected_candidates.append({
                                'chat': ch,
                                'id': msg.id,
                                'is_foreign': is_foreign,
                                'date': msg.date,
                                'key': track_key,
                                'title': raw_title,
                                'performer': raw_performer,
                                'duration': duration,
                                'channel': ch
                            })
                    except Exception as ch_err:
                        log(f"Music Scan Channel Error on {ch}: {ch_err}")

                collected_candidates.sort(key=lambda x: x['date'], reverse=True)

                for item in collected_candidates:
                    if len(MUSIC_QUEUE) >= 10:
                        break
                    save_seen_track(item['key'])
                    MUSIC_QUEUE.append(item)
                    log(f"Music Queued (Newest): {item['title']} ({item['duration']}s) from {item['channel']} (Total: {len(MUSIC_QUEUE)})")

        except Exception as e:
            log(f"Music Cycle Error: {e}")

        await asyncio.sleep(60)


async def broadcast_package(include_photo: bool, label: str) -> bool:
    log(f"--- Triggering broadcast for {label} (Photo: {include_photo}) ---")
    await ensure_connection()

    retry_wait = 0
    while (len(MUSIC_QUEUE) < 2 or (include_photo and len(PHOTO_QUEUE) < 1)) and retry_wait < 12:
        await asyncio.sleep(5 if TEST_MODE else 10)
        retry_wait += 1

    if len(MUSIC_QUEUE) < 2:
        log("Not enough music in queue yet.")
        return False

    clean_target = TARGET_CHANNEL.replace('@', '').replace('https://t.me/', '')
    channel_link = f"https://t.me/{clean_target}"

    temp_photo = None
    photo_caption = ""
    if include_photo and len(PHOTO_QUEUE) >= 1:
        p_item = PHOTO_QUEUE.pop(0)
        try:
            fresh_photo_msg = await user_client.get_messages(p_item['chat'], ids=p_item['id'])
            if fresh_photo_msg and fresh_photo_msg.media:
                temp_photo = f"photo_{p_item['id']}.jpg"
                await user_client.download_media(fresh_photo_msg, file=temp_photo)
                photo_caption = f'<blockquote><a href="{channel_link}"><b>🆔 @{clean_target}</b></a></blockquote>'
        except Exception as pe:
            log(f"Photo Fresh Download Error: {pe}")

    prepared_tracks = []
    for idx in range(2):
        m_item = MUSIC_QUEUE.pop(0)
        try:
            fresh_music_msg = await user_client.get_messages(m_item['chat'], ids=m_item['id'])
            if not fresh_music_msg or not fresh_music_msg.audio:
                continue

            raw_title = m_item.get('title') or "New Remix"
            raw_performer = m_item.get('performer') or ""
            duration = m_item.get('duration') or 0

            track_name = clean_track_name(raw_title)
            valid_artist = get_clean_artist(raw_performer)

            if valid_artist:
                display_title = f"{track_name} - @{clean_target}"
                display_performer = valid_artist
            else:
                display_title = track_name
                display_performer = f"T.me/{clean_target}"

            temp_full = f"full_{fresh_music_msg.id}.mp3"
            temp_demo = f"demo_{fresh_music_msg.id}.ogg"

            await user_client.download_media(fresh_music_msg, file=temp_full)
            update_metadata_and_cover(temp_full, display_title, display_performer, COVER_PATH)

            # بخش دمو دقیقاً بدون تغییر
            start_sec = create_demo_voice_ffmpeg(temp_full, temp_demo, start_sec=40, duration_sec=40)

            ai_desc = await generate_ai_music_description(
                audio_file_path=temp_demo if os.path.exists(temp_demo) else temp_full,
                track_name=track_name,
                artist_name=valid_artist,
            )

            proxy_link = await get_latest_proxy()
            m, s = divmod(start_sec, 60)
            timestamp_str = f"{m:02d}:{s:02d}"

            caption_demo = (
                f"<b>name: {track_name}</b>\n"
                f"<b>Demo⚠️⏯️</b>\n\n"
                f'<blockquote><a href="{channel_link}"><b>🆔 @{clean_target}</b></a></blockquote>\n\n'
                f"<b>🛑O.file👇</b>"
            )

            caption_full = (
                f"<b>name: {track_name}</b>\n"
                f"<b>full music ✅️⏯️</b>\n"
                f'<a href="{proxy_link}"><b>proxy</b></a>\n\n'
                f"<b>🎧 پارت دمو (لمس کنید) ⇦ {timestamp_str}</b>\n\n"
                f"<blockquote><b>{ai_desc}</b></blockquote>\n"
                f'<blockquote><a href="{channel_link}"><b>🎷&nbsp;&nbsp;معرفی بهترین ریمیکسها&nbsp;&nbsp;🎼</b></a></blockquote>\n'
                f"<blockquote><b>🆔 @{clean_target}</b></blockquote>"
            )


            prepared_tracks.append({
                "temp_demo": temp_demo,
                "caption_demo": caption_demo,
                "temp_full": temp_full,
                "caption_full": caption_full,
                "duration": duration,
                "display_title": display_title,
                "display_performer": display_performer
            })
        except Exception as m_err:
            log(f"Music Fresh Download Error for {m_item.get('title')}: {m_err}")

    if not prepared_tracks:
        return False

    try:
        log(f"Broadcasting package to {TARGET_CHANNEL}...")

        if temp_photo and os.path.exists(temp_photo):
            uploaded_photo = await bot_client.upload_file(temp_photo)
            target_peer = await bot_client.get_input_entity(TARGET_CHANNEL)
            caption_text, entities = await bot_client._parse_message_text(photo_caption, 'html')

            await bot_client(SendMediaRequest(
                peer=target_peer,
                media=InputMediaUploadedPhoto(file=uploaded_photo, spoiler=True),
                message=caption_text,
                entities=entities,
                silent=True
            ))

        for t in prepared_tracks:
            await bot_client.send_file(
                TARGET_CHANNEL,
                t["temp_demo"],
                caption=t["caption_demo"],
                parse_mode='html',
                voice_note=True,
                silent=True
            )

            await bot_client.send_file(
                TARGET_CHANNEL,
                t["temp_full"],
                caption=t["caption_full"],
                parse_mode='html',
                silent=True,
                thumb=COVER_PATH if os.path.exists(COVER_PATH) else None,
                attributes=[DocumentAttributeAudio(duration=t["duration"], title=t["display_title"], performer=t["display_performer"])]
            )

        log(f"Broadcast successful for {label}!")
        return True
    finally:
        if temp_photo and os.path.exists(temp_photo):
            try: os.remove(temp_photo)
            except Exception: pass
        for t in prepared_tracks:
            if os.path.exists(t.get("temp_demo", "")):
                try: os.remove(t["temp_demo"])
                except Exception: pass
            if os.path.exists(t.get("temp_full", "")):
                try: os.remove(t["temp_full"])
                except Exception: pass


async def publisher_worker():
    if TEST_MODE:
        log("TEST_MODE active: waiting for queues to fill, then sending 1 immediate test batch...")
        test_sent = False
        while not test_sent:
            try:
                if len(MUSIC_QUEUE) >= 2 and len(PHOTO_QUEUE) >= 1:
                    test_sent = await broadcast_package(include_photo=True, label="IMMEDIATE_TEST")
                    if test_sent:
                        log("TEST_MODE completed! Check @xibopay. Set TEST_MODE=false to switch to @remixiyu.")
                        break
            except Exception as e:
                log(f"Test Publisher Error: {e}")
            await asyncio.sleep(5)
        while True:
            await asyncio.sleep(3600)

    last_processed_slot = get_last_processed_slot()

    while True:
        try:
            now = datetime.now(IRAN_TZ)
            current_hour = now.hour
            current_minute = now.minute

            matched_slot = None
            include_photo = False

            for (sh, sm), has_photo in SCHEDULE_CONFIG.items():
                if current_hour == sh and sm <= current_minute <= sm + 5:
                    matched_slot = (sh, sm)
                    include_photo = has_photo
                    break

            if matched_slot is not None:
                sh, sm = matched_slot
                slot_key = f"{now.strftime('%Y-%m-%d')}_{sh:02d}_{sm:02d}"

                if last_processed_slot != slot_key:
                    success = await broadcast_package(include_photo=include_photo, label=f"{sh:02d}:{sm:02d}")
                    if success:
                        last_processed_slot = slot_key
                        set_last_processed_slot(slot_key)

        except Exception as e:
            log(f"Publisher Worker Error: {e}")

        await asyncio.sleep(20)


async def handle_ping(request):
    return web.Response(text="OK")


async def run_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    app.router.add_get('/health', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    log(f"Keep-Alive Server listening on port {port}...")


async def main():
    await run_server()

    log("Connecting user client...")
    await user_client.start()

    if not await user_client.is_user_authorized():
        log("Auth Error: STRING_SESSION is unauthorized!")
        return

    me = await user_client.get_me()
    log(f"User Client connected successfully as @{me.username or me.id}!")

    log("Connecting channel bot...")
    await bot_client.start(bot_token=BOT_TOKEN)
    bot_info = await bot_client.get_me()
    log(f"Bot Client connected successfully as @{bot_info.username}!")

    await load_history_from_target()

    await asyncio.gather(
        scan_photos_cycle(),
        scan_music_cycle(),
        publisher_worker()
    )


if __name__ == '__main__':
    asyncio.run(main())
