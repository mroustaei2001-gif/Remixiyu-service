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


def get_bold_font_path() -> str | None:
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
            return path
    return None


def load_bold_font(size: int):
    path = get_bold_font_path()
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
    انرژی وکال و ترکیب وکال+ریتم را استخراج می‌کند:
    - خروجی اول: ترکیب ۷۸٪ وکال + ۲۲٪ ریتم برای حرکت اکولایزر خطی
    - خروجی دوم: انرژی خالص وکال برای تشخیص بازه‌های فعالِ خواندن و سینک متن
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


def _clean_phrase_text(raw: str) -> str:
    """نقطه‌ها و نشانه‌های اضافی تبدیل‌صوت را تمیز می‌کند و حروف را به فارسی نرمال می‌کند."""
    cleaned = _normalize_persian_chars(raw)
    cleaned = re.sub(r"[.،؛:]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def build_vocal_synced_cues(
    lyrics_text: str, duration: float, fps: int, vocal_env: list[float]
) -> list[tuple[int, int, str]]:
    """
    متن را بر اساس خط‌بندی کاربر (یا جداکننده |) می‌گیرد و فقط در فریم‌هایی که
    انرژی وکال فعال است توزیع می‌کند تا متن در بخش‌های بی‌کلام جلو نزند و با خواننده سینک بماند.
    """
    clean = lyrics_text.strip()
    if not clean:
        return []

    has_explicit_lines = ("\n" in clean) or ("|" in clean)
    raw_chunks = [part.strip() for part in re.split(r"\n+|\s*\|\s*", clean) if part.strip()]

    phrases: list[str] = []
    for ch in raw_chunks:
        cleaned_ch = _clean_phrase_text(ch)
        if not cleaned_ch:
            continue
        words = [w.strip() for w in cleaned_ch.split() if w.strip()]
        # اگر کاربر خط‌بندی دستی کرده باشد، به خطوط او احترام می‌گذاریم (تا ۵ کلمه در یک خط)
        max_words = 5 if has_explicit_lines else 3
        if len(words) <= max_words:
            phrases.append(cleaned_ch)
        else:
            for i in range(0, len(words), max_words):
                part_phrase = " ".join(words[i : i + max_words]).strip()
                if part_phrase:
                    phrases.append(part_phrase)

    if not phrases:
        return []

    total_frames = max(1, len(vocal_env))
    # آستانه تشخیص فعال بودن صدای خواننده در هر فریم
    avg_vocal = sum(vocal_env) / total_frames
    threshold = max(0.14, avg_vocal * 0.58)
    active_frames = [idx for idx, val in enumerate(vocal_env) if val >= threshold]

    # اگر کل فایل خیلی آرام بود، از کل فریم‌ها استفاده می‌کنیم
    if len(active_frames) < len(phrases) * 4:
        active_frames = list(range(total_frames))

    weights = []
    for p in phrases:
        word_cnt = max(1, len(p.split()))
        char_cnt = len(re.sub(r"\s+", "", p))
        weights.append(max(2.5, word_cnt * 2.1 + char_cnt * 0.45))

    total_w = sum(weights)
    n_active = len(active_frames)
    cues: list[tuple[int, int, str]] = []
    act_cursor = 0

    for idx, (phrase, w) in enumerate(zip(phrases, weights)):
        if act_cursor >= n_active:
            break
        remaining_w = sum(weights[idx:])
        remaining_act = n_active - act_cursor
        take = max(4, int(round(remaining_act * (w / max(0.1, remaining_w)))))
        end_act = n_active - 1 if idx == len(phrases) - 1 else min(n_active - 1, act_cursor + take - 1)

        start_f = active_frames[act_cursor]
        end_f = active_frames[end_act]
        if end_f < start_f:
            end_f = start_f

        cues.append((start_f, end_f, phrase))
        act_cursor = end_act + 1

    return cues


def _render_text_via_ffmpeg_drawtext(
    text: str, font_path: str, color_rgba: tuple[int, int, int, int]
) -> Image.Image | None:
    """
    متن فارسی را مستقیماً با موتور شکل‌دهی داخلی ffmpeg (HarfBuzz/FriBidi) روی تصویر شفاف رندر می‌کند
    تا حروف فارسی ۱۰۰٪ متصل و راست‌به‌چپ باشند.
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

        vf = (
            f"drawtext=fontfile='{safe_font}':textfile='{safe_txt}':"
            f"text_shaping=1:fontsize=44:fontcolor={hex_color}:"
            f"borderw=3:bordercolor=black@0.95:"
            f"x=(w-text_w)/2:y=(h-text_h)/2"
        )
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black@0.0:s={WIDTH}x130:d=0.05",
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
                    pad_x, pad_y = 26, 16
                    x0 = max(0, bbox[0] - pad_x)
                    y0 = max(0, bbox[1] - pad_y)
                    x1 = min(img.width, bbox[2] + pad_x)
                    y1 = min(img.height, bbox[3] + pad_y)
                    cropped = img.crop((x0, y0, x1, y1))

                    bg = Image.new("RGBA", cropped.size, (0, 0, 0, 0))
                    bdraw = ImageDraw.Draw(bg)
                    bdraw.rounded_rectangle(
                        (0, 0, cropped.width - 1, cropped.height - 1),
                        radius=16,
                        fill=(0, 0, 0, 145),
                    )
                    bg.paste(cropped, (0, 0), cropped)
                    return bg
        except Exception as e:
            _log(f"drawtext fallback فعال شد: {e}")
    return None


def _render_text_via_pillow_fallback(
    text: str, font_bold, emoji_font, color_rgba: tuple[int, int, int, int]
) -> Image.Image:
    """رندر پشتیبان در صورتی که ffmpeg بدون drawtext کامپایل شده باشد."""
    s = _normalize_persian_chars(text)
    if _FA_RESHAPER is not None and get_display is not None:
        try:
            s = get_display(_FA_RESHAPER.reshape(s))
        except Exception:
            pass

    dummy = Image.new("RGBA", (WIDTH, 140), (0, 0, 0, 0))
    draw = ImageDraw.Draw(dummy)
    bbox = draw.textbbox((0, 0), s, font=font_bold)
    tw = max(1, bbox[2] - bbox[0])
    th = max(1, bbox[3] - bbox[1])

    box_w = min(WIDTH - 32, tw + 56)
    box_h = th + 36
    canvas = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    tdraw = ImageDraw.Draw(canvas)
    tdraw.rounded_rectangle((0, 0, box_w - 1, box_h - 1), radius=16, fill=(0, 0, 0, 145))

    tx = max(10, (box_w - tw) // 2)
    ty = max(8, (box_h - th) // 2)
    for ox, oy in ((-3, 0), (3, 0), (0, -3), (0, 3)):
        tdraw.text((tx + ox, ty + oy), s, font=font_bold, fill=(0, 0, 0, 240))
    tdraw.text((tx, ty), s, font=font_bold, fill=color_rgba)
    return canvas


def pre_render_cue_overlays(
    cues: list[tuple[int, int, str]],
    font_path: str | None,
    font_bold,
    emoji_font,
) -> dict[int, Image.Image]:
    """تصویر هر عبارت متنی را فقط یک بار می‌سازد تا ویدئو هم سریع‌تر و هم با فارسی واقعی رندر شود."""
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
            img = _render_text_via_pillow_fallback(norm_phrase, font_bold, emoji_font, color_rgba)
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
    صدای اصلی ویدئو را قطع می‌کند، اکولایزر خطی حساس به وکال/ریتم و متن بولد فارسی واقعی را روی بک‌گراند می‌گذارد
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
    cues = build_vocal_synced_cues(lyrics_text, duration, FPS, vocal_env)
    _log(f"تعداد عبارات زمان‌بندی‌شده با وکال: {len(cues)}")

    ensure_default_logos()
    font_path = get_bold_font_path()
    font_wm = load_bold_font(18)
    font_center = load_bold_font(44)
    emoji_font = load_emoji_font(44)

    cue_overlays = pre_render_cue_overlays(cues, font_path, font_center, emoji_font)

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
        return True, f"ریلز {duration:.0f} ثانیه‌ای با رندر واقعی فارسی و سینک با وکال آماده شد."

    except Exception as e:
        _log(f"استثنا در build_synced_reel: {e}")
        for p in (dec_proc, enc_proc):
            if p.poll() is None:
                p.kill()
        return False, f"خطا در ساخت ویدئو: {str(e)[:300]}"
