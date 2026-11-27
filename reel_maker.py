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
AUTO_FONT_PATH = os.path.join(FONTS_DIR, "PersianBoldFont.ttf")
TG_LOGO_PATH = os.path.join(BASE_DIR, "tg_logo.png")
IG_LOGO_PATH = os.path.join(BASE_DIR, "ig_logo.png")

FONT_DOWNLOAD_URLS = [
    "https://github.com/rastikerdar/vazirmatn/raw/master/fonts/ttf/Vazirmatn-Bold.ttf",
    "https://github.com/google/fonts/raw/main/ofl/notosansarabic/static/NotoSansArabic-Bold.ttf",
    "https://github.com/google/fonts/raw/main/ofl/rubik/Rubik-Bold.ttf",
]

MAX_DURATION = 60
WIDTH = 720
HEIGHT = 1280
FPS = 20
WM_TEXT_ALPHA = 102      # حدود ۴۰ درصد شفافیت برای متن واترماک
WM_ICON_OPACITY = 0.82   # وضوح بیشتر آیکون‌های تلگرام و اینستاگرام
EQ_STYLE = "segmented_linear"

TEXT_COLOR_PALETTE = [
    (255, 255, 255, 252),  # سفید خالص
    (255, 214, 10, 252),   # زرد طلایی
    (120, 220, 255, 252),  # آبی روشن
    (255, 130, 185, 252),  # صورتی ملایم
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

# جدول فرم‌های چهارگانه حروف فارسی: (جدا، پایانی، آغازین، میانی)
_PERSIAN_GLYPH_FORMS: dict[str, tuple[str, str, str, str]] = {
    "آ": ("\uFE81", "\uFE82", "\uFE81", "\uFE82"),
    "ا": ("\uFE8D", "\uFE8E", "\uFE8D", "\uFE8E"),
    "أ": ("\uFE83", "\uFE84", "\uFE83", "\uFE84"),
    "إ": ("\uFE87", "\uFE88", "\uFE87", "\uFE88"),
    "ئ": ("\uFE89", "\uFE8A", "\uFE8B", "\uFE8C"),
    "ب": ("\uFE8F", "\uFE90", "\uFE91", "\uFE92"),
    "پ": ("\uFB56", "\uFB57", "\uFB58", "\uFB59"),
    "ت": ("\uFE95", "\uFE96", "\uFE97", "\uFE98"),
    "ث": ("\uFE99", "\uFE9A", "\uFE9B", "\uFE9C"),
    "ج": ("\uFE9D", "\uFE9E", "\uFE9F", "\uFEA0"),
    "چ": ("\uFB7A", "\uFB7B", "\uFB7C", "\uFB7D"),
    "ح": ("\uFEA1", "\uFEA2", "\uFEA3", "\uFEA4"),
    "خ": ("\uFEA5", "\uFEA6", "\uFEA7", "\uFEA8"),
    "د": ("\uFEA9", "\uFEAA", "\uFEA9", "\uFEAA"),
    "ذ": ("\uFEAB", "\uFEAC", "\uFEAB", "\uFEAC"),
    "ر": ("\uFEAD", "\uFEAE", "\uFEAD", "\uFEAE"),
    "ز": ("\uFEAF", "\uFEB0", "\uFEAF", "\uFEB0"),
    "ژ": ("\uFB8A", "\uFB8B", "\uFB8A", "\uFB8B"),
    "س": ("\uFEB1", "\uFEB2", "\uFEB3", "\uFEB4"),
    "ش": ("\uFEB5", "\uFEB6", "\uFEB7", "\uFEB8"),
    "ص": ("\uFEB9", "\uFEBA", "\uFEBB", "\uFEBC"),
    "ض": ("\uFEBD", "\uFEBE", "\uFEBF", "\uFEC0"),
    "ط": ("\uFEC1", "\uFEC2", "\uFEC3", "\uFEC4"),
    "ظ": ("\uFEC5", "\uFEC6", "\uFEC7", "\uFEC8"),
    "ع": ("\uFEC9", "\uFECA", "\uFECB", "\uFECC"),
    "غ": ("\uFECD", "\uFECE", "\uFECF", "\uFED0"),
    "ف": ("\uFED1", "\uFED2", "\uFED3", "\uFED4"),
    "ق": ("\uFED5", "\uFED6", "\uFED7", "\uFED8"),
    "ک": ("\uFB8E", "\uFB8F", "\uFB90", "\uFB91"),
    "گ": ("\uFB92", "\uFB93", "\uFB94", "\uFB95"),
    "ل": ("\uFEDD", "\uFEDE", "\uFEDF", "\uFEE0"),
    "م": ("\uFEE1", "\uFEE2", "\uFEE3", "\uFEE4"),
    "ن": ("\uFEE5", "\uFEE6", "\uFEE7", "\uFEE8"),
    "و": ("\uFEED", "\uFEEE", "\uFEED", "\uFEEE"),
    "ؤ": ("\uFE85", "\uFE86", "\uFE85", "\uFE86"),
    "ه": ("\uFEE9", "\uFEEA", "\uFEEB", "\uFEEC"),
    "ی": ("\uFBFC", "\uFBFD", "\uFBFE", "\uFBFF"),
}

_RIGHT_JOIN_ONLY = {"آ", "ا", "أ", "إ", "د", "ذ", "ر", "ز", "ژ", "و", "ؤ"}
_PUNCT_MIRROR = {"؟": "؟", "?": "؟", "!": "!", "«": "»", "»": "«", "(": ")", ")": "("}


def _log(msg: str):
    print(f"[REEL_MAKER] {msg}", file=sys.stderr, flush=True)


def _normalize_persian_chars(text: str) -> str:
    """حروف عربی رایج و نیم‌فاصله‌های نامتعارف را به فرم استاندارد فارسی نرمال می‌کند."""
    s = text.replace("\u200c", " ")
    s = s.replace("ك", "ک").replace("ي", "ی").replace("ى", "ی").replace("ۀ", "ه")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _shape_single_word(word: str) -> str:
    """حروف یک کلمه فارسی را به هم متصل می‌کند و برای رندر چپ‌به‌راستِ Pillow معکوس می‌کند."""
    normalized = (
        word.replace("لآ", "\uFEF5")
        .replace("لأ", "\uFEF7")
        .replace("لإ", "\uFEF9")
        .replace("لا", "\uFEFB")
    )
    chars = list(normalized)
    out_chars: list[str] = []
    n = len(chars)

    for idx, ch in enumerate(chars):
        if ch in ("\uFEF5", "\uFEF7", "\uFEF9", "\uFEFB"):
            prev_ch = chars[idx - 1] if idx > 0 else ""
            can_join_prev = (
                prev_ch in _PERSIAN_GLYPH_FORMS and prev_ch not in _RIGHT_JOIN_ONLY
            )
            out_chars.append(chr(ord(ch) + 1) if can_join_prev else ch)
            continue

        if ch not in _PERSIAN_GLYPH_FORMS:
            out_chars.append(_PUNCT_MIRROR.get(ch, ch))
            continue

        prev_ch = chars[idx - 1] if idx > 0 else ""
        next_ch = chars[idx + 1] if idx + 1 < n else ""

        can_join_prev = (
            prev_ch in _PERSIAN_GLYPH_FORMS and prev_ch not in _RIGHT_JOIN_ONLY
        )
        can_join_next = (
            ch not in _RIGHT_JOIN_ONLY
            and (
                next_ch in _PERSIAN_GLYPH_FORMS
                or next_ch in ("\uFEF5", "\uFEF7", "\uFEF9", "\uFEFB")
            )
        )

        isolated, final, initial, medial = _PERSIAN_GLYPH_FORMS[ch]
        if can_join_prev and can_join_next:
            out_chars.append(medial)
        elif can_join_prev:
            out_chars.append(final)
        elif can_join_next:
            out_chars.append(initial)
        else:
            out_chars.append(isolated)

    return "".join(reversed(out_chars))


def _builtin_persian_reshape_and_bidi(text: str) -> str:
    """
    چینش راست‌به‌چپ دقیق برای Pillow:
    در عبارت فارسی «کلمه۱ کلمه۲؟»، در رسم چپ‌به‌راستِ Pillow باید «؟۲هملک ۱هملک» قرار بگیرد
    تا وقتی چشم از راست به چپ می‌خواند، «کلمه۱ کلمه۲؟» در جهت درست خوانده شود.
    """
    words = [w for w in text.split() if w.strip()]
    if not words:
        return ""

    shaped_words = [_shape_single_word(w) for w in words]
    # معکوس کردن ترتیب کلمات تا در رسم چپ‌به‌راستِ Pillow، عبارت از راست به چپ خوانده شود
    return " ".join(reversed(shaped_words))


def _shape_persian_text(text: str) -> str:
    """متن فارسی را نرمال، متصل و راست‌به‌چپ مرتب می‌کند."""
    s = _normalize_persian_chars(text)
    if not s:
        return ""
    has_persian = any("\u0600" <= ch <= "\u06FF" for ch in s)
    if not has_persian:
        return s

    if _FA_RESHAPER is not None and get_display is not None:
        try:
            reshaped = _FA_RESHAPER.reshape(s)
            bidi_out = get_display(reshaped)
            if isinstance(bidi_out, str) and bidi_out.strip():
                return bidi_out
        except Exception:
            pass

    return _builtin_persian_reshape_and_bidi(s)


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
    """در صورت نبود فونت بولد غیرمتغیر فارسی روی سیستم، آن را به صورت خودکار دانلود می‌کند."""
    if os.path.exists(AUTO_FONT_PATH) and os.path.getsize(AUTO_FONT_PATH) > 15000:
        return AUTO_FONT_PATH

    os.makedirs(FONTS_DIR, exist_ok=True)
    for url in FONT_DOWNLOAD_URLS:
        try:
            _log(f"در حال دانلود فونت بولد فارسی: {url}")
            resp = requests.get(url, timeout=20)
            if resp.status_code == 200 and resp.content and len(resp.content) > 15000:
                tmp_font = AUTO_FONT_PATH + ".tmp"
                with open(tmp_font, "wb") as f:
                    f.write(resp.content)
                os.replace(tmp_font, AUTO_FONT_PATH)
                _log("فونت بولد فارسی با موفقیت دانلود و ذخیره شد.")
                return AUTO_FONT_PATH
        except Exception as e:
            _log(f"خطا در دانلود فونت از {url}: {e}")

    return None


def load_bold_font(size: int):
    downloaded = download_font_if_needed()
    candidates = [
        downloaded,
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if path and os.path.exists(path):
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


def extract_vocal_and_rhythm_envelope(
    audio_path: str, start_sec: float, duration: float, fps: int
) -> list[float]:
    """
    انرژی را با تمرکز بالا روی وکال (حدود ۳۰۰ تا ۳۲۰۰ هرتز) و کمی ریتم کلی آهنگ استخراج می‌کند.
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
    return combined


def _clean_phrase_text(raw: str) -> str:
    """نقطه‌ها و نشانه‌های اضافی تبدیل‌صوت را تمیز می‌کند و حروف را به فارسی نرمال می‌کند."""
    cleaned = _normalize_persian_chars(raw)
    cleaned = re.sub(r"[.،؛:]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def build_rhythmic_cues(
    lyrics_text: str, duration: float, fps: int, energies: list[float]
) -> list[tuple[int, int, str]]:
    """
    متن را تمیز و به عبارات منسجم تقسیم می‌کند و با زمان‌بندی دقیق‌تر و روان‌تر
    روی بازه فریم‌ها می‌نشاند.
    """
    clean = lyrics_text.strip()
    if not clean:
        return []

    raw_chunks = [part.strip() for part in re.split(r"\n+|\s*\|\s*", clean) if part.strip()]
    phrases: list[str] = []
    for ch in raw_chunks:
        cleaned_ch = _clean_phrase_text(ch)
        if not cleaned_ch:
            continue
        words = [w.strip() for w in cleaned_ch.split() if w.strip()]
        if len(words) <= 3:
            phrases.append(cleaned_ch)
        else:
            for i in range(0, len(words), 3):
                part_phrase = " ".join(words[i : i + 3]).strip()
                if part_phrase:
                    phrases.append(part_phrase)

    if not phrases:
        return []

    total_frames = max(1, int(duration * fps))
    weights = []
    for p in phrases:
        word_cnt = max(1, len(p.split()))
        char_cnt = len(re.sub(r"\s+", "", p))
        weights.append(max(2.6, word_cnt * 2.0 + char_cnt * 0.4))

    total_w = sum(weights)
    cues: list[tuple[int, int, str]] = []
    cursor = max(1, int(fps * 0.15))

    for idx, (phrase, w) in enumerate(zip(phrases, weights)):
        if cursor >= total_frames - 1:
            break
        span = max(int(fps * 0.95), int(round((total_frames - cursor) * (w / total_w))))
        start_f = min(cursor, total_frames - 1)
        if idx == len(phrases) - 1:
            end_f = total_frames - 1
        else:
            end_f = min(total_frames - 1, max(start_f + 3, start_f + span - 2))

        cues.append((start_f, end_f, phrase))
        cursor = end_f + 2

    return cues


def draw_linear_equalizer(
    frame: Image.Image,
    f_idx: int,
    amp: float,
    eq_rgba: tuple[int, int, int, int],
    style: str = EQ_STYLE,
) -> int:
    """
    اکولایزر خطی حساس به وکال و ریتم را روی بک‌گراند ریلز رسم می‌کند
    و مختصات پایین اکولایزر را برمی‌گرداند.
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


def draw_centered_bold_text(
    frame: Image.Image,
    text: str,
    font_bold,
    emoji_font,
    color_rgba: tuple[int, int, int, int],
):
    """متن بولد فارسی، رنگی و دارای ایموجی را با چینش راست‌به‌چپ صحیح در وسط ویدئو رسم می‌کند."""
    rendered_text = _shape_persian_text(text)
    draw = ImageDraw.Draw(frame)
    bbox = draw.textbbox((0, 0), rendered_text, font=font_bold)
    tw = max(1, bbox[2] - bbox[0])
    th = max(1, bbox[3] - bbox[1])

    pad_x = 28
    pad_y = 18
    box_w = min(WIDTH - 32, tw + pad_x * 2)
    box_h = th + pad_y * 2

    txt_canvas = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    tdraw = ImageDraw.Draw(txt_canvas)

    tdraw.rounded_rectangle(
        (2, 2, box_w - 2, box_h - 2),
        radius=16,
        fill=(0, 0, 0, 150),
    )

    tx = max(10, (box_w - tw) // 2)
    ty = max(8, (box_h - th) // 2)

    for ox, oy in ((-3, 0), (3, 0), (0, -3), (0, 3), (-2, -2), (2, 2), (-2, 2), (2, -2)):
        tdraw.text((tx + ox, ty + oy), rendered_text, font=font_bold, fill=(0, 0, 0, 240))

    tdraw.text((tx, ty), rendered_text, font=font_bold, fill=color_rgba)

    if emoji_font is not None:
        emoji_chars = "".join(ch for ch in text if ord(ch) > 0x1F300)
        if emoji_chars:
            try:
                ebbox = tdraw.textbbox((0, 0), emoji_chars, font=emoji_font)
                ew = max(1, ebbox[2] - ebbox[0])
                eh = max(1, ebbox[3] - ebbox[1])
                tdraw.text(
                    (max(6, box_w - ew - 12), max(2, (box_h - eh) // 2)),
                    emoji_chars,
                    font=emoji_font,
                    embedded_color=True,
                )
            except Exception:
                pass

    paste_x = max(10, (WIDTH - box_w) // 2)
    paste_y = max(10, (HEIGHT - box_h) // 2)
    frame.paste(txt_canvas, (paste_x, paste_y), txt_canvas)


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
    صدای اصلی ویدئو را قطع می‌کند، اکولایزر خطی حساس به وکال/ریتم و متن بولد فارسی را روی بک‌گراند می‌گذارد
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

    energies = extract_vocal_and_rhythm_envelope(audio_path, start_sec, duration, FPS)
    cues = build_rhythmic_cues(lyrics_text, duration, FPS, energies)
    _log(f"تعداد عبارات زمان‌بندی‌شده: {len(cues)}")

    ensure_default_logos()
    font_wm = load_bold_font(18)
    font_center = load_bold_font(44)
    emoji_font = load_emoji_font(44)

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
            amp = energies[f_idx] if f_idx < len(energies) else 0.2

            active_text = ""
            cue_index = 0
            for idx, (s_f, e_f, tok) in enumerate(cues):
                if s_f <= f_idx <= e_f:
                    active_text = tok
                    cue_index = idx
                    break

            text_rgba = TEXT_COLOR_PALETTE[cue_index % len(TEXT_COLOR_PALETTE)]
            eq_rgba = EQ_COLOR_PALETTE[(cue_index + 1) % len(EQ_COLOR_PALETTE)]

            draw_linear_equalizer(frame, f_idx, amp, eq_rgba, style=EQ_STYLE)

            if active_text:
                draw_centered_bold_text(
                    frame=frame,
                    text=active_text,
                    font_bold=font_center,
                    emoji_font=emoji_font,
                    color_rgba=text_rgba,
                )

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
        return True, f"ریلز {duration:.0f} ثانیه‌ای با متن فارسی راست‌به‌چپ و متصل آماده شد."

    except Exception as e:
        _log(f"استثنا در build_synced_reel: {e}")
        for p in (dec_proc, enc_proc):
            if p.poll() is None:
                p.kill()
        return False, f"خطا در ساخت ویدئو: {str(e)[:300]}"
