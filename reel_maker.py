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
TG_LOGO_PATH = os.path.join(BASE_DIR, "tg_logo.png")
IG_LOGO_PATH = os.path.join(BASE_DIR, "ig_logo.png")

MAX_DURATION = 60
WIDTH = 720
HEIGHT = 1280
FPS = 20
WM_ALPHA = 102  # حدود ۴۰ درصد شفافیت (0.4 * 255)

# ترکیب رنگ‌های بولد و پرانرژی برای متن وسط فیلم
COLOR_PALETTE = [
    (255, 255, 255, 250),  # سفید درخشان
    (255, 214, 10, 250),   # زرد طلایی
    (120, 220, 255, 250),  # آبی یخی
    (255, 120, 180, 250),  # صورتی نئونی
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
    rgba = img.convert("RGBA")
    r, g, b, a = rgba.split()
    a = a.point(lambda p: int(p * alpha_factor))
    return Image.merge("RGBA", (r, g, b, a))


def load_bold_font(size: int):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
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


def extract_beat_envelope(
    audio_path: str, start_sec: float, duration: float, fps: int
) -> list[float]:
    """انرژی هر فریم از موزیک را استخراج می‌کند تا متن‌ها با ریتم/ضرباهنگ سینک شوند."""
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
    for i in range(total_frames):
        chunk = samples[i * samples_per_frame : (i + 1) * samples_per_frame]
        if not chunk:
            energies.append(0.1)
            continue
        rms = math.sqrt(sum(s * s for s in chunk) / len(chunk)) / 32768.0
        val = min(1.0, (rms * 4.5) ** 0.72)
        energies.append(max(0.08, val))

    return energies


def build_rhythmic_cues(
    lyrics_text: str, duration: float, fps: int, energies: list[float]
) -> list[tuple[int, int, str]]:
    """
    متن تاییدشده را به کلمات/عبارات تقسیم کرده و بر اساس ریتم/انرژی موزیک به بازه فریم‌ها نگاشت می‌کند.
    """
    clean = lyrics_text.strip()
    if not clean:
        return []

    chunks = [part.strip() for part in re.split(r"\n+|\s*\|\s*", clean) if part.strip()]
    tokens: list[str] = []
    for ch in chunks:
        words = [w.strip() for w in ch.split() if w.strip()]
        if len(words) <= 2:
            tokens.append(ch)
        else:
            tokens.extend(words)

    if not tokens:
        return []

    total_frames = max(1, int(duration * fps))
    base_weights = [max(1.0, len(re.sub(r"\s+", "", t)) * 0.6) for t in tokens]
    total_w = sum(base_weights)

    cues: list[tuple[int, int, str]] = []
    frame_cursor = 0
    for idx, (tok, w) in enumerate(zip(tokens, base_weights)):
        span = max(1, int(round(total_frames * (w / total_w))))
        start_f = min(frame_cursor, total_frames - 1)
        if idx == len(tokens) - 1:
            end_f = total_frames - 1
        else:
            end_f = min(total_frames - 1, max(start_f, start_f + span - 1))

        peak_window = energies[max(0, start_f - 2) : min(total_frames, start_f + 3)]
        if peak_window and max(peak_window) > 0.65 and start_f > 0:
            start_f = max(0, start_f - 1)

        cues.append((start_f, end_f, tok))
        frame_cursor = end_f + 1

    return cues


def make_fixed_bottom_watermark(tg_logo: Image.Image, ig_logo: Image.Image, font_wm) -> Image.Image:
    """واترمارک کوچک، ۴۰٪ شفاف و زیر هم بدون فاصله برای قرارگیری ثابت در پایین صفحه."""
    block_w = 240
    block_h = 44  # دو ردیف ۲۲ پیکسلی زیر هم بدون فاصله
    block = Image.new("RGBA", (block_w, block_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(block)

    icon_size = 20
    row_step = 22  # بدون فاصله عمودی بین دو خط

    # خط اول: آیکون + t.me/remixiyu
    block.paste(tg_logo, (0, 1), tg_logo)
    draw.text((icon_size + 5, 2), TG_TEXT, font=font_wm, fill=(255, 255, 255, WM_ALPHA))

    # خط دوم: آیکون + remixiyu دقیقاً زیر خط اول بدون فاصله
    block.paste(ig_logo, (0, row_step + 1), ig_logo)
    draw.text((icon_size + 5, row_step + 2), IG_TEXT, font=font_wm, fill=(255, 255, 255, WM_ALPHA))

    return block


def draw_centered_bold_text(
    frame: Image.Image,
    text: str,
    font_bold,
    emoji_font,
    color_rgba: tuple[int, int, int, int],
    pulse_scale: float = 1.0,
):
    """متن بولد، رنگی و دارای ایموجی را دقیقاً در وسط ویدئو رسم می‌کند."""
    draw = ImageDraw.Draw(frame)
    bbox = draw.textbbox((0, 0), text, font=font_bold)
    tw = max(1, bbox[2] - bbox[0])
    th = max(1, bbox[3] - bbox[1])

    pad_x = 24
    pad_y = 16
    box_w = tw + pad_x * 2
    box_h = th + pad_y * 2

    txt_canvas = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    tdraw = ImageDraw.Draw(txt_canvas)

    tdraw.rounded_rectangle(
        (2, 2, box_w - 2, box_h - 2),
        radius=16,
        fill=(0, 0, 0, 135),
    )

    tx = pad_x
    ty = pad_y
    for ox, oy in ((-2, 0), (2, 0), (0, -2), (0, 2), (2, 2)):
        tdraw.text((tx + ox, ty + oy), text, font=font_bold, fill=(0, 0, 0, 220))

    tdraw.text((tx, ty), text, font=font_bold, fill=color_rgba)

    if emoji_font is not None:
        emoji_chars = "".join(ch for ch in text if ord(ch) > 0x1F300)
        if emoji_chars:
            try:
                ebbox = tdraw.textbbox((0, 0), emoji_chars, font=emoji_font)
                ew = max(1, ebbox[2] - ebbox[0])
                eh = max(1, ebbox[3] - ebbox[1])
                tdraw.text(
                    (box_w - ew - 10, max(2, (box_h - eh) // 2)),
                    emoji_chars,
                    font=emoji_font,
                    embedded_color=True,
                )
            except Exception:
                pass

    scaled_w = max(1, int(box_w * pulse_scale))
    scaled_h = max(1, int(box_h * pulse_scale))
    if (scaled_w, scaled_h) != (box_w, box_h):
        txt_canvas = txt_canvas.resize((scaled_w, scaled_h), Image.Resampling.BILINEAR)

    paste_x = max(10, (WIDTH - scaled_w) // 2)
    paste_y = max(10, (HEIGHT - scaled_h) // 2)
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
    صدای اصلی ویدئوی پس‌زمینه را قطع می‌کند، ویدئو را دقیقاً هم‌اندازه تایم موزیک کات می‌زند،
    متن ریتماتیک را در وسط می‌گذارد و واترماک ثابت کوچک، ۴۰٪ شفاف و زیر هم بدون فاصله را
    در پایین صفحه قرار می‌دهد.
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
    _log(f"شروع ساخت ریلز به مدت {duration:.1f} ثانیه ({start_sec}s تا {start_sec + duration}s)")

    energies = extract_beat_envelope(audio_path, start_sec, duration, FPS)
    cues = build_rhythmic_cues(lyrics_text, duration, FPS, energies)
    _log(f"تعداد بازه‌های ریتمیک متن: {len(cues)}")

    ensure_default_logos()
    opacity = WM_ALPHA / 255.0
    font_wm = load_bold_font(18)
    font_center = load_bold_font(42)
    emoji_font = load_emoji_font(42)

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

            if active_text:
                color_rgba = COLOR_PALETTE[cue_index % len(COLOR_PALETTE)]
                pulse_scale = 1.0 + min(0.12, amp * 0.12)
                draw_centered_bold_text(
                    frame=frame,
                    text=active_text,
                    font_bold=font_center,
                    emoji_font=emoji_font,
                    color_rgba=color_rgba,
                    pulse_scale=pulse_scale,
                )

            # واترماک ثابت در پایین صفحه (بدون حرکت، ۴۰٪ شفاف، زیر هم بدون فاصله)
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
        return True, f"ریلز {duration:.0f} ثانیه‌ای با کات دقیق ویدئو، حذف صدای قبلی، سینک ریتماتیک و واترماک ثابت پایین آماده شد."

    except Exception as e:
        _log(f"استثنا در build_synced_reel: {e}")
        for p in (dec_proc, enc_proc):
            if p.poll() is None:
                p.kill()
        return False, f"خطا در ساخت ویدئو: {str(e)[:300]}"
