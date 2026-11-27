import os
import subprocess
from PIL import Image, ImageDraw

TG_TEXT = "t.me/remixiyu"
IG_TEXT = "remixiyu"
TG_LOGO_PATH = "tg_logo.png"
IG_LOGO_PATH = "ig_logo.png"
MAX_DURATION = 60


def ensure_default_logos():
    """در صورت نبود فایل لوگو در مخزن، آیکون گرافیکی تمیز تلگرام و اینستاگرام می‌سازد."""
    if not os.path.exists(TG_LOGO_PATH):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse((2, 2, 62, 62), fill=(36, 161, 222, 235))
        draw.polygon(
            [(16, 33), (48, 19), (41, 47), (31, 38), (26, 43), (26, 36)],
            fill=(255, 255, 255, 255),
        )
        img.save(TG_LOGO_PATH)

    if not os.path.exists(IG_LOGO_PATH):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle((4, 4, 60, 60), radius=16, fill=(225, 48, 108, 235))
        draw.rounded_rectangle(
            (13, 13, 51, 51), radius=11, outline=(255, 255, 255, 255), width=4
        )
        draw.ellipse((23, 23, 41, 41), outline=(255, 255, 255, 255), width=4)
        draw.ellipse((43, 17, 47, 21), fill=(255, 255, 255, 255))
        img.save(IG_LOGO_PATH)


def find_font_file() -> str:
    """یک فایل فونت معتبر روی سیستم پیدا می‌کند تا drawtext خطای فونت ندهد."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return ""


def parse_time_to_seconds(t_str: str) -> int:
    parts = [int(x.strip()) for x in t_str.strip().split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    elif len(parts) == 1:
        return parts[0]
    raise ValueError("فرمت زمان نامعتبر است. مثال درست: 00:35")


def _escape_drawtext(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
    )


def build_reel_video(
    audio_path: str,
    output_path: str,
    start_str: str,
    end_str: str,
    bg_path: str = "bg.mp4",
    hook_text: str = "",
) -> tuple[bool, str]:
    ensure_default_logos()

    start_sec = parse_time_to_seconds(start_str)
    end_sec = parse_time_to_seconds(end_str)

    if end_sec <= start_sec:
        return False, "زمان پایان باید بزرگ‌تر از زمان شروع باشد."

    duration = min(end_sec - start_sec, MAX_DURATION)

    has_bg = os.path.exists(bg_path)
    is_video_bg = has_bg and bg_path.lower().endswith(
        (".mp4", ".mov", ".mkv", ".webm")
    )

    # ایندکس 0: پس‌زمینه 1080x1920
    if is_video_bg:
        bg_inputs = ["-stream_loop", "-1", "-i", bg_path]
    elif has_bg:
        bg_inputs = ["-loop", "1", "-i", bg_path]
    else:
        bg_inputs = ["-f", "lavfi", "-i", "color=c=#0b0e17:s=1080x1920:r=30"]

    font_path = find_font_file()
    font_opt = f":fontfile='{_escape_drawtext(font_path)}'" if font_path else ""

    filters = [
        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,setsar=1,eq=brightness=-0.10,format=rgba[v0]"
    ]
    current_label = "v0"
    next_input_idx = 1
    step_idx = 1

    # متن قلاب اختیاری
    if hook_text.strip():
        safe_hook = _escape_drawtext(hook_text.strip())
        hook_lbl = f"v_hook_{step_idx}"
        step_idx += 1
        filters.append(
            f"[{current_label}]drawtext=text='{safe_hook}'{font_opt}:"
            f"fontcolor=white@0.95:fontsize=42:"
            f"x=(w-text_w)/2:y=340:"
            f"box=1:boxcolor=black@0.45:boxborderw=14[{hook_lbl}]"
        )
        current_label = hook_lbl

    # واترماک تلگرام: [لوگو] + t.me/remixiyu
    tg_y = 140
    tg_logo_idx = next_input_idx
    next_input_idx += 1
    bg_inputs.extend(["-i", TG_LOGO_PATH])

    tg_icon_lbl = f"tg_ico_{step_idx}"
    tg_comp_lbl = f"v_tg_{step_idx}"
    step_idx += 1

    filters.append(f"[{tg_logo_idx}:v]scale=40:40,format=rgba[{tg_icon_lbl}]")
    filters.append(
        f"[{current_label}][{tg_icon_lbl}]overlay=x=305:y={tg_y}+4[{tg_comp_lbl}]"
    )
    current_label = tg_comp_lbl

    safe_tg = _escape_drawtext(TG_TEXT)
    tg_txt_lbl = f"v_tg_txt_{step_idx}"
    step_idx += 1
    filters.append(
        f"[{current_label}]drawtext=text='{safe_tg}'{font_opt}:"
        f"fontcolor=white@0.85:fontsize=32:"
        f"x=358:y={tg_y}+8:"
        f"shadowcolor=black@0.7:shadowx=2:shadowy=2[{tg_txt_lbl}]"
    )
    current_label = tg_txt_lbl

    # واترماک اینستاگرام: [لوگو] + remixiyu
    ig_y = 198
    ig_logo_idx = next_input_idx
    next_input_idx += 1
    bg_inputs.extend(["-i", IG_LOGO_PATH])

    ig_icon_lbl = f"ig_ico_{step_idx}"
    ig_comp_lbl = f"v_ig_{step_idx}"
    step_idx += 1

    filters.append(f"[{ig_logo_idx}:v]scale=40:40,format=rgba[{ig_icon_lbl}]")
    filters.append(
        f"[{current_label}][{ig_icon_lbl}]overlay=x=345:y={ig_y}+4[{ig_comp_lbl}]"
    )
    current_label = ig_comp_lbl

    safe_ig = _escape_drawtext(IG_TEXT)
    ig_txt_lbl = f"v_ig_txt_{step_idx}"
    step_idx += 1
    filters.append(
        f"[{current_label}]drawtext=text='{safe_ig}'{font_opt}:"
        f"fontcolor=white@0.85:fontsize=32:"
        f"x=398:y={ig_y}+8:"
        f"shadowcolor=black@0.7:shadowx=2:shadowy=2[{ig_txt_lbl}]"
    )
    current_label = ig_txt_lbl

    # ایندکس واقعی فایل صوتی (بعد از پس‌زمینه و دو لوگو)
    audio_input_idx = next_input_idx
    filter_complex = ";".join(filters)

    cmd = [
        "ffmpeg",
        "-y",
        "-nostats",
        "-loglevel",
        "error",
        *bg_inputs,
        "-ss",
        str(start_sec),
        "-t",
        str(duration),
        "-i",
        audio_path,
        "-filter_complex",
        filter_complex,
        "-map",
        f"[{current_label}]",
        "-map",
        f"{audio_input_idx}:a",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-pix_fmt",
        "yuv420p",
        "-shortest",
        output_path,
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True, f"ریلز {duration} ثانیه‌ای (1080x1920) با واترماک آماده شد."
    except subprocess.CalledProcessError as e:
        raw_err = e.stderr.decode("utf-8", errors="ignore").strip()
        return False, f"خطا در ffmpeg:\n{raw_err[-1500:] if raw_err else 'خروجی خطا خالی بود'}"
