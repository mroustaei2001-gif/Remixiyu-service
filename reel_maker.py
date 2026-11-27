import os
import subprocess
from PIL import Image, ImageDraw, ImageFont

TG_TEXT = "t.me/remixiyu"
IG_TEXT = "remixiyu"
TG_LOGO_PATH = "tg_logo.png"
IG_LOGO_PATH = "ig_logo.png"
MAX_DURATION = 60
WIDTH = 720
HEIGHT = 1280
FPS = 20


def ensure_default_logos():
    """در صورت نبود فایل لوگو در مخزن، آیکون گرافیکی تمیز تلگرام و اینستاگرام می‌سازد."""
    if not os.path.exists(TG_LOGO_PATH):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse((2, 2, 62, 62), fill=(36, 161, 222, 240))
        draw.polygon(
            [(16, 33), (48, 19), (41, 47), (31, 38), (26, 43), (26, 36)],
            fill=(255, 255, 255, 255),
        )
        img.save(TG_LOGO_PATH)

    if not os.path.exists(IG_LOGO_PATH):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle((4, 4, 60, 60), radius=16, fill=(225, 48, 108, 240))
        draw.rounded_rectangle(
            (13, 13, 51, 51), radius=11, outline=(255, 255, 255, 255), width=4
        )
        draw.ellipse((23, 23, 41, 41), outline=(255, 255, 255, 255), width=4)
        draw.ellipse((43, 17, 47, 21), fill=(255, 255, 255, 255))
        img.save(IG_LOGO_PATH)


def load_font(size: int):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def parse_time_to_seconds(t_str: str) -> int:
    parts = [int(x.strip()) for x in t_str.strip().split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    elif len(parts) == 1:
        return parts[0]
    raise ValueError("فرمت زمان نامعتبر است. مثال درست: 00:35")


def build_watermark_layer(layer_path: str, hook_text: str = ""):
    """یک لایه شفاف شامل واترماک لوگو + متن تلگرام و اینستاگرام می‌سازد."""
    ensure_default_logos()
    canvas = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    font_wm = load_font(24)
    font_hook = load_font(32)

    # لوگو و متن تلگرام: [لوگو] + t.me/remixiyu
    tg_y = 95
    tg_logo = Image.open(TG_LOGO_PATH).convert("RGBA").resize((32, 32))
    tg_x_start = 200
    canvas.paste(tg_logo, (tg_x_start, tg_y), tg_logo)
    draw.text(
        (tg_x_start + 42, tg_y + 3),
        TG_TEXT,
        font=font_wm,
        fill=(255, 255, 255, 225),
    )

    # لوگو و متن اینستاگرام: [لوگو] + remixiyu
    ig_y = 138
    ig_logo = Image.open(IG_LOGO_PATH).convert("RGBA").resize((32, 32))
    ig_x_start = 225
    canvas.paste(ig_logo, (ig_x_start, ig_y), ig_logo)
    draw.text(
        (ig_x_start + 42, ig_y + 3),
        IG_TEXT,
        font=font_wm,
        fill=(255, 255, 255, 225),
    )

    # متن قلاب اختیاری
    if hook_text.strip():
        clean_hook = hook_text.strip()
        bbox = draw.textbbox((0, 0), clean_hook, font=font_hook)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        hx = max(16, (WIDTH - tw) // 2)
        hy = 230
        pad_x, pad_y = 14, 8
        draw.rounded_rectangle(
            (hx - pad_x, hy - pad_y, hx + tw + pad_x, hy + th + pad_y),
            radius=12,
            fill=(0, 0, 0, 130),
        )
        draw.text((hx, hy), clean_hook, font=font_hook, fill=(255, 255, 255, 250))

    canvas.save(layer_path, format="PNG")


def build_reel_video(
    audio_path: str,
    output_path: str,
    start_str: str,
    end_str: str,
    bg_path: str = "bg.mp4",
    hook_text: str = "",
) -> tuple[bool, str]:
    if not os.path.exists(audio_path):
        return False, "فایل صوتی ورودی یافت نشد."

    start_sec = parse_time_to_seconds(start_str)
    end_sec = parse_time_to_seconds(end_str)

    if end_sec <= start_sec:
        return False, "زمان پایان باید بزرگ‌تر از زمان شروع باشد."

    duration = min(end_sec - start_sec, MAX_DURATION)

    out_dir = os.path.dirname(output_path) or "."
    overlay_png = os.path.join(out_dir, "watermark_overlay.png")
    build_watermark_layer(overlay_png, hook_text=hook_text)

    has_bg = os.path.exists(bg_path)
    is_video_bg = has_bg and bg_path.lower().endswith(
        (".mp4", ".mov", ".mkv", ".webm")
    )

    if is_video_bg:
        bg_inputs = ["-stream_loop", "-1", "-i", bg_path]
    elif has_bg:
        bg_inputs = ["-loop", "1", "-i", bg_path]
    else:
        bg_inputs = ["-f", "lavfi", "-i", f"color=c=#0b0e17:s={WIDTH}x{HEIGHT}:r={FPS}"]

    filter_complex = (
        f"[0:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},fps={FPS},setsar=1,eq=brightness=-0.10[bg];"
        f"[bg][1:v]overlay=0:0:shortest=1[vout]"
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-threads",
        "1",
        *bg_inputs,
        "-loop",
        "1",
        "-i",
        overlay_png,
        "-ss",
        str(start_sec),
        "-t",
        str(duration),
        "-i",
        audio_path,
        "-filter_complex",
        filter_complex,
        "-map",
        "[vout]",
        "-map",
        "2:a",
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

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            return False, "فایل ویدئویی خروجی ساخته نشد یا خالی است."
        return True, f"ریلز {duration} ثانیه‌ای ({WIDTH}x{HEIGHT}) با واترماک آماده شد."
    except subprocess.CalledProcessError as e:
        if e.returncode == -9:
            return (
                False,
                "خطا در ffmpeg (کد -9): حتی با تنظیمات کم‌مصرف هم رم کانتینر پر شد. برای ساخت ریلز به رم بیشتر یا اجرای جداگانه نیاز است.",
            )
        err_out = (e.stderr or b"").decode("utf-8", errors="ignore").strip()
        std_out = (e.stdout or b"").decode("utf-8", errors="ignore").strip()
        combined = f"{err_out}\n{std_out}".strip()
        return False, f"خطا در ffmpeg (کد {e.returncode}):\n{combined[-1400:] or 'جزئیاتی ثبت نشد'}"
