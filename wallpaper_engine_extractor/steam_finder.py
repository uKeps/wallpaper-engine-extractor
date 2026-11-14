"""Detects Wallpaper Engine wallpapers installed via Steam Workshop."""

import json
import os
import platform
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

WALLPAPER_ENGINE_APP_ID = "431960"


@dataclass
class WallpaperInfo:
    workshop_id: str
    title: str
    folder: Path
    pkg_path: Optional[Path]
    video_path: Optional[Path]
    preview_path: Optional[Path]
    wp_type: str

    @property
    def asset_path(self) -> Optional[Path]:
        """The extractable file for this wallpaper, regardless of its type."""
        return self.pkg_path or self.video_path


def _registry_steam_paths() -> list[Path]:
    """Read Steam's install location from the Windows registry, if available."""
    paths = []
    try:
        import winreg
    except ImportError:
        return paths

    for hive, subkey in (
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
    ):
        try:
            with winreg.OpenKey(hive, subkey) as key:
                for value_name in ("SteamPath", "InstallPath"):
                    try:
                        value, _ = winreg.QueryValueEx(key, value_name)
                        if value:
                            paths.append(Path(value))
                    except FileNotFoundError:
                        continue
        except FileNotFoundError:
            continue
    return paths


def _default_steam_paths() -> list[Path]:
    """Fall back to the conventional Steam install locations per platform."""
    system = platform.system()
    home = Path.home()
    if system == "Windows":
        return [Path("C:/Program Files (x86)/Steam"), Path("C:/Program Files/Steam")]
    if system == "Darwin":
        return [home / "Library/Application Support/Steam"]
    data_home = Path(os.environ.get("XDG_DATA_HOME") or home / ".local/share")
    return [
        home / ".steam/steam",  # usually a symlink to the next one; callers dedupe by resolved path
        data_home / "Steam",
        home / ".var/app/com.valvesoftware.Steam/data/Steam",  # Flatpak
        home / "snap/steam/common/.local/share/Steam",  # Snap
    ]


def find_steam_install_paths() -> list[Path]:
    """Find likely Steam installation directories, deduplicated (symlinks resolved)."""
    found = []
    for path in _registry_steam_paths() + _default_steam_paths():
        try:
            path = path.resolve()
            if path.is_dir() and path not in found:
                found.append(path)
        except OSError:
            continue
    return found


def _parse_library_folders(steam_path: Path) -> list[Path]:
    """Parse steamapps/libraryfolders.vdf to find every Steam library location."""
    libraries = [steam_path]
    vdf_path = steam_path / "steamapps" / "libraryfolders.vdf"
    if not vdf_path.is_file():
        return libraries
    try:
        text = vdf_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return libraries
    for match in re.finditer(r'"path"\s*"([^"]+)"', text):
        lib_path = Path(match.group(1).replace("\\\\", "\\"))
        try:
            if lib_path.is_dir() and lib_path not in libraries:
                libraries.append(lib_path)
        except OSError:
            continue
    return libraries


def find_workshop_content_dirs() -> list[Path]:
    """Find every steamapps/workshop/content/431960 folder across all Steam libraries."""
    content_dirs = []
    for steam_path in find_steam_install_paths():
        for library in _parse_library_folders(steam_path):
            try:
                content_dir = (library / "steamapps" / "workshop" / "content" / WALLPAPER_ENGINE_APP_ID).resolve()
                if content_dir.is_dir() and content_dir not in content_dirs:
                    content_dirs.append(content_dir)
            except OSError:
                continue
    return content_dirs


def _safe_child(folder: Path, raw_name: object) -> Optional[Path]:
    """Resolve a relative path inside `folder` safely, falling back to case-insensitive lookup."""
    if not isinstance(raw_name, str) or not raw_name.strip():
        return None
    rel = raw_name.strip().replace("\\", "/")
    if rel.startswith("/") or Path(rel).is_absolute() or Path(rel).drive or re.match(r"^[A-Za-z]:", rel):
        return None
    try:
        folder_real = folder.resolve()
        exact = folder / rel
        if exact.is_file() and exact.resolve().is_relative_to(folder_real):
            return exact
        cur = folder
        for part in Path(rel).parts:
            if part in ("", ".", ".."):
                return None
            cur = next((p for p in cur.iterdir() if p.name.casefold() == part.casefold()), None)
            if cur is None:
                return None
        return cur if cur.is_file() and cur.resolve().is_relative_to(folder_real) else None
    except OSError:
        return None


def _first_by_ext(folder: Path, exts: tuple[str, ...]) -> Optional[Path]:
    """First regular file in `folder` matching one of `exts` (case-insensitive, deterministic order)."""
    try:
        entries = sorted(folder.iterdir(), key=lambda p: p.name.casefold())
    except OSError:
        return None
    for entry in entries:
        if entry.is_file() and entry.suffix.lower() in exts:
            return entry
    return None


def _find_preview(folder: Path, project: dict) -> Optional[Path]:
    candidate = _safe_child(folder, project.get("preview"))
    if candidate:
        return candidate
    for ext in ("jpg", "jpeg", "png", "gif"):
        candidate = _safe_child(folder, f"preview.{ext}")
        if candidate:
            return candidate
    return None


def _find_pkg(folder: Path, project: dict) -> Optional[Path]:
    candidate = _safe_child(folder, project.get("file"))
    if candidate and candidate.suffix.lower() == ".pkg":
        return candidate
    return _safe_child(folder, "scene.pkg") or _first_by_ext(folder, (".pkg",))


def _find_video(folder: Path, project: dict) -> Optional[Path]:
    candidate = _safe_child(folder, project.get("file"))
    if candidate and candidate.suffix.lower() in (".mp4", ".webm"):
        return candidate
    return _first_by_ext(folder, (".mp4", ".webm"))


def wallpaper_from_folder(folder: Path) -> Optional[WallpaperInfo]:
    """Describe one wallpaper folder (a workshop item), or None if it isn't a folder."""
    folder = Path(folder)
    if not folder.is_dir():
        return None

    project = {}
    project_path = folder / "project.json"
    if project_path.is_file():
        try:
            project = json.loads(project_path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            project = {}
    if not isinstance(project, dict):
        project = {}

    raw_title = project.get("title")
    title = raw_title.strip() if isinstance(raw_title, str) and raw_title.strip() else folder.name
    raw_type = project.get("type")
    wp_type = raw_type.strip().lower() if isinstance(raw_type, str) and raw_type.strip() else "unknown"

    return WallpaperInfo(
        workshop_id=folder.name,
        title=title,
        folder=folder,
        pkg_path=_find_pkg(folder, project),
        video_path=_find_video(folder, project),
        preview_path=_find_preview(folder, project),
        wp_type=wp_type,
    )


def find_installed_wallpapers() -> list[WallpaperInfo]:
    """Scan every detected Steam workshop library for Wallpaper Engine wallpapers."""
    wallpapers = []
    for content_dir in find_workshop_content_dirs():
        try:
            folders = sorted(content_dir.iterdir())
        except OSError:
            continue
        for folder in folders:
            wallpaper = wallpaper_from_folder(folder)
            if wallpaper:
                wallpapers.append(wallpaper)
    return wallpapers
