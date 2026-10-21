# 🎞️ AnythingToVideo

A powerful tool designed for lossless data storage inside raw video frames (MP4 container with `libx264rgb` / `libx264` codec, CRF 0). Features a self-describing header signature (`ATVD`), SHA-256 data integrity verification, configurable video parameters, and automatic multi-part archive splitting and merging.

---

## 🌟 Key Features

### 1. Default Parameters
- **Resolution**: `1920x1080` (1080p Full HD)
- **Frame Rate (FPS)**: `30 fps`
- **Color Mode**: `rgb24` (Full Color, 24-bit RGB)
- **x264 Preset**: `ultrafast`
- **Part Splitting**: `None` (Single video output)

### 2. Video Resolution Configuration
- **Predefined Profiles**:
  - `1920x1080` (1080p FHD - Default)
  - `1280x720` (720p HD)
  - `2560x1440` (1440p 2K QHD)
  - `3840x2160` (2160p 4K UHD)
  - `854x480` (480p SD)
  - `640x360` (360p)
- **Custom Resolution**: Any `Width x Height` (automatically sanitized to even numbers for H.264 compliance).

### 3. Frame Rate (FPS) Configuration
- **Profiles**: `30 fps` (Default), `60 fps` (Smooth), `24 fps` (Cinematic), `15 fps` (Compact), or any custom integer FPS.

### 4. Color Palettes
- **Full Color (24-bit RGB / 16.7M colors)**:
  - 3 bytes per pixel (`bgr24`).
  - Highest capacity (e.g., ~6.22 MB/frame at 1080p).
- **8 Colors (3-bit saturated RGB)**:
  - Black, Red, Green, Yellow, Blue, Magenta, Cyan, White.
  - 3 bits per pixel (e.g., ~777 KB/frame at 1080p).
- **Black & White (1-bit B&W / 2 colors)**:
  - 1 bit per pixel (`monob`).
  - Maximum resilience against re-encoding artifacts (e.g., ~259 KB/frame at 1080p).

### 5. Multi-part Splitting & Automatic Merging
- **Split on Encoding**: Set a maximum part size (e.g., `500 MB`, `1 GB`, `2 GB`, `4 GB`, or custom MB). Files exceeding this limit are saved as `.part1.mp4`, `.part2.mp4`, etc.
- **Smart Merging on Decoding**: Point the decoder to **any part** of the archive (e.g., `part1.mp4` or `part3.mp4`). The tool scans the directory, verifies all parts are present, merges them in sequence, and validates SHA-256 integrity.

---

## 🚀 Running the Graphical User Interface (GUI)

- **Double-click**: `launch_gui.bat`
- **From terminal**:
  ```powershell
  python anything_to_video_gui.py
  ```

---

## 💻 Command-Line Interface (CLI)

The core engine in `anything_to_video.py` is independent of GUI libraries (`tkinter` is not imported) and runs headlessly in terminal, Docker, or batch scripts:

```powershell
# 1. Encode with defaults (1920x1080, 30fps, Full Color 24-bit RGB):
python anything_to_video.py encode document.pdf

# 2. Encode with custom resolution, FPS, Black & White mode, and 1GB splitting:
python anything_to_video.py encode large_file.iso backup.mp4 --res 1280x720 --fps 60 --color bw --split 1GB

# 3. Encode with 8-color mode in 4K UHD:
python anything_to_video.py encode archive.tar video.mp4 --res 3840x2160 --color 8col

# 4. Inspect video metadata without decoding:
python anything_to_video.py info backup.mp4

# 5. Decode video and auto-merge multi-part sequences:
python anything_to_video.py decode backup.part1.mp4 C:\Recovered
```
