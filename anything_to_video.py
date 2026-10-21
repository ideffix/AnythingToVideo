import os
import sys
import re
import struct
import hashlib
import shutil
import subprocess
import argparse

# Magic signature
MAGIC_HEADER = b"ATVD"  # Signature for AnythingToVideo (configurable resolution, fps, color mode, multipart)

# Color modes
COLOR_RGB24 = "rgb24"  # Full Color (24-bit RGB, 3 bytes per pixel)
COLOR_8COL = "8col"    # 8 Saturated Colors (3 bits per pixel)
COLOR_BW = "bw"        # Black & White (1 bit per pixel)

COLOR_MODE_MAP = {
    1: COLOR_RGB24,
    2: COLOR_8COL,
    3: COLOR_BW
}
COLOR_MODE_REV_MAP = {v: k for k, v in COLOR_MODE_MAP.items()}

# Default values
DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080
DEFAULT_FPS = 30
DEFAULT_COLOR_MODE = COLOR_RGB24
DEFAULT_PRESET = "ultrafast"

# Palette for 8-color mode (BGR order)
PALETTE_8COL = [
    bytes([(c & 1) * 255, ((c >> 1) & 1) * 255, ((c >> 2) & 1) * 255])
    for c in range(8)
]


def find_ffmpeg():
    """Locate ffmpeg executable in system PATH or common installation directories."""
    p = shutil.which("ffmpeg")
    if p:
        return p
    candidates = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
        os.path.expanduser(r"~\MiniConda3\Library\bin\ffmpeg.exe"),
        os.path.expanduser(r"~\Anaconda3\Library\bin\ffmpeg.exe"),
        r"C:\Program Files (x86)\YouTube Playlist Downloader\ffmpeg.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return "ffmpeg"


def parse_size_str(s):
    """
    Parse a human-readable size string (e.g. '1GB', '500MB', '2.5 GB', '1024') into bytes.
    Returns None if unlimited, empty or invalid.
    """
    if not s:
        return None
    s_clean = str(s).strip().lower()
    if s_clean in ("none", "unlimited", "0", "brak", ""):
        return None
    m = re.match(r"^([\d.]+)\s*(gb|g|mb|m|kb|k|b)?$", s_clean)
    if not m:
        return None
    val = float(m.group(1))
    unit = m.group(2) or "mb"
    if unit in ("gb", "g"):
        return int(val * 1024 * 1024 * 1024)
    elif unit in ("mb", "m"):
        return int(val * 1024 * 1024)
    elif unit in ("kb", "k"):
        return int(val * 1024)
    return int(val)


def format_size(bytes_val):
    """Format bytes into human-readable string (B, KB, MB, GB)."""
    if bytes_val is None:
        return "None"
    if bytes_val >= 1024**3:
        return f"{bytes_val / (1024**3):.2f} GB"
    elif bytes_val >= 1024**2:
        return f"{bytes_val / (1024**2):.2f} MB"
    elif bytes_val >= 1024:
        return f"{bytes_val / 1024:.2f} KB"
    return f"{bytes_val} B"


def parse_resolution_str(res_str):
    """
    Parse a resolution string (e.g. '1920x1080', '1280x720') into a (width, height) tuple.
    Ensures dimensions are even numbers (required by H.264 video encoders).
    """
    if not res_str:
        return DEFAULT_WIDTH, DEFAULT_HEIGHT
    m = re.match(r"^(\d+)\s*[xX*:,]\s*(\d+)$", str(res_str).strip())
    if not m:
        raise ValueError(f"Invalid resolution format: '{res_str}'. Expected format like '1920x1080'.")
    w, h = int(m.group(1)), int(m.group(2))
    if w % 2 != 0: w += 1
    if h % 2 != 0: h += 1
    return w, h


def get_frame_specs(width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT, color_mode=DEFAULT_COLOR_MODE):
    """
    Calculate frame parameters based on resolution and color mode:
    - payload_bytes: user payload bytes per video frame
    - raw_bytes: raw stream bytes transferred to/from ffmpeg
    - pix_fmt: pixel format for rawvideo pipe
    - vcodec: video codec (libx264 or libx264rgb)
    """
    total_pixels = width * height
    # Ensure total pixels is a multiple of 8 for bit-level modes
    if total_pixels % 8 != 0:
        total_pixels = (total_pixels // 8) * 8

    if color_mode == COLOR_BW:
        payload_bytes = total_pixels // 8
        raw_bytes = payload_bytes
        pix_fmt = "monob"
        vcodec = "libx264"
    elif color_mode == COLOR_8COL:
        payload_bytes = (total_pixels // 8) * 3
        raw_bytes = total_pixels * 3
        pix_fmt = "bgr24"
        vcodec = "libx264rgb"
    else:  # COLOR_RGB24
        payload_bytes = total_pixels * 3
        raw_bytes = total_pixels * 3
        pix_fmt = "bgr24"
        vcodec = "libx264rgb"

    return {
        "width": width,
        "height": height,
        "total_pixels": total_pixels,
        "color_mode": color_mode,
        "payload_bytes": payload_bytes,
        "raw_bytes": raw_bytes,
        "pix_fmt": pix_fmt,
        "vcodec": vcodec
    }


def encode_8col_frame(data_chunk, total_pixels):
    """
    Encode data chunk into 8 saturated RGB colors (BGR byte buffer).
    Maps 3 bytes (24 bits) into 8 pixels of 3 bits each.
    """
    expected_data_len = (total_pixels // 8) * 3
    if len(data_chunk) < expected_data_len:
        data_chunk = data_chunk + b"\x00" * (expected_data_len - len(data_chunk))

    out = bytearray(total_pixels * 3)
    out_idx = 0
    p = PALETTE_8COL

    for i in range(0, expected_data_len, 3):
        val = (data_chunk[i] << 16) | (data_chunk[i+1] << 8) | data_chunk[i+2]
        out[out_idx:out_idx+24] = (
            p[(val >> 21) & 7] + p[(val >> 18) & 7] +
            p[(val >> 15) & 7] + p[(val >> 12) & 7] +
            p[(val >> 9) & 7] + p[(val >> 6) & 7] +
            p[(val >> 3) & 7] + p[val & 7]
        )
        out_idx += 24

    return bytes(out)


def decode_8col_frame(bgr_bytes, expected_data_len):
    """
    Decode 8-color BGR pixel buffer back into binary data.
    Maps 8 pixels (24 bytes BGR) back into 3 payload bytes.
    """
    out = bytearray((len(bgr_bytes) // 24) * 3)
    out_idx = 0

    for i in range(0, len(bgr_bytes), 24):
        val = 0
        for p_idx in range(8):
            base = i + p_idx * 3
            bits = (1 if bgr_bytes[base] > 127 else 0) | \
                   (2 if bgr_bytes[base+1] > 127 else 0) | \
                   (4 if bgr_bytes[base+2] > 127 else 0)
            val = (val << 3) | bits
        out[out_idx] = (val >> 16) & 255
        out[out_idx+1] = (val >> 8) & 255
        out[out_idx+2] = val & 255
        out_idx += 3

    return bytes(out[:expected_data_len])


def probe_video_format(video_path, ffmpeg_path=None):
    """
    Probe video container with ffmpeg to extract:
    - resolution (width, height)
    - fps
    - color_mode (from metadata comment or stream properties)
    """
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Video file '{video_path}' does not exist.")

    ffmpeg_bin = ffmpeg_path or find_ffmpeg()
    cmd = [ffmpeg_bin, "-i", video_path]
    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True)
    _, err = proc.communicate()

    # 1. Parse container 'comment' metadata tag
    m_comment = re.search(r"comment\s*:\s*ATVD:([^\r\n]+)", err, re.IGNORECASE)
    comment_info = {}
    if m_comment:
        parts = m_comment.group(1).split(":")
        for part in parts:
            if "=" in part:
                k, v = part.split("=", 1)
                comment_info[k.strip().lower()] = v.strip().lower()

    # 2. Parse resolution and FPS from video stream output
    w, h, fps = DEFAULT_WIDTH, DEFAULT_HEIGHT, DEFAULT_FPS
    m_res = re.search(r"Stream.*Video:.*?(\d{2,5})x(\d{2,5})", err)
    if m_res:
        w, h = int(m_res.group(1)), int(m_res.group(2))

    m_fps = re.search(r"(\d+(?:\.\d+)?)\s*fps", err)
    if m_fps:
        fps = int(round(float(m_fps.group(1))))

    color_mode = comment_info.get("mode", DEFAULT_COLOR_MODE)
    if "w" in comment_info:
        try: w = int(comment_info["w"])
        except ValueError: pass
    if "h" in comment_info:
        try: h = int(comment_info["h"])
        except ValueError: pass
    if "fps" in comment_info:
        try: fps = int(comment_info["fps"])
        except ValueError: pass

    # Fallback heuristic if metadata tag was stripped
    if "mode" not in comment_info:
        if "yuv420p" in err and "monob" in err:
            color_mode = COLOR_BW
        else:
            color_mode = COLOR_RGB24

    return {
        "width": w,
        "height": h,
        "fps": fps,
        "color_mode": color_mode
    }


def peek_header(video_path, ffmpeg_path=None):
    """
    Inspect the video file, probe format, read the first frame, and return metadata dictionary.
    """
    format_info = probe_video_format(video_path, ffmpeg_path)
    width = format_info["width"]
    height = format_info["height"]
    fps = format_info["fps"]
    color_mode = format_info["color_mode"]

    specs = get_frame_specs(width, height, color_mode)
    raw_frame_size = specs["raw_bytes"]
    payload_frame_size = specs["payload_bytes"]
    pix_fmt = specs["pix_fmt"]

    ffmpeg_bin = ffmpeg_path or find_ffmpeg()
    cmd = [
        ffmpeg_bin,
        "-i", video_path,
        "-f", "rawvideo",
        "-pix_fmt", pix_fmt,
        "-v", "quiet",
        "-"
    ]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        raw_first_frame = proc.stdout.read(raw_frame_size)
    finally:
        proc.stdout.close()
        proc.kill()

    if len(raw_first_frame) < raw_frame_size:
        raise ValueError("Video file is corrupt or too short (no complete first frame).")

    if color_mode == COLOR_8COL:
        first_frame = decode_8col_frame(raw_first_frame, payload_frame_size)
    else:
        first_frame = raw_first_frame

    magic = first_frame[:4]
    if magic != MAGIC_HEADER:
        raise ValueError("No valid AnythingToVideo (ATVD) header found in the first video frame.")

    offset = 4
    part_num, total_parts = struct.unpack(">HH", first_frame[offset:offset + 4])
    offset += 4
    part_payload_size, total_file_size, part_offset = struct.unpack(">QQQ", first_frame[offset:offset + 24])
    offset += 24
    file_sha256 = first_frame[offset:offset + 32]
    offset += 32
    part_sha256 = first_frame[offset:offset + 32]
    offset += 32

    h_width, h_height, h_fps, color_mode_id = struct.unpack(">HHHB", first_frame[offset:offset + 7])
    offset += 7
    actual_color_mode = COLOR_MODE_MAP.get(color_mode_id, color_mode)

    fn_len, = struct.unpack(">H", first_frame[offset:offset + 2])
    offset += 2
    filename = first_frame[offset:offset + fn_len].decode("utf-8", errors="ignore")
    offset += fn_len

    return {
        "part_num": part_num,
        "total_parts": total_parts,
        "part_payload_size": part_payload_size,
        "total_file_size": total_file_size,
        "part_offset": part_offset,
        "sha256": file_sha256.hex(),
        "sha256_bytes": file_sha256,
        "part_sha256": part_sha256.hex(),
        "part_sha256_bytes": part_sha256,
        "filename": filename,
        "width": h_width or width,
        "height": h_height or height,
        "fps": h_fps or fps,
        "color_mode": actual_color_mode,
        "header_len": offset
    }


def find_related_parts(sample_video_path, ffmpeg_path=None):
    """
    Given any part of a multi-part archive, find all related parts in the same directory.
    """
    meta = peek_header(sample_video_path, ffmpeg_path)
    total_parts = meta["total_parts"]
    sample_part_num = meta["part_num"]

    found_parts = {sample_part_num: os.path.abspath(sample_video_path)}
    if total_parts <= 1:
        return {
            "is_complete": True,
            "total_parts": 1,
            "parts": found_parts,
            "missing": [],
            "meta": meta
        }

    dir_path = os.path.dirname(os.path.abspath(sample_video_path))
    expected_sha256 = meta["sha256"]
    sample_basename = os.path.basename(sample_video_path)

    # 1. Direct regex substitution matching part numbers
    part_patterns = [
        (rf"(?i)(\.part)({sample_part_num})(\.mp4)$", r"\g<1>{num}\g<3>"),
        (rf"(?i)(_part)({sample_part_num})(\.mp4)$", r"\g<1>{num}\g<3>"),
        (rf"(?i)(\.part)({sample_part_num:02d})(\.mp4)$", r"\g<1>{num:02d}\g<3>"),
        (rf"(?i)(_part)({sample_part_num:02d})(\.mp4)$", r"\g<1>{num:02d}\g<3>"),
    ]

    for p in range(1, total_parts + 1):
        if p in found_parts:
            continue
        for pat, repl in part_patterns:
            candidate_name = re.sub(pat, lambda m: repl.format(num=p), sample_basename)
            candidate_path = os.path.join(dir_path, candidate_name)
            if os.path.isfile(candidate_path):
                try:
                    c_meta = peek_header(candidate_path, ffmpeg_path)
                    if (c_meta["sha256"] == expected_sha256 and
                            c_meta["total_parts"] == total_parts and
                            c_meta["part_num"] == p):
                        found_parts[p] = candidate_path
                        break
                except Exception:
                    pass

    # 2. Directory scan for all video files with matching checksum and total parts
    if len(found_parts) < total_parts and os.path.isdir(dir_path):
        for fname in os.listdir(dir_path):
            if not fname.lower().endswith((".mp4", ".mkv", ".avi")):
                continue
            fpath = os.path.join(dir_path, fname)
            if fpath in found_parts.values():
                continue
            try:
                c_meta = peek_header(fpath, ffmpeg_path)
                if (c_meta["sha256"] == expected_sha256 and
                        c_meta["total_parts"] == total_parts):
                    p_num = c_meta["part_num"]
                    if p_num not in found_parts:
                        found_parts[p_num] = fpath
            except Exception:
                continue

    missing = [p for p in range(1, total_parts + 1) if p not in found_parts]
    return {
        "is_complete": len(missing) == 0,
        "total_parts": total_parts,
        "parts": found_parts,
        "missing": missing,
        "meta": meta
    }


def encode_file(input_path, output_mp4="video.mp4", max_part_size=None,
                width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT, fps=DEFAULT_FPS,
                color_mode=DEFAULT_COLOR_MODE, preset=DEFAULT_PRESET,
                progress_callback=None, log_callback=None, cancel_event=None,
                ffmpeg_path=None):
    """
    Encode any file into a lossless MP4 video with:
    - configurable resolution (width, height)
    - configurable frame rate (fps)
    - configurable color palette (rgb24, 8col, bw)
    - automatic splitting if max_part_size is exceeded
    """
    def log(msg):
        if log_callback: log_callback(msg)
        else: print(msg)

    if not os.path.isfile(input_path):
        msg = f"[!] Error: File '{input_path}' not found."
        log(msg)
        return False, msg

    # Validate resolution and options
    width = int(width) if width else DEFAULT_WIDTH
    height = int(height) if height else DEFAULT_HEIGHT
    if width % 2 != 0: width += 1
    if height % 2 != 0: height += 1
    fps = int(fps) if fps and int(fps) > 0 else DEFAULT_FPS
    if color_mode not in (COLOR_RGB24, COLOR_8COL, COLOR_BW):
        color_mode = DEFAULT_COLOR_MODE

    specs = get_frame_specs(width, height, color_mode)
    payload_frame_size = specs["payload_bytes"]
    pix_fmt = specs["pix_fmt"]
    vcodec = specs["vcodec"]

    ffmpeg_bin = ffmpeg_path or find_ffmpeg()
    total_size = os.path.getsize(input_path)
    filename_bytes = os.path.basename(input_path).encode("utf-8")

    if isinstance(max_part_size, str):
        max_part_size = parse_size_str(max_part_size)

    if max_part_size and max_part_size > 0 and total_size > max_part_size:
        total_parts = (total_size + max_part_size - 1) // max_part_size
    else:
        total_parts = 1
        max_part_size = total_size

    mode_names = {
        COLOR_RGB24: "Full Color (24-bit RGB)",
        COLOR_8COL: "8 Primary Colors (3-bit RGB)",
        COLOR_BW: "Black & White (1-bit B&W)"
    }

    log(f"[*] Input file: {os.path.basename(input_path)} ({format_size(total_size)})")
    log(f"[*] Video specs: {width}x{height} @ {fps} fps | Mode: {mode_names[color_mode]}")
    log(f"[*] Frame capacity: {format_size(payload_frame_size)} ({payload_frame_size:,} bytes/frame)")
    if total_parts > 1:
        log(f"[*] Multi-part enabled: {total_parts} parts (max {format_size(max_part_size)} each).")
    else:
        log("[*] Single video output (no splitting).")

    # 1. Compute SHA-256 for entire file and individual parts
    log("[*] Computing SHA-256 checksums...")
    if progress_callback:
        progress_callback(0, 100, "Computing SHA-256 checksums...")

    full_hasher = hashlib.sha256()
    part_hashers = [hashlib.sha256() for _ in range(total_parts)]

    hashed_bytes = 0
    with open(input_path, "rb") as f:
        for p in range(total_parts):
            p_offset = p * max_part_size
            p_size = min(max_part_size, total_size - p_offset)
            remaining_part = p_size

            while remaining_part > 0:
                if cancel_event and cancel_event.is_set():
                    log("[!] Cancelled by user.")
                    return False, "Cancelled by user."

                chunk_to_read = min(16 * 1024 * 1024, remaining_part)
                chunk = f.read(chunk_to_read)
                if not chunk:
                    break
                full_hasher.update(chunk)
                part_hashers[p].update(chunk)
                remaining_part -= len(chunk)
                hashed_bytes += len(chunk)

                if progress_callback and total_size > 0:
                    pct = (hashed_bytes / total_size) * 100
                    progress_callback(pct, 100, f"Hashing SHA-256 ({pct:.1f}%)...")

    full_sha256 = full_hasher.digest()
    log(f"[*] Full SHA-256: {full_sha256.hex()}")

    # 2. Output filenames
    base_out, ext_out = os.path.splitext(output_mp4)
    ext_out = ext_out if ext_out else ".mp4"

    part_files = []
    if total_parts == 1:
        part_files.append(output_mp4)
    else:
        for p in range(1, total_parts + 1):
            part_files.append(f"{base_out}.part{p}{ext_out}")

    # Prepare part headers and frame counts
    part_specs = []
    total_frames_all = 0
    color_mode_id = COLOR_MODE_REV_MAP.get(color_mode, 1)

    for p_idx in range(total_parts):
        part_num = p_idx + 1
        part_offset = p_idx * max_part_size
        part_payload_size = min(max_part_size, total_size - part_offset)
        part_sha256 = part_hashers[p_idx].digest()

        header = (
            MAGIC_HEADER
            + struct.pack(">HH", part_num, total_parts)
            + struct.pack(">QQQ", part_payload_size, total_size, part_offset)
            + full_sha256
            + part_sha256
            + struct.pack(">HHHB", width, height, fps, color_mode_id)
            + struct.pack(">H", len(filename_bytes))
            + filename_bytes
        )

        payload_with_header = len(header) + part_payload_size
        part_frames = (payload_with_header + payload_frame_size - 1) // payload_frame_size
        total_frames_all += part_frames

        part_specs.append({
            "part_num": part_num,
            "part_file": part_files[p_idx],
            "part_offset": part_offset,
            "part_payload_size": part_payload_size,
            "header": header,
            "part_frames": part_frames
        })

    log(f"[*] Total frames to encode: {total_frames_all:,} across {total_parts} part(s).")

    # 3. Stream frames into ffmpeg
    frames_written_global = 0

    with open(input_path, "rb") as in_f:
        for spec in part_specs:
            part_num = spec["part_num"]
            out_file = spec["part_file"]
            header = spec["header"]
            part_payload_size = spec["part_payload_size"]
            part_frames = spec["part_frames"]

            log(f"[*] Starting part {part_num}/{total_parts}: {out_file} ({part_frames} frames)...")

            ffmpeg_cmd = [
                ffmpeg_bin, "-y",
                "-f", "rawvideo",
                "-vcodec", "rawvideo",
                "-s", f"{width}x{height}",
                "-pix_fmt", pix_fmt,
                "-r", str(fps),
                "-i", "-",
                "-metadata", f"comment=ATVD:mode={color_mode}:w={width}:h={height}:fps={fps}",
                "-c:v", vcodec,
                "-crf", "0",
                "-preset", preset,
                out_file
            ]

            try:
                proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
            except Exception as e:
                msg = f"[!] Failed to launch ffmpeg ({ffmpeg_bin}): {e}"
                log(msg)
                return False, msg

            buffer = bytearray(header)
            part_bytes_read = 0
            in_f.seek(spec["part_offset"])

            try:
                while True:
                    if cancel_event and cancel_event.is_set():
                        proc.kill()
                        if os.path.exists(out_file):
                            try: os.remove(out_file)
                            except OSError: pass
                        log("[!] Encoding cancelled by user.")
                        return False, "Encoding cancelled."

                    while len(buffer) < payload_frame_size and part_bytes_read < part_payload_size:
                        to_read = min(payload_frame_size, part_payload_size - part_bytes_read)
                        chunk = in_f.read(to_read)
                        if not chunk:
                            break
                        buffer.extend(chunk)
                        part_bytes_read += len(chunk)

                    if not buffer:
                        break

                    if len(buffer) >= payload_frame_size:
                        raw_payload = buffer[:payload_frame_size]
                        del buffer[:payload_frame_size]
                    else:
                        raw_payload = buffer + b"\x00" * (payload_frame_size - len(buffer))
                        buffer = bytearray()

                    if color_mode == COLOR_8COL:
                        frame_bytes_to_send = encode_8col_frame(raw_payload, specs["total_pixels"])
                    else:
                        frame_bytes_to_send = raw_payload

                    proc.stdin.write(frame_bytes_to_send)

                    frames_written_global += 1
                    if frames_written_global % 15 == 0 or frames_written_global == total_frames_all:
                        pct = (float(frames_written_global) / total_frames_all) * 100
                        status = f"Part {part_num}/{total_parts} | Frames: {frames_written_global}/{total_frames_all} ({pct:.1f}%)"
                        if progress_callback:
                            progress_callback(pct, 100, status)
                        else:
                            sys.stdout.write(f"\r{status}")
                            sys.stdout.flush()

                proc.stdin.close()
                proc.wait()
            except Exception as e:
                proc.kill()
                msg = f"[!] Error while encoding part {part_num}: {e}"
                log(msg)
                return False, msg

            log(f"[+] Completed part {part_num}/{total_parts}: {out_file}")

    if total_parts == 1:
        success_msg = f"Success! Created video: {part_files[0]}"
    else:
        success_msg = f"Success! Created {total_parts} video parts:\n" + "\n".join(part_files)

    log(f"\n[+] {success_msg}")
    if progress_callback:
        progress_callback(100, 100, "Encoding completed successfully!")
    return True, success_msg


def decode_file(video_path, output_dir=".",
                progress_callback=None, log_callback=None, cancel_event=None,
                ffmpeg_path=None):
    """
    Decode hidden file from video, automatically detecting resolution, fps,
    color mode and multi-part sequences, and verifying SHA-256 integrity.
    """
    def log(msg):
        if log_callback: log_callback(msg)
        else: print(msg)

    if not os.path.isfile(video_path):
        msg = f"[!] Error: Video file '{video_path}' not found."
        log(msg)
        return False, msg

    ffmpeg_bin = ffmpeg_path or find_ffmpeg()

    try:
        parts_info = find_related_parts(video_path, ffmpeg_bin)
    except Exception as e:
        msg = f"[!] Error reading video header: {e}"
        log(msg)
        return False, msg

    meta = parts_info["meta"]
    total_parts = parts_info["total_parts"]
    filename = meta["filename"]
    total_file_size = meta["total_file_size"]
    expected_full_sha256 = meta["sha256"]
    width = meta["width"]
    height = meta["height"]
    fps = meta["fps"]
    color_mode = meta["color_mode"]

    specs = get_frame_specs(width, height, color_mode)
    raw_frame_size = specs["raw_bytes"]
    payload_frame_size = specs["payload_bytes"]
    pix_fmt = specs["pix_fmt"]

    if not parts_info["is_complete"]:
        missing_str = ", ".join(str(p) for p in parts_info["missing"])
        msg = (f"[!] Error: Incomplete multi-part archive ({len(parts_info['parts'])}/{total_parts} parts found).\n"
               f"    Missing parts: {missing_str}.\n"
               f"    Ensure all part files are located in the same directory.")
        log(msg)
        return False, msg

    ordered_part_files = [parts_info["parts"][p] for p in range(1, total_parts + 1)]

    log(f"[*] Detected file: {filename} ({format_size(total_file_size)})")
    log(f"[*] Video specs: {width}x{height} @ {fps} fps | Mode: {color_mode}")
    if total_parts > 1:
        log(f"[*] Multi-part archive: {total_parts} parts.")
        for p_num, p_path in enumerate(ordered_part_files, 1):
            log(f"    Part {p_num}: {os.path.basename(p_path)}")
    log(f"[*] Expected SHA-256: {expected_full_sha256}")

    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    target_path = os.path.join(output_dir, filename)
    temp_target_path = target_path + ".restoring"

    full_hasher = hashlib.sha256()
    total_written_bytes = 0

    try:
        with open(temp_target_path, "wb") as out_f:
            for p_idx, part_file in enumerate(ordered_part_files):
                part_num = p_idx + 1
                log(f"[*] Opening part {part_num}/{total_parts}: {os.path.basename(part_file)}...")

                ffmpeg_cmd = [
                    ffmpeg_bin,
                    "-i", part_file,
                    "-f", "rawvideo",
                    "-pix_fmt", pix_fmt,
                    "-v", "quiet",
                    "-"
                ]

                proc = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                try:
                    raw_first_frame = proc.stdout.read(raw_frame_size)
                    if len(raw_first_frame) < raw_frame_size:
                        proc.kill()
                        raise ValueError(f"Video file '{part_file}' is corrupt or empty.")

                    if color_mode == COLOR_8COL:
                        first_frame = decode_8col_frame(raw_first_frame, payload_frame_size)
                    else:
                        first_frame = raw_first_frame

                    magic = first_frame[:4]
                    if magic != MAGIC_HEADER:
                        proc.kill()
                        raise ValueError(f"Invalid AnythingToVideo header signature in '{part_file}'.")

                    offset = 4 + 4
                    p_payload_size, _, _ = struct.unpack(">QQQ", first_frame[offset:offset+24])
                    offset += 24 + 32
                    expected_part_sha = first_frame[offset:offset+32].hex()
                    offset += 32 + 7  # 7 bytes: width, height, fps, color_mode_id
                    fn_len, = struct.unpack(">H", first_frame[offset:offset+2])
                    offset += 2 + fn_len

                    part_hasher = hashlib.sha256()
                    part_written = 0

                    first_avail = min(len(first_frame) - offset, p_payload_size)
                    if first_avail > 0:
                        first_data = first_frame[offset:offset + first_avail]
                        out_f.write(first_data)
                        full_hasher.update(first_data)
                        part_hasher.update(first_data)
                        part_written += len(first_data)
                        total_written_bytes += len(first_data)

                    while part_written < p_payload_size:
                        if cancel_event and cancel_event.is_set():
                            proc.stdout.close()
                            proc.kill()
                            raise KeyboardInterrupt("Cancelled by user.")

                        raw_chunk = proc.stdout.read(raw_frame_size)
                        if not raw_chunk:
                            break

                        if color_mode == COLOR_8COL:
                            chunk_data = decode_8col_frame(raw_chunk, payload_frame_size)
                        else:
                            chunk_data = raw_chunk

                        to_write_len = min(len(chunk_data), p_payload_size - part_written)
                        valid_data = chunk_data[:to_write_len]

                        out_f.write(valid_data)
                        full_hasher.update(valid_data)
                        part_hasher.update(valid_data)
                        part_written += len(valid_data)
                        total_written_bytes += len(valid_data)

                        if total_written_bytes % (16 * 1024 * 1024) == 0 or total_written_bytes == total_file_size:
                            pct = (float(total_written_bytes) / total_file_size) * 100
                            status = (f"Part {part_num}/{total_parts} | Total: {format_size(total_written_bytes)} / "
                                      f"{format_size(total_file_size)} ({pct:.1f}%)")
                            if progress_callback:
                                progress_callback(pct, 100, status)
                            else:
                                sys.stdout.write(f"\r{status}")
                                sys.stdout.flush()

                    proc.stdout.close()
                    proc.wait()

                    if part_hasher.hexdigest() != expected_part_sha:
                        raise ValueError(f"Part {part_num} SHA-256 mismatch! Part file is damaged.")

                except Exception:
                    proc.kill()
                    raise

        # Verify full restored file SHA-256
        actual_full_sha = full_hasher.hexdigest()
        if actual_full_sha != expected_full_sha256:
            if os.path.exists(temp_target_path):
                os.remove(temp_target_path)
            msg = (f"[!] CRITICAL ERROR: SHA-256 checksum mismatch!\n"
                   f"    Expected: {expected_full_sha256}\n"
                   f"    Actual:   {actual_full_sha}")
            log(msg)
            return False, msg

        if os.path.exists(target_path):
            os.remove(target_path)
        os.rename(temp_target_path, target_path)

    except KeyboardInterrupt:
        if os.path.exists(temp_target_path):
            try: os.remove(temp_target_path)
            except OSError: pass
        log("[!] Decoding aborted.")
        return False, "Decoding cancelled by user."
    except Exception as e:
        if os.path.exists(temp_target_path):
            try: os.remove(temp_target_path)
            except OSError: pass
        msg = f"[!] Error during decoding: {e}"
        log(msg)
        return False, msg

    log("")
    success_msg = f"[+] SUCCESS! File recovered and verified: {target_path}"
    if total_parts > 1:
        success_msg += f" (merged from {total_parts} parts)."
    log(success_msg)

    if progress_callback:
        progress_callback(100, 100, "File restored and verified successfully!")
    return True, success_msg


# ==========================================
# COMMAND-LINE INTERFACE (CLI)
# ==========================================
def main():
    parser = argparse.ArgumentParser(
        description="AnythingToVideo - Store and recover any file inside lossless MP4 video frames.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""CLI Examples:
  # Encode file with defaults (1920x1080, 30fps, RGB 24-bit):
  python anything_to_video.py encode document.pdf

  # Encode with custom resolution, FPS, Black & White mode and 500MB splitting:
  python anything_to_video.py encode file.iso backup.mp4 --res 1280x720 --fps 60 --color bw --split 500MB

  # Encode with 8-color mode in 4K UHD:
  python anything_to_video.py encode archive.tar video.mp4 --res 3840x2160 --color 8col

  # Inspect video metadata without decoding:
  python anything_to_video.py info backup.mp4

  # Decode and auto-merge parts:
  python anything_to_video.py decode backup.part1.mp4 C:\\Recovered
"""
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Command: encode
    p_enc = subparsers.add_parser("encode", help="Encode a file into MP4 video")
    p_enc.add_argument("input", help="Path to input file to encode")
    p_enc.add_argument("output", nargs="?", default="video.mp4", help="Path to output MP4 video (default: video.mp4)")
    p_enc.add_argument("--res", default=f"{DEFAULT_WIDTH}x{DEFAULT_HEIGHT}",
                       help=f"Video resolution WxH (default: {DEFAULT_WIDTH}x{DEFAULT_HEIGHT})")
    p_enc.add_argument("--fps", type=int, default=DEFAULT_FPS,
                       help=f"Frames per second (default: {DEFAULT_FPS})")
    p_enc.add_argument("--color", choices=["rgb24", "8col", "bw"], default=DEFAULT_COLOR_MODE,
                       help="Color mode: 'rgb24' (Full Color), '8col' (8 Colors), 'bw' (Black & White)")
    p_enc.add_argument("--split", "-s", default=None,
                       help="Maximum part size (e.g. 500MB, 1GB, 2GB; default: no splitting)")
    p_enc.add_argument("--preset", "-p", default=DEFAULT_PRESET,
                       help=f"x264 encoder preset (default: {DEFAULT_PRESET})")

    # Command: decode
    p_dec = subparsers.add_parser("decode", help="Decode file from video and auto-merge parts")
    p_dec.add_argument("video", help="Path to video file (or any part of an archive)")
    p_dec.add_argument("dest", nargs="?", default=".", help="Destination directory (default: current directory)")

    # Command: info
    p_info = subparsers.add_parser("info", help="Inspect video metadata without decoding")
    p_info.add_argument("video", help="Path to video file")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "encode":
        w, h = parse_resolution_str(args.res)
        encode_file(
            input_path=args.input,
            output_mp4=args.output,
            max_part_size=args.split,
            width=w,
            height=h,
            fps=args.fps,
            color_mode=args.color,
            preset=args.preset
        )
    elif args.command == "decode":
        decode_file(video_path=args.video, output_dir=args.dest)
    elif args.command == "info":
        try:
            meta = peek_header(args.video)
            print("=== AnythingToVideo Metadata ===")
            print(f"Original file:  {meta['filename']}")
            print(f"Total size:     {format_size(meta['total_file_size'])} ({meta['total_file_size']:,} bytes)")
            print(f"SHA-256 hash:   {meta['sha256']}")
            print(f"Resolution:     {meta['width']}x{meta['height']}")
            print(f"FPS:            {meta['fps']}")
            print(f"Color mode:     {meta['color_mode']}")
            print(f"Part:           {meta['part_num']} of {meta['total_parts']}")
            if meta['total_parts'] > 1:
                parts_info = find_related_parts(args.video)
                status_str = "Complete (all parts found in folder)" if parts_info['is_complete'] else "Incomplete"
                print(f"Part status:    {status_str}")
                if parts_info['missing']:
                    print(f"Missing parts:  {parts_info['missing']}")
        except Exception as e:
            print(f"[!] Error reading metadata: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
