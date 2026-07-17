"""Handles Wallpaper Engine video wallpapers (.mp4/.webm).

Unlike scene wallpapers, video wallpapers store the finished video file directly
with no .pkg container to parse, so "extracting" one just means copying it out
of the Steam Workshop folder into the chosen output location.
"""

import shutil
from pathlib import Path

SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".webm"}


def extract_video_file(video_path: Path, output_dir: Path | None = None, log_callback=None) -> Path:
    """Copy a Wallpaper Engine video wallpaper into the output directory.

    Args:
        video_path: Path to the .mp4 or .webm file.
        output_dir: Optional output directory. Defaults to the same directory as the video.
        log_callback: Optional callable for logging progress (e.g. log_callback(message)).

    Returns:
        Path to the copied video file.
    """
    video_path = Path(video_path)
    if not video_path.is_file():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    if video_path.suffix.lower() not in SUPPORTED_VIDEO_EXTENSIONS:
        raise ValueError(f"Unsupported video format: {video_path.suffix}")

    output_dir = video_path.parent if output_dir is None else Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    def log(msg: str):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    destination = output_dir / video_path.name
    if destination.resolve() == video_path.resolve():
        log(f"Video wallpaper already in output location: {video_path.name}")
    else:
        log(f"Copying video wallpaper: {video_path.name}...")
        shutil.copy2(video_path, destination)

    return destination
