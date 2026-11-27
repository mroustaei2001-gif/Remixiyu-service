import math
import os
import re
import struct
import subprocess
import sys
import tempfile
import requests
from PIL import Image, ImageDraw, ImageFont

TG_TEXT = "t.me/remixiyu"
IG_TEXT = "remixiyu"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(BASE_DIR, "fonts")
AUTO_FONT_PATH = os.path.join(FONTS_DIR, "ReelBoldFont.ttf")
TG_LOGO_PATH = os.path.join(BASE_DIR, "tg_logo.png")
IG_LOGO_PATH = os.path.join(BASE_DIR, "ig_logo.png")

FONT_DOWNLOAD_URLS = [
    "https://github.com/google/fonts/raw/main/ofl/vazirmatn/Vazirmatn%5Bwght%5D.ttf",
    "https://github.com/google/fonts/raw/main/ofl/notosansarabic/NotoSansArabic%5Bwdth%2Cwght%5D.ttf",
    "https://github.com/google/fonts/raw/main/ofl/inter/Inter%5Bopsz%2Cwght%5D.ttf",
]

MAX_DURATION = 60
WIDTH = 720
HEIGHT = 1280
FPS = 20
WM_ALPHA = 102  # حدود ۴۰ درصد شفافیت (0.4 * 255)

COLOR_PALETTE = [
    (255, 255, 255, 252),  # سفید خالص
    (255, 214, 10, 252),   # زرد طلایی
    (120, 220, 255, 252),  # آبی روشن
    (255, 130, 185, 252),  # صورتی ملایم
]


def _log(msg: str):
    print(f"[REEL_MAKER] {msg}", file=sys.stderr, flush=True)


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
    """در صورت نبود فونت بولد روی سیستم، فونت را به صورت خودکار دانلود می‌کند."""
    if os.path.exists(AUTO_FONT_PATH) and os.path.getsize(AUTO_FONT_PATH) > 10000:
        return AUTO_FONT_PATH

    os.makedirs(FONTS_DIR, exist_ok=True)
    for url in FONT_DOWNLOAD_URLS:
        try:
            _log(f"در حال دانلود فونت بولد: {url}")
            resp = requests.get(url, timeout=20)
            if resp.status_code == 200 and resp.content and len(resp.content) > 10000:
                tmp_font = AUTO_FONT_PATH + ".tmp"
                with open(tmp_font, "wb") as f:
                    f.write(resp.content)
                os.replace(tmp_font, AUTO_FONT_PATH)
                _log("فونت بولد با موفقیت دانلود و ذخیره شد.")
                return AUTO_FONT_PATH
        except Exception as e:
            _log(f"خطا در دانلود فونت از {url}: {e}")

    return None


def _apply_font_variation_bold(font, weight: int = 800):
    """اگر فونت متغیر (Variable) باشد، وزن را روی Bold/ExtraBold تنظیم می‌کند."""
    try:
        if hasattr(font, "set_variation_by_axes"):
            font.set_variation_by_axes([weight])
    except Exception:
        try:
            if hasattr(font, "set_variation_by_name"):
                font.set_variation_by_name("Bold")
        except Exception:
            pass
    return font


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
                f = ImageFont.truetype(path, size=size)
                return _apply_font_variation_bold(f, weight=800)
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


def extract_beat_envelope(
    audio_path: str, start_sec: float, duration: float, fps: int
) -> list[float]:
    """انرژی هر فریم از موزیک را استخراج می‌کند تا متن و اکولایزر با ریتم سینک شوند."""
    total_frames = max(1, int(duration * fps))
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
        "-f",
        "s16le",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        pcm_path,
    ]
    try:
        subprocess.run(
            cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45
        )
        with open(pcm_path, "rb") as f:
            raw = f.read()
    except Exception as e:
        _log(f"خطای استخراج ریتم صدا: {e}")
        return [0.35] * total_frames
    finally:
        if os.path.exists(pcm_path):
            os.remove(pcm_path)

    if not raw:
        return [0.35] * total_frames

    count = len(raw) // 2
    samples = struct.unpack(f"<{count}h", raw[: count * 2])
    samples_per_frame = max(1, count // total_frames)

    energies: list[float] = []
    smoothed = 0.25
    for i in range(total_frames):
        chunk = samples[i * samples_per_frame : (i + 1) * samples_per_frame]
        if not chunk:
            energies.append(smoothed)
            continue
        rms = math.sqrt(sum(s * s for s in chunk) / len(chunk)) / 32768.0
        raw_val = min(1.0, (rms * 4.2) ** 0.75)
        smoothed = smoothed * 0.45 + max(0.08, raw_val) * 0.55
        energies.append(smoothed)

    return energies


def build_rhythmic_cues(
    lyrics_text: str, duration: float, fps: int, energies: list[float]
) -> list[tuple[int, int, str]]:
    """
    متن تاییدشده را به عبارات کوتاهِ طبیعی (۲ تا ۳ کلمه‌ای) تقسیم می‌کند تا سرعت نمایش
    از خواننده جلو نزند و با ریتم موزیک همگام باشد.
    """
    clean = lyrics_text.strip()
    if not clean:
        return []

    raw_chunks = [part.strip() for part in re.split(r"\n+|\s*\|\s*", clean) if part.strip()]
    phrases: list[str] = []
    for ch in raw_chunks:
        words = [w.strip() for w in ch.split() if w.strip()]
        if len(words) <= 3:
            phrases.append(ch)
        else:
            for i in range(0, len(words), 3):
                phrases.append(" ".join(words[i : i + 3]))

    if not phrases:
        return []

    total_frames = max(1, int(duration * fps))
    weights = [max(2.0, len(re.sub(r"\s+", "", p)) * 0.85) for p in phrases]
    total_w = sum(weights)

    cues: list[tuple[int, int, str]] = []
    cursor = 0
    for idx, (phrase, w) in enumerate(zip(phrases, weights)):
        span = max(int(fps * 0.9), int(round(total_frames * (w / total_w))))
        start_f = min(cursor, total_frames - 1)
        if idx == len(phrases) - 1:
            end_f = total_frames - 1
        else:
            end_f = min(total_frames - 1, max(start_f + 2, start_f + span - 2))

        cues.append((start_f, end_f, phrase))
        cursor = end_f + 3

    return cues


def draw_equalizer_on_background(
    frame: Image.Image, f_idx: int, amp: float, accent_rgba: tuple[int, int, int, int]
):
    """اکولایزر میله‌ای را مستقیماً روی بک‌گراند ریلز (در پایینِ وسط، بالای واترماک) رسم می‌کند."""
    draw = ImageDraw.Draw(frame)
    bar_count = 28
    bar_w = 10
    gap = 6
    total_w = bar_count * bar_w + (bar_count - 1) * gap
    start_x = (WIDTH - total_w) // 2
    base_y = HEIGHT - 155
    max_bar_h = 72

    r, g, b, _ = accent_rgba
    bar_color = (r, g, b, 210)

    for i in range(bar_count):
        center_dist = abs(i - (bar_count - 1) / 2.0) / ((bar_count - 1) / 2.0)
        arch = max(0.35, 1.0 - 0.55 * (center_dist ** 1.4))
        wave = 0.55 + 0.45 * math.sin(f_idx * 0.35 + i * 0.55)
        h = max(8, int(max_bar_h * amp * arch * wave))

        x0 = start_x + i * (bar_w + gap)
        y0 = base_y - h
        x1 = x0 + bar_w
        y1 = base_y
        draw.rounded_rectangle((x0, y0, x1, y1), radius=5, fill=bar_color)


def make_fixed_bottom_watermark(tg_logo: Image.Image, ig_logo: Image.Image, font_wm) -> Image.Image:
    """واترمارک کوچک، ۴۰٪ شفاف و زیر هم بدون فاصله برای قرارگیری ثابت در پایین صفحه."""
    block_w = 240
    block_h = 44  # دو ردیف ۲۲ پیکسلی زیر هم بدون فاصله
    block = Image.new("RGBA", (block_w, block_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(block)

    icon_size = 20
    row_step = 22  # بدون فاصله عمودی بین دو خط

    block.paste(tg_logo, (0, 1), tg_logo)
    draw.text((icon_size + 5, 2), TG_TEXT, font=font_wm, fill=(255, 255, 255, WM_ALPHA))

    block.paste(ig_logo, (0, row_step + 1), ig_logo)
    draw.text((icon_size + 5, row_step + 2), IG_TEXT, font=font_wm, fill=(255, 255, 255, WM_ALPHA))

    return block


def draw_centered_bold_text(
    frame: Image.Image,
    text: str,
    font_bold,
    emoji_font,
    color_rgba: tuple[int, int, int, int],
):
    """متن بولد، رنگی و دارای ایموجی را با سرعت آرام و هماهنگ با خواننده در وسط ویدئو رسم می‌کند."""
    draw = ImageDraw.Draw(frame)
    bbox = draw.textbbox((0, 0), text, font=font_bold)
    tw = max(1, bbox[2] - bbox[0])
    th = max(1, bbox[3] - bbox[1])

    pad_x = 26
    pad_y = 18
    box_w = min(WIDTH - 36, tw + pad_x * 2)
    box_h = th + pad_y * 2

    txt_canvas = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    tdraw = ImageDraw.Draw(txt_canvas)

    tdraw.rounded_rectangle(
        (2, 2, box_w - 2, box_h - 2),
        radius=18,
        fill=(0, 0, 0, 145),
    )

    tx = max(10, (box_w - tw) // 2)
    ty = max(8, (box_h - th) // 2)

    for ox, oy in ((-2, 0), (2, 0), (0, -2), (0, 2), (2, 2)):
        tdraw.text((tx + ox, ty + oy), text, font=font_bold, fill=(0, 0, 0, 235))

    tdraw.text((tx, ty), text, font=font_bold, fill=color_rgba)

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
    صدای اصلی ویدئو را قطع می‌کند، اکولایزر و متن بولد را روی بک‌گراند می‌گذارد
    و واترماک ثابت کوچک، ۴۰٪ شفاف و زیر هم بدون فاصله را در پایین صفحه قرار می‌دهد.
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
    _log(f"شروع ساخت ریلز ۶۰ ثانیه‌ای/برش‌خورده به مدت {duration:.1f} ثانیه")

    energies = extract_beat_envelope(audio_path, start_sec, duration, FPS)
    cues = build_rhythmic_cues(lyrics_text, duration, FPS, energies)
    _log(f"تعداد عبارات زمان‌بندی‌شده: {len(cues)}")

    ensure_default_logos()
    opacity = WM_ALPHA / 255.0
    font_wm = load_bold_font(18)
    font_center = load_bold_font(44)
    emoji_font = load_emoji_font(44)

    tg_logo = apply_opacity(Image.open(TG_LOGO_PATH).resize((20, 20)), opacity)
    ig_logo = apply_opacity(Image.open(IG_LOGO_PATH).resize((20, 20)), opacity)
    wm_block = make_fixed_bottom_watermark(tg_logo, ig_logo, font_wm)
    wm_w, wm_h = wm_block.size

    fixed_wm_x = (WIDTH - wm_w) // 2
    fixed_wm_y = HEIGHT - wm_h - 48

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

            accent_rgba = COLOR_PALETTE[cue_index % len(COLOR_PALETTE)]

            draw_equalizer_on_background(frame, f_idx, amp, accent_rgba)

            if active_text:
                draw_centered_bold_text(
                    frame=frame,
                    text=active_text,
                    font_bold=font_center,
                    emoji_font=emoji_font,
                    color_rgba=accent_rgba,
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
        return True, f"ریلز {duration:.0f} ثانیه‌ای با بک‌گراند ویدئو/عکس، اکولایزر، فونت بولد و واترماک ثابت پایین آماده شد."

    except Exception as e:
        _log(f"استثنا در build_synced_reel: {e}")
        for p in (dec_proc, enc_proc):
            if p.poll() is None:
                p.kill()
        return False, f"خطا در ساخت ویدئو: {str(e)[:300]}"
