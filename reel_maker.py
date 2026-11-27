import math
import os
import struct
import subprocess
import sys
import tempfile
from PIL import Image, ImageDraw, ImageFont

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

# تنظیمات کوچک و جمع‌وجور برای قرار گرفتن روی کلیپ
WM_TEXT_ALPHA = 105        # حدود ۴۰ درصد شفافیت برای متن واترمارک
WM_ICON_OPACITY = 0.85     # وضوح آیکون‌های تلگرام و اینستاگرام
CHANNEL_AVATAR_SIZE = 32   # سایز جمع‌وجور و مجزا برای عکس کانال روی کلیپ
CHANNEL_AVATAR_OPACITY = 0.92
EQ_STYLE = "segmented_linear"

EQ_COLOR_PALETTE = [
    (0, 245, 212, 230),    # فیروزه‌ای نئونی
    (185, 110, 255, 230),  # بنفش یاسی پرانرژی
    (255, 159, 28, 230),   # نارنجی کهربایی
    (72, 229, 132, 230),   # سبز نعنایی
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
                (0, 0, size - 1, size - 1), outline=(255, 255, 255, 180), width=1
            )
            return apply_opacity(avatar, CHANNEL_AVATAR_OPACITY)
        except Exception as e:
            _log(f"خطا در آماده‌سازی عکس کانال: {e}")

    avatar = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(avatar)
    draw.ellipse((1, 1, size - 2, size - 2), fill=(30, 30, 36, 230), outline=(255, 255, 255, 180), width=1)
    badge_font = font_badge or load_wm_font(max(11, size // 2))
    label = "R"
    bbox = draw.textbbox((0, 0), label, font=badge_font)
    lw = bbox[2] - bbox[0]
    lh = bbox[3] - bbox[1]
    draw.text(((size - lw) // 2, (size - lh) // 2 - 1), label, font=badge_font, fill=(255, 255, 255, 235))
    return apply_opacity(avatar, CHANNEL_AVATAR_OPACITY)


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
    تشخیص مجزا و دقیق‌ترِ ریتم (ضرب/باس) و وکال (صدای خواننده/کلمات تاکیدی)
    با نرخ نمونه‌برداری ۸۰۰۰ هرتز تا فیلترهای فرکانسی با دقت بیشتری عمل کنند.
    """
    total_frames = max(1, int(duration * fps))

    # تشخیص ریتم: فیلتر پایین‌گذر برای ضرب‌ها و باس‌های کوبشی
    rhythm_raw = _extract_pcm_envelope(
        audio_path,
        start_sec,
        duration,
        total_frames,
        af_filter="lowpass=f=240:p=1,highpass=f=45:p=1",
        gain=5.2,
        sample_rate=8000,
    )

    # تشخیص وکال: فیلتر میان‌گذر در محدوده صدای خواننده و هارمونیک‌های وکال
    vocal_raw = _extract_pcm_envelope(
        audio_path,
        start_sec,
        duration,
        total_frames,
        af_filter="bandpass=f=1450:w=1600:t=h",
        gain=6.2,
        sample_rate=8000,
    )

    rhythm_avg = sum(rhythm_raw) / max(1, len(rhythm_raw))
    vocal_avg = sum(vocal_raw) / max(1, len(vocal_raw))

    rhythm_env: list[float] = []
    vocal_env: list[float] = []

    prev_r_raw = rhythm_raw[0] if rhythm_raw else 0.2
    prev_v_raw = vocal_raw[0] if vocal_raw else 0.2
    prev_r_out = 0.18
    prev_v_out = 0.18

    for r_cur, v_cur in zip(rhythm_raw, vocal_raw):
        # ضرب‌های ناگهانی ریتم را تیزتر تشخیص می‌دهد
        r_hit = max(0.0, r_cur - prev_r_raw) * 2.1
        if r_cur > rhythm_avg * 1.18:
            r_hit += (r_cur - rhythm_avg * 1.18) * 0.8
        r_target = min(1.0, r_cur * 0.85 + r_hit)
        r_out = max(0.05, r_target * 0.84 + prev_r_out * 0.16)

        # تاکید وکال را نرم‌تر و دقیق‌تر روی کلمات و اوج صدا نشان می‌دهد
        v_accent = max(0.0, v_cur - prev_v_raw) * 1.65
        if v_cur > vocal_avg * 1.15:
            v_accent += (v_cur - vocal_avg * 1.15) * 0.75
        v_target = min(1.0, v_cur * 0.88 + v_accent)
        v_out = max(0.05, v_target * 0.80 + prev_v_out * 0.20)

        rhythm_env.append(r_out)
        vocal_env.append(v_out)

        prev_r_raw, prev_v_raw = r_cur, v_cur
        prev_r_out, prev_v_out = r_out, v_out

    return rhythm_env, vocal_env


def draw_compact_dual_equalizer(
    frame: Image.Image,
    f_idx: int,
    rhythm_amp: float,
    vocal_amp: float,
    eq_rgba: tuple[int, int, int, int],
    style: str = EQ_STYLE,
) -> int:
    """
    اکولایزر کوچک و جمع‌وجور مخصوص روی کلیپ:
    بخش میانی حساس‌تر به وکال و بخش‌های کناری/ضرب‌پذیر حساس‌تر به ریتم.
    """
    draw = ImageDraw.Draw(frame)
    r, g, b, alpha = eq_rgba
    main_color = (r, g, b, alpha)
    dim_color = (r, g, b, max(65, alpha // 2))

    # ابعاد کوچک و متعادل تا روی کلیپ مزاحم نباشد
    line_count = 32
    line_w = 3
    gap = 5
    total_w = line_count * line_w + (line_count - 1) * gap
    start_x = (WIDTH - total_w) // 2
    base_y = HEIGHT - 135
    max_h = 46

    draw.line(
        [(start_x, base_y + 2), (start_x + total_w, base_y + 2)],
        fill=dim_color,
        width=2,
    )

    right_to_left_phase = f_idx * 0.20

    for i in range(line_count):
        norm_pos = (i / max(1, line_count - 1)) * 2.0 - 1.0  # -1 تا +1
        dist_center = abs(norm_pos)

        # وزن وکال در مرکز بیشتر و وزن ریتم در اطراف بیشتر است
        vocal_weight = max(0.25, 1.0 - 0.75 * dist_center)
        rhythm_weight = max(0.35, 0.45 + 0.55 * dist_center)
        blended_amp = vocal_amp * vocal_weight * 0.58 + rhythm_amp * rhythm_weight * 0.52
        blended_amp = min(1.0, blended_amp)

        shape_weight = max(0.35, 1.0 - 0.45 * dist_center)
        travel_wave = abs(math.sin(right_to_left_phase - i * 0.30)) ** 1.2
        h = max(4, int(max_h * blended_amp * shape_weight * travel_wave))

        x = start_x + i * (line_w + gap)
        if style == "dual_linear":
            mid_y = base_y - 20
            half_h = max(3, h // 2)
            draw.line([(x, mid_y - half_h), (x, mid_y + half_h)], fill=main_color, width=line_w)
        else:
            seg_h = 5
            seg_gap = 2
            cur_y = base_y
            drawn = 0
            while drawn < h and cur_y > base_y - max_h:
                step = min(seg_h, h - drawn)
                draw.line([(x, cur_y), (x, cur_y - step)], fill=main_color, width=line_w)
                cur_y -= step + seg_gap
                drawn += step + seg_gap

    return base_y + 4


def make_fixed_bottom_watermark(
    tg_logo: Image.Image,
    ig_logo: Image.Image,
    channel_avatar: Image.Image,
    font_wm,
    icon_size: int = 16,
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
    اکولایزر کوچک و حساس به ریتم و وکال را در پایین قرار می‌دهد و عکس کانال + واترمارک را
    در وسط و زیر اکولایزر با فاصله کم و کیفیت بالا ذخیره می‌کند.
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
    _log(f"شروع ساخت ریلز {duration:.1f} ثانیه‌ای با اکولایزر کوچکِ ریتم و وکال")

    rhythm_env, vocal_env = extract_rhythm_and_vocal_envelopes(audio_path, start_sec, duration, FPS)

    ensure_default_logos()
    icon_px = 16
    font_wm = load_wm_font(14)

    tg_logo = apply_opacity(Image.open(TG_LOGO_PATH).resize((icon_px, icon_px)), WM_ICON_OPACITY)
    ig_logo = apply_opacity(Image.open(IG_LOGO_PATH).resize((icon_px, icon_px)), WM_ICON_OPACITY)
    channel_avatar = build_channel_avatar(size=CHANNEL_AVATAR_SIZE, font_badge=load_wm_font(15))

    wm_block = make_fixed_bottom_watermark(
        tg_logo=tg_logo,
        ig_logo=ig_logo,
        channel_avatar=channel_avatar,
        font_wm=font_wm,
        icon_size=icon_px,
    )
    wm_w, wm_h = wm_block.size

    fixed_wm_x = (WIDTH - wm_w) // 2
    eq_bottom_y = HEIGHT - 131
    gap_below_eq = 8
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
            r_amp = rhythm_env[f_idx] if f_idx < len(rhythm_env) else 0.2
            v_amp = vocal_env[f_idx] if f_idx < len(vocal_env) else 0.2

            color_idx = (f_idx // max(1, FPS * 8)) % len(EQ_COLOR_PALETTE)
            eq_rgba = EQ_COLOR_PALETTE[color_idx]

            draw_compact_dual_equalizer(frame, f_idx, r_amp, v_amp, eq_rgba, style=EQ_STYLE)
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
        return True, f"ریلز {duration:.0f} ثانیه‌ای با اکولایزر کوچکِ ریتم و وکال آماده شد."

    except Exception as e:
        _log(f"استثنا در build_synced_reel: {e}")
        for p in (dec_proc, enc_proc):
            if p.poll() is None:
                p.kill()
        return False, f"خطا در ساخت ویدئو: {str(e)[:300]}"
