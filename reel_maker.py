import math
import os
import random
import struct
import subprocess
import sys
import tempfile
from PIL import Image, ImageDraw, ImageFilter, ImageFont

TG_TEXT = "t.me/remixiyu"
IG_TEXT = "remixiyu"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TG_LOGO_PATH = os.path.join(BASE_DIR, "tg_logo.png")
IG_LOGO_PATH = os.path.join(BASE_DIR, "ig_logo.png")
CHANNEL_LOGO_PATH = os.path.join(BASE_DIR, "channel_logo.png")
COVER_FALLBACK_PATH = os.path.join(BASE_DIR, "cover.png")

MAX_DURATION = 60
WIDTH = 720
HEIGHT = 1280
FPS = 20

# تنظیمات متعادل و تمیز روی کلیپ (با فضای آزاد در وسط برای متن آهنگ)
WM_TEXT_ALPHA = 165
WM_ICON_OPACITY = 0.94
CHANNEL_AVATAR_SIZE = 32
CHANNEL_AVATAR_OPACITY = 0.96

# پالت‌های رندومِ گرادیانی (هر کلیپ یک پالت ثابت و متمایز می‌گیرد)
RANDOM_WAVE_PALETTES = [
    ((65, 240, 245), (125, 165, 250), (180, 105, 245)),   # فیروزه‌ای به آبی یاسی و بنفش
    ((255, 196, 120), (225, 130, 165), (175, 135, 245)),  # کهربایی گرم + صورتی ملایم + یاسی
    ((245, 145, 185), (170, 165, 250), (125, 215, 250)),  # صورتی ملایم + یاسی + آبی یخی
    ((95, 235, 185), (135, 210, 245), (195, 155, 250)),   # نعنایی نرم + آبی ملایم + یاسی کم‌اشباع
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


def load_wm_font(size: int = 14):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if path and os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def build_channel_avatar(size: int = CHANNEL_AVATAR_SIZE, font_badge=None) -> Image.Image:
    """عکس کانال را به‌صورت دایره‌ای و جمع‌وجور کنار واترمارک آماده می‌کند."""
    src_path = None
    if os.path.exists(CHANNEL_LOGO_PATH):
        src_path = CHANNEL_LOGO_PATH
    elif os.path.exists(COVER_FALLBACK_PATH):
        src_path = COVER_FALLBACK_PATH

    if src_path:
        try:
            raw = Image.open(src_path).convert("RGBA")
            w, h = raw.size
            side = min(w, h)
            left = (w - side) // 2
            top = (h - side) // 2
            cropped = raw.crop((left, top, left + side, top + side)).resize(
                (size, size), Image.Resampling.LANCZOS
            )

            mask = Image.new("L", (size, size), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)

            avatar = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            avatar.paste(cropped, (0, 0), mask)
            ImageDraw.Draw(avatar).ellipse(
                (0, 0, size - 1, size - 1), outline=(255, 255, 255, 195), width=1
            )
            return apply_opacity(avatar, CHANNEL_AVATAR_OPACITY)
        except Exception as e:
            _log(f"خطا در آماده‌سازی عکس کانال: {e}")

    avatar = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(avatar)
    draw.ellipse((1, 1, size - 2, size - 2), fill=(25, 25, 35, 235), outline=(255, 255, 255, 195), width=1)
    badge_font = font_badge or load_wm_font(max(11, size // 2))
    label = "R"
    bbox = draw.textbbox((0, 0), label, font=badge_font)
    lw = bbox[2] - bbox[0]
    lh = bbox[3] - bbox[1]
    draw.text(((size - lw) // 2, (size - lh) // 2 - 1), label, font=badge_font, fill=(255, 255, 255, 240))
    return apply_opacity(avatar, CHANNEL_AVATAR_OPACITY)


def build_bottom_shadow_overlay(width: int = WIDTH, height: int = HEIGHT) -> Image.Image:
    """
    هاله سایه کاملاً یکنواخت و بدون خط مرز در پایین صفحه:
    با منحنی Smootherstep و بلور عمودی تا انتقال از تصویر به سایه اصلاً به چشم نیاید.
    """
    shadow_h = int(height * 0.55)
    start_y = height - shadow_h
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    max_alpha = 242
    for y in range(start_y, height):
        t = (y - start_y) / max(1, shadow_h - 1)
        t_soft = t ** 1.15
        smooth = t_soft * t_soft * t_soft * (t_soft * (t_soft * 6.0 - 15.0) + 10.0)
        alpha = int(max_alpha * smooth)
        draw.line([(0, y), (width - 1, y)], fill=(6, 6, 9, alpha))

    return overlay.filter(ImageFilter.GaussianBlur(radius=16))


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
    """برش دقیق موزیک بین زمان شروع و پایان (حداکثر ۶۰ ثانیه)."""
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
        "192k",
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


def _extract_pcm_envelope(
    audio_path: str,
    start_sec: float,
    duration: float,
    total_frames: int,
    af_filter: str | None = None,
    gain: float = 5.0,
    sample_rate: int = 8000,
) -> list[float]:
    """انرژی هر فریم از سیگنال صوتی را برای باند فرکانسی مشخص استخراج می‌کند."""
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
        return [0.22] * total_frames
    finally:
        if os.path.exists(pcm_path):
            os.remove(pcm_path)

    if not raw:
        return [0.22] * total_frames

    count = len(raw) // 2
    samples = struct.unpack(f"<{count}h", raw[: count * 2])
    samples_per_frame = max(1, count // total_frames)

    out: list[float] = []
    for i in range(total_frames):
        chunk = samples[i * samples_per_frame : (i + 1) * samples_per_frame]
        if not chunk:
            out.append(0.06)
            continue
        rms = math.sqrt(sum(s * s for s in chunk) / len(chunk)) / 32768.0
        val = min(1.0, (rms * gain) ** 0.85)
        out.append(max(0.05, val))
    return out


def extract_rhythm_and_vocal_envelopes(
    audio_path: str, start_sec: float, duration: float, fps: int
) -> tuple[list[float], list[float]]:
    """
    تشخیص مجزا و دقیق‌ترِ ریتم (ضرب/باس) و وکال (صدای خواننده/کلمات تاکیدی).
    """
    total_frames = max(1, int(duration * fps))

    rhythm_raw = _extract_pcm_envelope(
        audio_path,
        start_sec,
        duration,
        total_frames,
        af_filter="lowpass=f=240:p=1,highpass=f=45:p=1",
        gain=5.6,
        sample_rate=8000,
    )

    vocal_raw = _extract_pcm_envelope(
        audio_path,
        start_sec,
        duration,
        total_frames,
        af_filter="bandpass=f=1450:w=1600:t=h",
        gain=6.6,
        sample_rate=8000,
    )

    rhythm_avg = sum(rhythm_raw) / max(1, len(rhythm_raw))
    vocal_avg = sum(vocal_raw) / max(1, len(vocal_raw))

    rhythm_env: list[float] = []
    vocal_env: list[float] = []

    prev_r_raw = rhythm_raw[0] if rhythm_raw else 0.2
    prev_v_raw = vocal_raw[0] if vocal_raw else 0.2
    prev_r_out = 0.22
    prev_v_out = 0.22

    for r_cur, v_cur in zip(rhythm_raw, vocal_raw):
        r_hit = max(0.0, r_cur - prev_r_raw) * 2.2
        if r_cur > rhythm_avg * 1.18:
            r_hit += (r_cur - rhythm_avg * 1.18) * 0.85
        r_target = min(1.0, r_cur * 0.88 + r_hit)
        r_out = max(0.08, r_target * 0.85 + prev_r_out * 0.15)

        v_accent = max(0.0, v_cur - prev_v_raw) * 1.75
        if v_cur > vocal_avg * 1.15:
            v_accent += (v_cur - vocal_avg * 1.15) * 0.80
        v_target = min(1.0, v_cur * 0.90 + v_accent)
        v_out = max(0.08, v_target * 0.82 + prev_v_out * 0.18)

        rhythm_env.append(r_out)
        vocal_env.append(v_out)

        prev_r_raw, prev_v_raw = r_cur, v_cur
        prev_r_out, prev_v_out = r_out, v_out

    return rhythm_env, vocal_env


def _lerp_triple_color(
    c1: tuple[int, int, int],
    c2: tuple[int, int, int],
    c3: tuple[int, int, int],
    t: float,
) -> tuple[int, int, int]:
    """گرادیان سه‌رنگِ نرم از چپ به راست را حساب می‌کند."""
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        k = t * 2.0
        a, b = c1, c2
    else:
        k = (t - 0.5) * 2.0
        a, b = c2, c3
    return (
        int(a[0] + (b[0] - a[0]) * k),
        int(a[1] + (b[1] - a[1]) * k),
        int(a[2] + (b[2] - a[2]) * k),
    )


def draw_intertwined_sine_equalizer(
    frame: Image.Image,
    f_idx: int,
    rhythm_amp: float,
    vocal_amp: float,
    palette: tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]],
) -> int:
    """
    اکولایزر موج‌های سینوسیِ درهم‌تنیده نئونی:
    - ۵ رشته موجِ هم‌تنیده با فرکانس و فاز متفاوت
    - هاله نوریِ دو مرحله‌ای و ذرات نوریِ ریز اطراف موج
    - واکنش رشته‌های اصلی به ریتم و رشته درخشانِ مرکزی به وکال
    - خط جداکننده ظریف بین اکولایزر و واترمارک
    """
    c1, c2, c3 = palette

    wave_w = 340
    wave_h = 96
    pad = 22
    canvas_w = wave_w + pad * 2
    canvas_h = wave_h + pad * 2

    start_x = (WIDTH - canvas_w) // 2
    base_y = HEIGHT - 225

    ambient_glow = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    tight_glow = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    overlay = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

    draw_amb = ImageDraw.Draw(ambient_glow)
    draw_tight = ImageDraw.Draw(tight_glow)
    draw_main = ImageDraw.Draw(overlay)

    center_y = pad + wave_h // 2
    phase = f_idx * 0.20

    # (فرکانس، سرعت فاز، ضریب ارتفاع، شفافیت، ضخامت، نوع واکنش)
    strands = [
        (5.5, 1.00, 1.00, 245, 2, "vocal"),   # موج اصلیِ درخشان (حساس به وکال)
        (4.2, -0.85, 0.92, 185, 2, "rhythm"), # موج دومِ متقاطع (حساس به ریتم)
        (6.8, 1.35, 0.72, 145, 1, "rhythm"),  # موج ظریف‌ترِ سریع
        (3.4, -0.55, 0.80, 120, 1, "both"),   # موج پهنِ پس‌زمینه
        (8.0, 0.70, 0.50, 95, 1, "vocal"),    # رشته نازکِ هارمونیک
    ]

    steps = 85
    max_amp = (wave_h // 2) - 8

    for freq, speed, amp_scale, alpha, stroke_w, mode in strands:
        pts = []
        for s in range(steps + 1):
            u = s / steps
            x = pad + int(u * wave_w)

            envelope = math.sin(u * math.pi) ** 1.35

            if mode == "vocal":
                energy = 0.25 + vocal_amp * 0.85
            elif mode == "rhythm":
                energy = 0.25 + rhythm_amp * 0.85
            else:
                energy = 0.22 + (rhythm_amp * 0.5 + vocal_amp * 0.5) * 0.80

            y_offset = math.sin(u * math.pi * freq - phase * speed) * max_amp * amp_scale * energy * envelope
            y = int(center_y + y_offset)
            pts.append((x, y, u))

        for idx in range(len(pts) - 1):
            x1, y1, u1 = pts[idx]
            x2, y2, _ = pts[idx + 1]
            col = _lerp_triple_color(c1, c2, c3, u1)

            if stroke_w >= 2:
                bright = (min(255, col[0] + 50), min(255, col[1] + 50), min(255, col[2] + 50))
                draw_amb.line([(x1, y1), (x2, y2)], fill=(col[0], col[1], col[2], 125), width=6)
                draw_tight.line([(x1, y1), (x2, y2)], fill=(col[0], col[1], col[2], 190), width=3)
                draw_main.line([(x1, y1), (x2, y2)], fill=(bright[0], bright[1], bright[2], alpha), width=stroke_w)
            else:
                draw_main.line([(x1, y1), (x2, y2)], fill=(col[0], col[1], col[2], alpha), width=1)

    # ذرات نوریِ ریز و متحرک اطراف موج
    for p_idx in range(14):
        u_p = ((p_idx * 0.073 + f_idx * 0.004) % 0.84) + 0.08
        px = pad + int(u_p * wave_w)
        py_shift = math.sin(p_idx * 2.3 + f_idx * 0.12) * (max_amp * 0.85) * (0.4 + rhythm_amp * 0.6)
        py = int(center_y + py_shift)
        col = _lerp_triple_color(c1, c2, c3, u_p)
        p_alpha = int(170 * math.sin(u_p * math.pi))
        draw_main.ellipse((px - 1, py - 1, px + 1, py + 1), fill=(col[0], col[1], col[2], p_alpha))

    amb_blurred = ambient_glow.filter(ImageFilter.GaussianBlur(radius=10))
    tight_blurred = tight_glow.filter(ImageFilter.GaussianBlur(radius=3))

    frame.paste(amb_blurred, (start_x, base_y), amb_blurred)
    frame.paste(tight_blurred, (start_x, base_y), tight_blurred)
    frame.paste(overlay, (start_x, base_y), overlay)

    # خط جداکننده ظریف بین اکولایزر و واترمارک
    divider_y = base_y + pad + wave_h + 10
    div_w = 270
    div_x0 = (WIDTH - div_w) // 2
    div_layer = Image.new("RGBA", (WIDTH, 4), (0, 0, 0, 0))
    div_draw = ImageDraw.Draw(div_layer)
    for dx in range(0, div_w, 3):
        u = dx / max(1, div_w)
        a = int(90 * math.sin(u * math.pi))
        div_draw.line([(div_x0 + dx, 1), (div_x0 + dx + 3, 1)], fill=(220, 225, 240, a), width=1)
    frame.paste(div_layer, (0, divider_y), div_layer)

    return divider_y + 4


def make_fixed_bottom_watermark(
    tg_logo: Image.Image,
    ig_logo: Image.Image,
    channel_avatar: Image.Image,
    font_wm,
    icon_size: int = 15,
) -> Image.Image:
    """
    عکس کانال را به‌صورت مجزا و جمع‌وجور کنار بخش واترمارک (آیکون‌های TG/IG + متن‌ها)
    و در یک ترکیب متعادل و هم‌تراز قرار می‌دهد.
    """
    temp_img = Image.new("RGBA", (1, 1))
    temp_draw = ImageDraw.Draw(temp_img)

    def text_size(txt: str) -> tuple[int, int]:
        bbox = temp_draw.textbbox((0, 0), txt, font=font_wm)
        return max(1, bbox[2] - bbox[0]), max(1, bbox[3] - bbox[1])

    tg_w, tg_h = text_size(TG_TEXT)
    ig_w, ig_h = text_size(IG_TEXT)

    icon_text_gap = 5
    group_gap = 14
    avatar_to_wm_gap = 8
    pad_x = 4
    pad_y = 3

    tg_group_w = icon_size + icon_text_gap + tg_w
    ig_group_w = icon_size + icon_text_gap + ig_w
    wm_part_w = tg_group_w + group_gap + ig_group_w
    wm_part_h = max(icon_size, tg_h, ig_h)

    avatar_w, avatar_h = channel_avatar.size
    total_w = avatar_w + avatar_to_wm_gap + wm_part_w + pad_x * 2
    total_h = max(avatar_h, wm_part_h) + pad_y * 2

    block = Image.new("RGBA", (total_w, total_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(block)

    avatar_x = pad_x
    avatar_y = (total_h - avatar_h) // 2
    block.paste(channel_avatar, (avatar_x, avatar_y), channel_avatar)

    wm_origin_x = avatar_x + avatar_w + avatar_to_wm_gap
    wm_origin_y = (total_h - wm_part_h) // 2
    icon_y = wm_origin_y + (wm_part_h - icon_size) // 2

    tg_x = wm_origin_x
    tg_text_y = wm_origin_y + (wm_part_h - tg_h) // 2
    block.paste(tg_logo, (tg_x, icon_y), tg_logo)
    draw.text(
        (tg_x + icon_size + icon_text_gap, tg_text_y),
        TG_TEXT,
        font=font_wm,
        fill=(255, 255, 255, WM_TEXT_ALPHA),
    )

    ig_x = tg_x + tg_group_w + group_gap
    ig_text_y = wm_origin_y + (wm_part_h - ig_h) // 2
    block.paste(ig_logo, (ig_x, icon_y), ig_logo)
    draw.text(
        (ig_x + icon_size + icon_text_gap, ig_text_y),
        IG_TEXT,
        font=font_wm,
        fill=(255, 255, 255, WM_TEXT_ALPHA),
    )

    return block


def build_synced_reel(
    video_path: str,
    audio_path: str,
    output_path: str,
    start_str: str,
    end_str: str,
    lyrics_text: str = "",
) -> tuple[bool, str]:
    """
    کلیپ پس‌زمینه را هم‌اندازه تایم موزیک کات می‌زند، صدای اصلی کلیپ را قطع می‌کند،
    سایه کاملاً محو و بدون مرز در پایین صفحه اعمال می‌کند، اکولایزر موج‌های درهم‌تنیده را
    با یک پالت رندوم ثابت در پایین قرار می‌دهد و آواتار کانال + واترمارک را زیر آن ذخیره می‌کند.
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

    selected_palette = random.choice(RANDOM_WAVE_PALETTES)
    _log(f"شروع ساخت ریلز {duration:.1f} ثانیه‌ای با پالت رندوم: {selected_palette}")

    rhythm_env, vocal_env = extract_rhythm_and_vocal_envelopes(audio_path, start_sec, duration, FPS)
    bottom_shadow = build_bottom_shadow_overlay(WIDTH, HEIGHT)

    ensure_default_logos()
    icon_px = 15
    font_wm = load_wm_font(14)

    tg_logo = apply_opacity(Image.open(TG_LOGO_PATH).resize((icon_px, icon_px)), WM_ICON_OPACITY)
    ig_logo = apply_opacity(Image.open(IG_LOGO_PATH).resize((icon_px, icon_px)), WM_ICON_OPACITY)
    channel_avatar = build_channel_avatar(size=CHANNEL_AVATAR_SIZE, font_badge=load_wm_font(14))

    wm_block = make_fixed_bottom_watermark(
        tg_logo=tg_logo,
        ig_logo=ig_logo,
        channel_avatar=channel_avatar,
        font_wm=font_wm,
        icon_size=icon_px,
    )
    wm_w, wm_h = wm_block.size

    fixed_wm_x = (WIDTH - wm_w) // 2
    fixed_wm_y = HEIGHT - wm_h - 42

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
        "fast",
        "-threads",
        "1",
        "-x264-params",
        "threads=1:rc-lookahead=0:sync-lookahead=0:bframes=0:ref=1",
        "-crf",
        "19",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
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
            frame = Image.alpha_composite(frame, bottom_shadow)

            r_amp = rhythm_env[f_idx] if f_idx < len(rhythm_env) else 0.2
            v_amp = vocal_env[f_idx] if f_idx < len(vocal_env) else 0.2

            draw_intertwined_sine_equalizer(frame, f_idx, r_amp, v_amp, selected_palette)
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
        return True, f"ریلز {duration:.0f} ثانیه‌ای با سایه محو پایین و اکولایزر موج درهم‌تنیده آماده شد."

    except Exception as e:
        _log(f"استثنا در build_synced_reel: {e}")
        for p in (dec_proc, enc_proc):
            if p.poll() is None:
                p.kill()
        return False, f"خطا در ساخت ویدئو: {str(e)[:300]}"
