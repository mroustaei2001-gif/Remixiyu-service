import math
import os
import re
import struct
import subprocess
import sys
import tempfile
import requests
from PIL import Image, ImageDraw, ImageFont

try:
    import arabic_reshaper  # type: ignore
except Exception:
    arabic_reshaper = None

try:
    from bidi.algorithm import get_display  # type: ignore
except Exception:
    get_display = None

TG_TEXT = "t.me/remixiyu"
IG_TEXT = "remixiyu"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(BASE_DIR, "fonts")
CUSTOM_FONT_PATH = os.path.join(FONTS_DIR, "CustomUserFont.ttf")
AUTO_FONT_PATH = os.path.join(FONTS_DIR, "PersianMinimalFont.ttf")
TG_LOGO_PATH = os.path.join(BASE_DIR, "tg_logo.png")
IG_LOGO_PATH = os.path.join(BASE_DIR, "ig_logo.png")

# فونت‌های ظریف و خوش‌فرم فارسی (Medium/Regular) برای استایل کوچک و مینیمال
FONT_DOWNLOAD_URLS = [
    "https://github.com/rastikerdar/vazirmatn/raw/master/fonts/ttf/Vazirmatn-Medium.ttf",
    "https://github.com/rastikerdar/vazirmatn/raw/master/fonts/ttf/Vazirmatn-Regular.ttf",
    "https://github.com/google/fonts/raw/main/ofl/notosansarabic/static/NotoSansArabic-Medium.ttf",
]

MAX_DURATION = 60
WIDTH = 720
HEIGHT = 1280
FPS = 20
WM_TEXT_ALPHA = 102      # حدود ۴۰ درصد شفافیت برای متن واترماک
WM_ICON_OPACITY = 0.82   # وضوح مناسب آیکون‌های تلگرام و اینستاگرام
MINIMAL_FONT_SIZE = 28   # سایز کوچک، ریز و مینیمال برای متن وسط
EQ_STYLE = "segmented_linear"

TEXT_COLOR_PALETTE = [
    (255, 255, 255, 248),  # سفید خالص
    (255, 232, 165, 248),  # کرم طلایی ملایم
    (185, 235, 255, 248),  # آبی یخی روشن
    (255, 200, 225, 248),  # صورتی پاستلی روشن
]

EQ_COLOR_PALETTE = [
    (0, 245, 212, 235),    # فیروزه‌ای نئونی
    (185, 110, 255, 235),  # بنفش یاسی پرانرژی
    (255, 159, 28, 235),   # نارنجی کهربایی
    (72, 229, 132, 235),   # سبز نعنایی
]

_FA_RESHAPER = None
if arabic_reshaper is not None:
    try:
        _FA_RESHAPER = arabic_reshaper.ArabicReshaper(configuration={"language": "fa"})
    except Exception:
        _FA_RESHAPER = None


def _log(msg: str):
    print(f"[REEL_MAKER] {msg}", file=sys.stderr, flush=True)


def _normalize_persian_chars(text: str) -> str:
    """حروف عربی رایج و نیم‌فاصله‌های نامتعارف را به فرم استاندارد فارسی نرمال می‌کند."""
    s = text.replace("\u200c", " ")
    s = s.replace("ك", "ک").replace("ي", "ی").replace("ى", "ی").replace("ۀ", "ه")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def ensure_default_logos():
    if not os.path.exists(TG_LOGO_PATH):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse((2, 2, 62, 62), fill=(36, 161, 222, 255))
        draw.polygon(
            [(16, 33), (48, 19), (41, 47), (31, 38), (26, 43), (26, 36)],
            fill=(255, 255, 255, 255),
        )
        img.save(TG_LOGO_PATH)

    if not os.path.exists(IG_LOGO_PATH):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle((4, 4, 60, 60), radius=16, fill=(225, 48, 108, 255))
        draw.rounded_rectangle(
            (13, 13, 51, 51), radius=11, outline=(255, 255, 255, 255), width=4
        )
        draw.ellipse((23, 23, 41, 41), outline=(255, 255, 255, 255), width=4)
        draw.ellipse((43, 17, 47, 21), fill=(255, 255, 255, 255))
        img.save(IG_LOGO_PATH)


def apply_opacity(img: Image.Image, alpha_factor: float) -> Image.Image:
    """شفافیت تصویر RGBA را بر اساس ضریب alpha_factor تنظیم می‌کند."""
    rgba = img.convert("RGBA")
    r, g, b, a = rgba.split()
    a = a.point(lambda p: max(0, min(255, int(p * alpha_factor))))
    return Image.merge("RGBA", (r, g, b, a))


def download_font_if_needed() -> str | None:
    """در صورت نبود فونت فارسی روی سیستم، فونت ظریف فارسی را به صورت خودکار دانلود می‌کند."""
    if os.path.exists(AUTO_FONT_PATH) and os.path.getsize(AUTO_FONT_PATH) > 15000:
        return AUTO_FONT_PATH

    os.makedirs(FONTS_DIR, exist_ok=True)
    for url in FONT_DOWNLOAD_URLS:
        try:
            _log(f"در حال دانلود فونت ظریف فارسی: {url}")
            resp = requests.get(url, timeout=20)
            if resp.status_code == 200 and resp.content and len(resp.content) > 15000:
                tmp_font = AUTO_FONT_PATH + ".tmp"
                with open(tmp_font, "wb") as f:
                    f.write(resp.content)
                os.replace(tmp_font, AUTO_FONT_PATH)
                _log("فونت ظریف فارسی با موفقیت دانلود و ذخیره شد.")
                return AUTO_FONT_PATH
        except Exception as e:
            _log(f"خطا در دانلود فونت از {url}: {e}")

    return None


def get_active_font_path() -> str | None:
    """اگر کاربر با .setfont فونت سفارشی داده باشد آن را برمی‌گرداند، وگرنه فونت ظریف پیش‌فرض."""
    if os.path.exists(CUSTOM_FONT_PATH) and os.path.getsize(CUSTOM_FONT_PATH) > 5000:
        return CUSTOM_FONT_PATH
    downloaded = download_font_if_needed()
    candidates = [
        downloaded,
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def load_font(size: int):
    path = get_active_font_path()
    if path:
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def load_emoji_font(size: int):
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
        "/usr/share/fonts/truetype/noto/NotoEmoji-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                pass
    return None


def parse_time_to_seconds(t_str: str) -> float:
    cleaned = t_str.strip()
    parts = [float(x.strip()) for x in cleaned.split(":")]
    if len(parts) == 2:
        return parts[0] * 60.0 + parts[1]
    elif len(parts) == 1:
        return parts[0]
    raise ValueError("فرمت زمان نامعتبر است. مثال درست: 00:35")


def cut_audio_segment(
    audio_path: str, output_audio_path: str, start_str: str, end_str: str
) -> tuple[bool, float, str]:
    """برش دقیق موزیک بین زمان شروع و پایان (حداکثر ۶۰ ثانیه) برای تبدیل به متن."""
    if not audio_path or not os.path.exists(audio_path):
        return False, 0.0, "فایل موزیک یافت نشد."

    start_sec = parse_time_to_seconds(start_str)
    end_sec = parse_time_to_seconds(end_str)
    if start_sec < 0 or end_sec <= start_sec:
        return False, 0.0, "زمان پایان باید بزرگ‌تر از زمان شروع باشد."

    duration = min(end_sec - start_sec, float(MAX_DURATION))

    cmd = [
        "ffmpeg",
        "-y",
        "-threads",
        "1",
        "-ss",
        str(start_sec),
        "-t",
        str(duration),
        "-i",
        audio_path,
        "-vn",
        "-c:a",
        "libmp3lame",
        "-b:a",
        "128k",
        output_audio_path,
    ]
    try:
        subprocess.run(
            cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60
        )
        if not os.path.exists(output_audio_path) or os.path.getsize(output_audio_path) == 0:
            return False, 0.0, "برش موزیک خروجی تولید نکرد."
        return True, duration, f"برش {duration:.1f} ثانیه‌ای موزیک آماده شد."
    except subprocess.TimeoutExpired:
        return False, 0.0, "زمان برش موزیک بیش از حد طولانی شد."
    except subprocess.CalledProcessError as e:
        err_txt = (e.stderr or b"").decode("utf-8", errors="ignore").strip()
        return False, 0.0, f"خطا در برش موزیک:\n{err_txt[-800:]}"


def test_voicemaker_transcription(audio_path: str, timeout: int = 15) -> tuple[bool, str]:
    """
    تلاش می‌کند اتصال و ارسال فایل صوتی به voicemaker.in را تست کند.
    در صورت برخورد با Cloudflare یا عدم دسترسی مستقیم API، دلیل را گزارش می‌دهد.
    """
    if not audio_path or not os.path.exists(audio_path):
        return False, "فایل صوتی برای تست وجود ندارد."

    url = "https://voicemaker.in/speech-to-text/persian/"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
    }

    try:
        session = requests.Session()
        resp = session.get(url, headers=headers, timeout=timeout)
        body_lower = resp.text.lower()

        if (
            resp.status_code in (403, 429, 503)
            or "cf-browser-verification" in body_lower
            or "just a moment..." in body_lower
            or "enable javascript and cookies" in body_lower
        ):
            return (
                False,
                f"سایت voicemaker.in با محافظت امنیتی/Cloudflare (کد {resp.status_code}) جلوی درخواست خودکار را گرفت.",
            )

        with open(audio_path, "rb") as f:
            files = {"file": (os.path.basename(audio_path), f, "audio/mpeg")}
            data = {"language": "persian", "lang": "fa"}
            post_resp = session.post(
                url, headers=headers, files=files, data=data, timeout=timeout
            )

        ctype = post_resp.headers.get("Content-Type", "").lower()
        if "application/json" in ctype:
            try:
                payload = post_resp.json()
                for key in ("text", "transcript", "result", "data"):
                    if isinstance(payload, dict) and payload.get(key):
                        return True, str(payload[key]).strip()
            except Exception:
                pass

        return (
            False,
            f"سایت پاسخ مستقیم متنی نداد (وضعیت {post_resp.status_code}). تبدیل دستی انجام شود.",
        )

    except requests.RequestException as e:
        return False, f"خطا در ارتباط شبکه با سایت: {str(e)[:200]}"


def _extract_pcm_envelope(
    audio_path: str,
    start_sec: float,
    duration: float,
    total_frames: int,
    af_filter: str | None = None,
    gain: float = 5.0,
) -> list[float]:
    """انرژی هر فریم از سیگنال صوتی (اختیاری با فیلتر فرکانسی وکال) را استخراج می‌کند."""
    sample_rate = 4000
    with tempfile.NamedTemporaryFile(suffix=".pcm", delete=False) as tf:
        pcm_path = tf.name

    cmd = [
        "ffmpeg",
        "-y",
        "-threads",
        "1",
        "-ss",
        str(start_sec),
        "-t",
        str(duration),
        "-i",
        audio_path,
    ]
    if af_filter:
        cmd.extend(["-af", af_filter])
    cmd.extend(
        [
            "-f",
            "s16le",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            pcm_path,
        ]
    )

    try:
        subprocess.run(
            cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45
        )
        with open(pcm_path, "rb") as f:
            raw = f.read()
    except Exception:
        return [0.3] * total_frames
    finally:
        if os.path.exists(pcm_path):
            os.remove(pcm_path)

    if not raw:
        return [0.3] * total_frames

    count = len(raw) // 2
    samples = struct.unpack(f"<{count}h", raw[: count * 2])
    samples_per_frame = max(1, count // total_frames)

    out: list[float] = []
    for i in range(total_frames):
        chunk = samples[i * samples_per_frame : (i + 1) * samples_per_frame]
        if not chunk:
            out.append(0.08)
            continue
        rms = math.sqrt(sum(s * s for s in chunk) / len(chunk)) / 32768.0
        val = min(1.0, (rms * gain) ** 0.8)
        out.append(max(0.06, val))
    return out


def extract_vocal_and_rhythm_envelopes(
    audio_path: str, start_sec: float, duration: float, fps: int
) -> tuple[list[float], list[float]]:
    """
    انرژی وکال و ترکیب وکال+ریتم را استخراج می‌کند.
    """
    total_frames = max(1, int(duration * fps))
    vocal_env = _extract_pcm_envelope(
        audio_path,
        start_sec,
        duration,
        total_frames,
        af_filter="bandpass=f=1500:w=1800:t=h",
        gain=6.2,
    )
    rhythm_env = _extract_pcm_envelope(
        audio_path,
        start_sec,
        duration,
        total_frames,
        af_filter=None,
        gain=4.4,
    )

    combined: list[float] = []
    prev_v = 0.2
    for v, r in zip(vocal_env, rhythm_env):
        target = min(1.0, v * 0.78 + r * 0.22)
        cur = max(0.06, target * 0.82 + prev_v * 0.18)
        prev_v = cur
        combined.append(cur)
    return combined, vocal_env


def _detect_vocal_speech_segments(
    audio_path: str, start_sec: float, duration: float
) -> list[tuple[float, float]]:
    """
    با فیلتر bandpass وکال و silencedetect، بازه‌های زمانیِ واقعیِ خواندن خواننده را استخراج می‌کند.
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-threads",
        "1",
        "-ss",
        str(start_sec),
        "-t",
        str(duration),
        "-i",
        audio_path,
        "-af",
        "bandpass=f=1500:w=1800:t=h,silencedetect=noise=-28dB:d=0.35",
        "-f",
        "null",
        "-",
    ]
    try:
        res = subprocess.run(
            cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30
        )
        err = (res.stderr or b"").decode("utf-8", errors="ignore")
    except Exception:
        return [(0.0, duration)]

    silences: list[tuple[float, float]] = []
    cur_start: float | None = None
    for line in err.splitlines():
        m_start = re.search(r"silence_start:\s*([0-9.]+)", line)
        if m_start:
            cur_start = float(m_start.group(1))
        m_end = re.search(r"silence_end:\s*([0-9.]+)", line)
        if m_end and cur_start is not None:
            silences.append((cur_start, float(m_end.group(1))))
            cur_start = None
    if cur_start is not None:
        silences.append((cur_start, duration))

    speech_segs: list[tuple[float, float]] = []
    cursor = 0.0
    for s_start, s_end in silences:
        if s_start - cursor >= 0.35:
            speech_segs.append((cursor, min(duration, s_start)))
        cursor = max(cursor, s_end)
    if duration - cursor >= 0.35:
        speech_segs.append((cursor, duration))

    return speech_segs if speech_segs else [(0.0, duration)]


def _clean_phrase_text(raw: str) -> str:
    """نقطه‌ها و نشانه‌های اضافی تبدیل‌صوت را تمیز می‌کند و حروف را به فارسی نرمال می‌کند."""
    cleaned = _normalize_persian_chars(raw)
    cleaned = re.sub(r"[.،؛:]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _parse_timed_lines(raw_text: str) -> list[tuple[float | None, str]]:
    """
    خطوط متن را بررسی می‌کند؛ اگر ابتدای خط زمان باشد (مثل `00:04 متن`) زمان شروع را می‌گیرد،
    وگرنه `None` برمی‌گرداند تا خودکار روی بخش‌های وکال سینک شود.
    """
    lines = [part.strip() for part in re.split(r"\n+|\s*\|\s*", raw_text.strip()) if part.strip()]
    parsed: list[tuple[float | None, str]] = []
    for line in lines:
        m = re.match(r"^\[?(\d{1,2}:\d{2}(?:\.\d+)?|\d+(?:\.\d+)?s?)\]?\s+(.+)$", line)
        if m:
            t_raw = m.group(1).rstrip("s")
            phrase = _clean_phrase_text(m.group(2))
            if phrase:
                try:
                    parsed.append((parse_time_to_seconds(t_raw), phrase))
                    continue
                except ValueError:
                    pass
        phrase = _clean_phrase_text(line)
        if phrase:
            parsed.append((None, phrase))
    return parsed


def build_vocal_synced_cues(
    lyrics_text: str,
    audio_path: str,
    start_sec: float,
    duration: float,
    fps: int,
    vocal_env: list[float],
) -> list[tuple[int, int, str]]:
    """
    سینک متن با خواننده:
    1. اگر کاربر کنار خط‌ها زمان شروع داده باشد (`00:03 متن`)، دقیقاً روی همان ثانیه‌ها می‌نشیند.
    2. در غیر این صورت، با `silencedetect` بخش‌های واقعیِ خواندن خواننده پیدا شده و عبارات روی آن‌ها توزیع می‌شوند.
    """
    timed_items = _parse_timed_lines(lyrics_text)
    if not timed_items:
        return []

    total_frames = max(1, int(duration * fps))

    # حالت اول: زمان‌بندی دستی خط‌به‌خط (LRC ساده)
    if any(t is not None for t, _ in timed_items):
        cues: list[tuple[int, int, str]] = []
        valid_timed: list[tuple[float, str]] = []
        last_t = 0.0
        for t_val, phrase in timed_items:
            t_use = t_val if t_val is not None else last_t + 2.5
            t_use = max(0.0, min(duration - 0.3, t_use))
            valid_timed.append((t_use, phrase))
            last_t = t_use

        for idx, (t_start, phrase) in enumerate(valid_timed):
            t_end = valid_timed[idx + 1][0] if idx + 1 < len(valid_timed) else duration
            s_f = max(0, min(total_frames - 1, int(round(t_start * fps))))
            e_f = max(s_f + 2, min(total_frames - 1, int(round(t_end * fps)) - 1))
            cues.append((s_f, e_f, phrase))
        return cues

    # حالت دوم: خرد کردن منطقی فقط اگر خط‌ها خیلی طولانی باشند
    has_explicit_lines = ("\n" in lyrics_text.strip()) or ("|" in lyrics_text.strip())
    phrases: list[str] = []
    for _, ch in timed_items:
        words = [w.strip() for w in ch.split() if w.strip()]
        max_words = 6 if has_explicit_lines else 4
        if len(words) <= max_words:
            phrases.append(ch)
        else:
            for i in range(0, len(words), max_words):
                part_phrase = " ".join(words[i : i + max_words]).strip()
                if part_phrase:
                    phrases.append(part_phrase)

    if not phrases:
        return []

    speech_segs = _detect_vocal_speech_segments(audio_path, start_sec, duration)
    active_frames: list[int] = []
    for seg_s, seg_e in speech_segs:
        f0 = max(0, int(round(seg_s * fps)))
        f1 = min(total_frames - 1, int(round(seg_e * fps)))
        active_frames.extend(range(f0, f1 + 1))

    if len(active_frames) < len(phrases) * 4:
        active_frames = list(range(total_frames))

    weights = [max(2.5, len(p.split()) * 2.0 + len(re.sub(r"\s+", "", p)) * 0.4) for p in phrases]
    n_active = len(active_frames)
    cues = []
    act_cursor = 0

    for idx, (phrase, w) in enumerate(zip(phrases, weights)):
        if act_cursor >= n_active:
            break
        remaining_w = sum(weights[idx:])
        remaining_act = n_active - act_cursor
        take = max(4, int(round(remaining_act * (w / max(0.1, remaining_w)))))
        end_act = n_active - 1 if idx == len(phrases) - 1 else min(n_active - 1, act_cursor + take - 1)

        s_f = active_frames[act_cursor]
        e_f = max(s_f, active_frames[end_act])
        cues.append((s_f, e_f, phrase))
        act_cursor = end_act + 1

    return cues


def _render_text_via_ffmpeg_drawtext(
    text: str, font_path: str, color_rgba: tuple[int, int, int, int]
) -> Image.Image | None:
    """
    متن فارسی را با سایز کوچک و ظریف (مینیمال) و بدون کادر شلوغ با موتور داخلی ffmpeg رندر می‌کند.
    """
    if not font_path or not os.path.exists(font_path):
        return None

    r, g, b, _ = color_rgba
    hex_color = f"0x{r:02x}{g:02x}{b:02x}"

    with tempfile.TemporaryDirectory() as tmpdir:
        txt_file = os.path.join(tmpdir, "line.txt")
        png_file = os.path.join(tmpdir, "rendered.png")
        with open(txt_file, "w", encoding="utf-8") as f:
            f.write(text)

        safe_font = font_path.replace("\\", "/").replace(":", "\\:")
        safe_txt = txt_file.replace("\\", "/").replace(":", "\\:")

        # استایل کوچک، ظریف و مینیمال با سایه نرم و حاشیه خیلی نازک (بدون کادر تیره)
        vf = (
            f"drawtext=fontfile='{safe_font}':textfile='{safe_txt}':"
            f"text_shaping=1:fontsize={MINIMAL_FONT_SIZE}:fontcolor={hex_color}:"
            f"borderw=1:bordercolor=black@0.75:shadowx=1:shadowy=2:shadowcolor=black@0.85:"
            f"x=(w-text_w)/2:y=(h-text_h)/2"
        )
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black@0.0:s={WIDTH}x110:d=0.05",
            "-vf",
            vf,
            "-frames:v",
            "1",
            "-pix_fmt",
            "rgba",
            png_file,
        ]
        try:
            subprocess.run(
                cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10
            )
            if os.path.exists(png_file) and os.path.getsize(png_file) > 0:
                img = Image.open(png_file).convert("RGBA")
                bbox = img.getbbox()
                if bbox:
                    pad_x, pad_y = 14, 10
                    x0 = max(0, bbox[0] - pad_x)
                    y0 = max(0, bbox[1] - pad_y)
                    x1 = min(img.width, bbox[2] + pad_x)
                    y1 = min(img.height, bbox[3] + pad_y)
                    return img.crop((x0, y0, x1, y1))
        except Exception as e:
            _log(f"drawtext fallback فعال شد: {e}")
    return None


def _render_text_via_pillow_fallback(
    text: str, font_minimal, color_rgba: tuple[int, int, int, int]
) -> Image.Image:
    """رندر پشتیبان مینیمال در صورتی که ffmpeg بدون drawtext کامپایل شده باشد."""
    s = _normalize_persian_chars(text)
    if _FA_RESHAPER is not None and get_display is not None:
        try:
            s = get_display(_FA_RESHAPER.reshape(s))
        except Exception:
            pass

    dummy = Image.new("RGBA", (WIDTH, 110), (0, 0, 0, 0))
    draw = ImageDraw.Draw(dummy)
    bbox = draw.textbbox((0, 0), s, font=font_minimal)
    tw = max(1, bbox[2] - bbox[0])
    th = max(1, bbox[3] - bbox[1])

    box_w = min(WIDTH - 32, tw + 28)
    box_h = th + 20
    canvas = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    tdraw = ImageDraw.Draw(canvas)

    tx = max(6, (box_w - tw) // 2)
    ty = max(4, (box_h - th) // 2)
    tdraw.text((tx + 1, ty + 2), s, font=font_minimal, fill=(0, 0, 0, 210))
    tdraw.text((tx, ty), s, font=font_minimal, fill=color_rgba)
    return canvas


def pre_render_cue_overlays(
    cues: list[tuple[int, int, str]],
    font_path: str | None,
    font_minimal,
) -> dict[int, Image.Image]:
    """تصویر مینیمال هر عبارت متنی را فقط یک بار از پیش می‌سازد."""
    overlays: dict[int, Image.Image] = {}
    for idx, (_, _, phrase) in enumerate(cues):
        color_rgba = TEXT_COLOR_PALETTE[idx % len(TEXT_COLOR_PALETTE)]
        norm_phrase = _normalize_persian_chars(phrase)
        img = (
            _render_text_via_ffmpeg_drawtext(norm_phrase, font_path, color_rgba)
            if font_path
            else None
        )
        if img is None:
            img = _render_text_via_pillow_fallback(norm_phrase, font_minimal, color_rgba)
        overlays[idx] = img
    return overlays


def draw_linear_equalizer(
    frame: Image.Image,
    f_idx: int,
    amp: float,
    eq_rgba: tuple[int, int, int, int],
    style: str = EQ_STYLE,
) -> int:
    """
    اکولایزر خطی حساس به وکال و ریتم را روی بک‌گراند ریلز رسم می‌کند.
    """
    draw = ImageDraw.Draw(frame)
    r, g, b, alpha = eq_rgba
    main_color = (r, g, b, alpha)
    dim_color = (r, g, b, max(70, alpha // 2))

    line_count = 44
    line_w = 4
    gap = 6
    total_w = line_count * line_w + (line_count - 1) * gap
    start_x = (WIDTH - total_w) // 2
    base_y = HEIGHT - 150
    max_h = 78

    draw.line(
        [(start_x, base_y + 2), (start_x + total_w, base_y + 2)],
        fill=dim_color,
        width=2,
    )

    for i in range(line_count):
        norm_pos = (i / max(1, line_count - 1)) * 2.0 - 1.0
        center_weight = max(0.3, 1.0 - 0.55 * abs(norm_pos))

        vocal_wave = abs(math.sin(f_idx * 0.72 + i * 0.85)) ** 1.25
        rhythm_tick = 0.75 + 0.25 * math.cos(f_idx * 0.35 + i * 0.4)
        h = max(5, int(max_h * amp * center_weight * vocal_wave * rhythm_tick))

        x = start_x + i * (line_w + gap)
        if style == "dual_linear":
            mid_y = base_y - 34
            half_h = max(4, h // 2)
            draw.line([(x, mid_y - half_h), (x, mid_y + half_h)], fill=main_color, width=line_w)
        else:
            seg_h = 7
            seg_gap = 3
            cur_y = base_y
            drawn = 0
            while drawn < h and cur_y > base_y - max_h:
                step = min(seg_h, h - drawn)
                draw.line([(x, cur_y), (x, cur_y - step)], fill=main_color, width=line_w)
                cur_y -= step + seg_gap
                drawn += step + seg_gap

    return base_y + 4


def make_fixed_bottom_watermark(tg_logo: Image.Image, ig_logo: Image.Image, font_wm) -> Image.Image:
    """واترمارک کوچک با آیکون‌های واضح‌تر و متن ۴۰٪ شفاف زیر هم بدون فاصله."""
    block_w = 240
    block_h = 44
    block = Image.new("RGBA", (block_w, block_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(block)

    icon_size = 20
    row_step = 22

    block.paste(tg_logo, (0, 1), tg_logo)
    draw.text((icon_size + 5, 2), TG_TEXT, font=font_wm, fill=(255, 255, 255, WM_TEXT_ALPHA))

    block.paste(ig_logo, (0, row_step + 1), ig_logo)
    draw.text((icon_size + 5, row_step + 2), IG_TEXT, font=font_wm, fill=(255, 255, 255, WM_TEXT_ALPHA))

    return block


def build_synced_reel(
    video_path: str,
    audio_path: str,
    output_path: str,
    start_str: str,
    end_str: str,
    lyrics_text: str,
) -> tuple[bool, str]:
    """
    بک‌گراند ریلز (ویدئو/عکس بدون واترماک) را تا سقف ۶۰ ثانیه و دقیقاً هم‌اندازه تایم موزیک کات می‌زند،
    صدای اصلی ویدئو را قطع می‌کند، اکولایزر خطی و متن ظریفِ مینیمال هماهنگ با خواننده را روی بک‌گراند می‌گذارد
    و واترماک ثابت را در وسط و زیر اکولایزر با فاصله کم قرار می‌دهد.
    """
    if not video_path or not os.path.exists(video_path):
        return False, "ابتدا ویدئوی خام بدون واترماک را با دستور .setbg ثبت کنید."
    if not audio_path or not os.path.exists(audio_path):
        return False, "فایل موزیک یافت نشد."

    start_sec = parse_time_to_seconds(start_str)
    end_sec = parse_time_to_seconds(end_str)
    if start_sec < 0 or end_sec <= start_sec:
        return False, "زمان پایان باید بزرگ‌تر از زمان شروع باشد."

    duration = min(end_sec - start_sec, float(MAX_DURATION))
    _log(f"شروع ساخت ریلز به مدت {duration:.1f} ثانیه")

    eq_energies, vocal_env = extract_vocal_and_rhythm_envelopes(audio_path, start_sec, duration, FPS)
    cues = build_vocal_synced_cues(lyrics_text, audio_path, start_sec, duration, FPS, vocal_env)
    _log(f"تعداد عبارات سینک‌شده با خواننده: {len(cues)}")

    ensure_default_logos()
    font_path = get_active_font_path()
    font_wm = load_font(18)
    font_minimal = load_font(MINIMAL_FONT_SIZE)

    cue_overlays = pre_render_cue_overlays(cues, font_path, font_minimal)

    tg_logo = apply_opacity(Image.open(TG_LOGO_PATH).resize((20, 20)), WM_ICON_OPACITY)
    ig_logo = apply_opacity(Image.open(IG_LOGO_PATH).resize((20, 20)), WM_ICON_OPACITY)
    wm_block = make_fixed_bottom_watermark(tg_logo, ig_logo, font_wm)
    wm_w, wm_h = wm_block.size

    fixed_wm_x = (WIDTH - wm_w) // 2
    eq_bottom_y = HEIGHT - 146
    gap_below_eq = 12
    fixed_wm_y = min(HEIGHT - wm_h - 10, eq_bottom_y + gap_below_eq)

    is_video = video_path.lower().endswith((".mp4", ".mov", ".mkv", ".webm"))
    vid_input = ["-stream_loop", "-1", "-i", video_path] if is_video else ["-loop", "1", "-i", video_path]

    dec_cmd = [
        "ffmpeg",
        "-y",
        "-threads",
        "1",
        *vid_input,
        "-an",
        "-t",
        str(duration),
        "-vf",
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT},fps={FPS},setsar=1",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-",
    ]

    enc_cmd = [
        "ffmpeg",
        "-y",
        "-threads",
        "1",
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-s",
        f"{WIDTH}x{HEIGHT}",
        "-pix_fmt",
        "rgb24",
        "-r",
        str(FPS),
        "-i",
        "-",
        "-ss",
        str(start_sec),
        "-t",
        str(duration),
        "-i",
        audio_path,
        "-map",
        "0:v",
        "-map",
        "1:a",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-threads",
        "1",
        "-x264-params",
        "threads=1:rc-lookahead=0:sync-lookahead=0:bframes=0:ref=1",
        "-crf",
        "25",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-pix_fmt",
        "yuv420p",
        "-t",
        str(duration),
        output_path,
    ]

    dec_proc = subprocess.Popen(dec_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    enc_proc = subprocess.Popen(enc_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    frame_bytes_len = WIDTH * HEIGHT * 3
    total_frames = max(1, int(duration * FPS))
    written_frames = 0

    try:
        _log(f"پردازش {total_frames} فریم آغاز شد...")
        for f_idx in range(total_frames):
            raw_frame = dec_proc.stdout.read(frame_bytes_len) if dec_proc.stdout else b""
            if not raw_frame or len(raw_frame) < frame_bytes_len:
                _log(f"اتمام یا توقف جریان فریم ورودی در فریم {f_idx}")
                break

            if enc_proc.poll() is not None or not enc_proc.stdin or enc_proc.stdin.closed:
                _log(f"فرآیند انکود ffmpeg در فریم {f_idx} زودتر بسته شد.")
                break

            frame = Image.frombytes("RGB", (WIDTH, HEIGHT), raw_frame).convert("RGBA")
            amp = eq_energies[f_idx] if f_idx < len(eq_energies) else 0.2

            active_cue_idx = -1
            for idx, (s_f, e_f, _) in enumerate(cues):
                if s_f <= f_idx <= e_f:
                    active_cue_idx = idx
                    break

            eq_rgba = EQ_COLOR_PALETTE[(max(0, active_cue_idx) + 1) % len(EQ_COLOR_PALETTE)]
            draw_linear_equalizer(frame, f_idx, amp, eq_rgba, style=EQ_STYLE)

            if active_cue_idx >= 0 and active_cue_idx in cue_overlays:
                overlay = cue_overlays[active_cue_idx]
                px = max(10, (WIDTH - overlay.width) // 2)
                py = max(10, (HEIGHT - overlay.height) // 2)
                frame.paste(overlay, (px, py), overlay)

            frame.paste(wm_block, (fixed_wm_x, fixed_wm_y), wm_block)

            try:
                enc_proc.stdin.write(frame.convert("RGB").tobytes())
                written_frames += 1
            except (BrokenPipeError, ValueError) as write_err:
                _log(f"توقف نوشتن روی stdin انکود در فریم {f_idx}: {write_err}")
                break

            if written_frames % 60 == 0 or written_frames == total_frames:
                _log(f"پیشرفت فریم‌ها: {written_frames}/{total_frames}")

        if dec_proc.stdout and not dec_proc.stdout.closed:
            dec_proc.stdout.close()
        if enc_proc.stdin and not enc_proc.stdin.closed:
            try:
                enc_proc.stdin.close()
            except ValueError:
                pass

        dec_err = ""
        if dec_proc.stderr:
            try:
                dec_err = dec_proc.stderr.read().decode("utf-8", errors="ignore").strip()
                dec_proc.stderr.close()
            except ValueError:
                pass

        try:
            dec_proc.wait(timeout=30)
        except Exception:
            pass

        enc_err = ""
        try:
            _, enc_err_bytes = enc_proc.communicate(timeout=60)
            enc_err = (enc_err_bytes or b"").decode("utf-8", errors="ignore").strip()
        except ValueError:
            if enc_proc.stderr:
                try:
                    enc_err = enc_proc.stderr.read().decode("utf-8", errors="ignore").strip()
                except ValueError:
                    pass

        try:
            enc_proc.wait(timeout=15)
        except Exception:
            pass

        rc = enc_proc.returncode
        file_ready = (
            written_frames > 0
            and os.path.exists(output_path)
            and os.path.getsize(output_path) > 0
        )

        if rc not in (0, None):
            _log(f"خطای انکود ffmpeg با کد {rc}: {enc_err[-400:]}")
            if rc == -9:
                return False, "خطا در ffmpeg (کد -9): رم کانتینر در لحظه انکود پر شد."
            if not file_ready:
                return False, f"خطا در ffmpeg (کد {rc}):\n{enc_err[-1000:]}"

        if not file_ready:
            _log(f"فایل خروجی ساخته نشد (rc={rc}). dec_err={dec_err[-300:]}")
            return False, f"فایل ویدئویی نهایی ساخته نشد.\n{dec_err[-500:]}"

        _log(f"ساخت ویدئو با موفقیت تمام شد ({written_frames} فریم، rc={rc}).")
        return True, f"ریلز {duration:.0f} ثانیه‌ای با فونت ظریف مینیمال و سینک خواننده آماده شد."

    except Exception as e:
        _log(f"استثنا در build_synced_reel: {e}")
        for p in (dec_proc, enc_proc):
            if p.poll() is None:
                p.kill()
        return False, f"خطا در ساخت ویدئو: {str(e)[:300]}"
