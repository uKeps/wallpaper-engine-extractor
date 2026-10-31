"""Core parser and extractor for Wallpaper Engine .pkg files."""

import json
import os
import re
import shutil
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from wallpaper_engine_extractor.tex_parser import extract_tex_file


@dataclass
class FileEntry:
    name: str
    offset: int
    length: int


@dataclass
class PackageInfo:
    root: str
    files: list[FileEntry]
    data_offset: int


def read_uint32(data: bytes) -> int:
    """Read a 32-bit unsigned little-endian integer from bytes."""
    return int.from_bytes(data, byteorder="little", signed=False)


def read_string(data: bytes) -> str:
    """Read a null-terminated UTF-8 string and strip padding."""
    return data.decode("utf-8", errors="replace").rstrip("\x00").strip()


PACKAGE_ERROR = "Not a Wallpaper Engine package, or the file is damaged"

# Files a wallpaper is made of that are not images; "images only" cleanup deletes these.
JUNK_EXTENSIONS = {
    ".json", ".lua", ".vs", ".fs", ".glsl", ".vert", ".frag",
    ".hlsl", ".fx", ".cfg", ".txt", ".xml",
}
MEDIA_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tga", ".mp4", ".webm"}

WINDOWS_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def read_pascal_string(file: BinaryIO, what: str) -> str:
    """Read a 4-byte length prefixed string from a binary file."""
    length_bytes = file.read(4)
    if len(length_bytes) < 4:
        raise ValueError(f"{PACKAGE_ERROR}: cannot read {what}")
    length = read_uint32(length_bytes)
    # Check against the bytes left so a corrupt length can't trigger a huge read
    remaining = os.fstat(file.fileno()).st_size - file.tell()
    if length > remaining:
        raise ValueError(f"{PACKAGE_ERROR}: {what} is longer than the file")
    return read_string(file.read(length))


def parse_package(pkg_path: Path) -> PackageInfo:
    """Parse the .pkg file header and file metadata table."""
    if not pkg_path.is_file():
        raise FileNotFoundError(f"Package file not found: {pkg_path}")
        
    with open(pkg_path, "rb") as f:
        root = read_pascal_string(f, "header")
        num_files_bytes = f.read(4)
        if len(num_files_bytes) < 4:
            raise ValueError(f"{PACKAGE_ERROR}: cannot read file count")
        num_files = read_uint32(num_files_bytes)
        
        files: list[FileEntry] = []
        for _ in range(num_files):
            name = read_pascal_string(f, "file name")
            offset_bytes = f.read(4)
            length_bytes = f.read(4)
            if len(offset_bytes) < 4 or len(length_bytes) < 4:
                raise ValueError(f"{PACKAGE_ERROR}: truncated file entry table")
                
            offset = read_uint32(offset_bytes)
            length = read_uint32(length_bytes)
            files.append(FileEntry(name=name, offset=offset, length=length))
            
        data_offset = f.tell()
        
    return PackageInfo(root=root, files=files, data_offset=data_offset)


def wallpaper_output_name(input_path: Path) -> str:
    """A filesystem-safe folder name for a wallpaper's output.

    Uses the title from project.json next to the input, else the workshop folder
    name (numeric id), else the input's stem.
    """
    input_path = Path(input_path)
    folder = input_path if input_path.is_dir() else input_path.parent
    name = ""
    try:
        project = json.loads((folder / "project.json").read_text(encoding="utf-8", errors="replace"))
        title = project.get("title") if isinstance(project, dict) else None
        name = title if isinstance(title, str) else ""
    except (OSError, ValueError):
        pass
    if not name.strip():
        name = folder.name if input_path.is_dir() or folder.name.isdigit() else input_path.stem

    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip()[:60].rstrip(". ")
    if name.split(".")[0].upper() in WINDOWS_RESERVED_NAMES:
        name += "_"
    return name or "wallpaper"


# Texture names that are almost never the wallpaper itself
NOT_BACKGROUND = re.compile(r"mask|particle|fx|effect|noise|flowmap|shadow|glow", re.IGNORECASE)
MIN_MAIN_IMAGE_AREA = 64 * 64


def _tex_size(tex_path: Path) -> tuple[int, int]:
    """Image width and height from a .tex header, (0, 0) if unreadable."""
    try:
        with open(tex_path, "rb") as f:
            head = f.read(42)
        # "TEXV0005\0TEXI0001\0", format, flags, texture w/h, image w/h
        tex_w, tex_h, img_w, img_h = struct.unpack_from("<4i", head, 26)
        return (img_w or tex_w, img_h or tex_h) if head.startswith(b"TEXV") else (0, 0)
    except (OSError, struct.error):
        return (0, 0)


def _value(v):
    """Unwrap a value bound to a user property: {"user": "name", "value": ...}."""
    return v.get("value") if isinstance(v, dict) else v


def _vec(v, n: int) -> list[float] | None:
    """First n numbers of a scene vector ("1.0 2.0 3.0", a list, or a single number)."""
    v = _value(v)
    try:
        if isinstance(v, (int, float)):
            return [float(v)] * n
        parts = [float(x) for x in (v.split() if isinstance(v, str) else v)]
    except (TypeError, ValueError):
        return None
    return parts[:n] if len(parts) >= n else None


def _scene_main_texture(root: Path, sizes: dict[Path, tuple[int, int]]) -> Path | None:
    """The .tex of the bottom-most scene.json image layer that covers the screen, else of the largest layer."""
    def load(rel) -> dict:
        data = json.loads((root / rel).read_text(encoding="utf-8-sig", errors="replace"))
        return data if isinstance(data, dict) else {}

    scene = load("scene.json")
    general = _value(scene.get("general"))
    projection = _value(general.get("orthogonalprojection")) if isinstance(general, dict) else None
    screen = _vec([_value(projection.get(k)) for k in ("width", "height")], 2) if isinstance(projection, dict) else None
    objects = _value(scene.get("objects"))
    best, best_area = None, 0.0
    for obj in objects if isinstance(objects, list) else []:
        # Objects are drawn in list order, so the first full-screen one is the bottom layer
        if not isinstance(obj, dict) or not isinstance(obj.get("image"), str) or _value(obj.get("visible")) is False:
            continue
        try:
            material = load(load(obj["image"])["material"])
            tex = (root / "materials" / f"{material['passes'][0]['textures'][0]}.tex").resolve()
        except (OSError, ValueError, LookupError, TypeError):
            continue  # e.g. a model from Wallpaper Engine's own assets, not in this package
        if tex not in sizes:
            continue
        size = _vec(obj.get("size"), 2)
        if not size or not all(size):
            size = sizes[tex]
        scale = _vec(obj.get("scale"), 2) or [1.0, 1.0]
        w, h = abs(size[0] * scale[0]), abs(size[1] * scale[1])
        if screen and all(screen) and w >= 0.9 * screen[0] and h >= 0.9 * screen[1]:
            return tex
        if w * h > best_area:
            best, best_area = tex, w * h
    return best


def find_main_image(root: Path, textures: dict[Path, list[Path]]) -> Path | None:
    """Pick "the wallpaper" among the images converted from a scene's textures.

    textures maps each converted .tex (still on disk) to the images made from it. Uses the
    layers in scene.json when it can, else the largest texture that isn't a mask, effect or tiny.
    """
    images = {tex: imgs[0] for tex, imgs in textures.items() if imgs and imgs[0].suffix.lower() not in {".mp4", ".webm"}}
    sizes = {tex: _tex_size(tex) for tex in images}
    try:
        tex = _scene_main_texture(root, sizes)
    except Exception:
        tex = None  # missing or malformed scene.json
    if tex is None:
        # ponytail: name/size heuristic, wrong when a character or effect layer is bigger than the background
        candidates = [t for t in images if sizes[t][0] * sizes[t][1] >= MIN_MAIN_IMAGE_AREA
                      and not NOT_BACKGROUND.search(t.relative_to(root).as_posix())]
        tex = max(candidates, key=lambda t: (sizes[t][0] * sizes[t][1], t.stat().st_size), default=None)
    return images.get(tex)


def extract_package(
    pkg_path: Path,
    output_dir: Path | None = None,
    extract_tex: bool = True,
    extract_all_mipmaps: bool = False,
    cleanup_non_images: bool = False,
    log_callback=None
) -> list[Path]:
    """Extract all files from a Wallpaper Engine .pkg package.
    
    Args:
        pkg_path: Path to the .pkg file.
        output_dir: Optional output directory. Defaults to a folder named after the package.
        extract_tex: If True, automatically convert .tex files to standard images.
        extract_all_mipmaps: If True, convert all mipmap sizes of .tex files.
        cleanup_non_images: If True, delete the non-image files this run extracted and keep only converted wallpapers.
        log_callback: Optional callable for logging progress (e.g. log_callback(message)).
        
    Returns:
        List of paths to the extracted/converted files.

    Raises:
        ValueError: If the package is damaged, or it has textures and none of them could be decoded.
    """
    pkg_path = Path(pkg_path)
    if output_dir is None:
        # Default to a folder next to the .pkg
        output_dir = pkg_path.parent / f"{pkg_path.stem}_extracted"
    else:
        output_dir = Path(output_dir)
        
    def log(msg: str):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)
            
    log(f"Reading package metadata for {pkg_path.name}...")
    info = parse_package(pkg_path)
    log(f"Found {len(info.files)} files inside package ({info.root})")

    # Only after a successful parse, so a damaged package leaves no empty folder behind
    output_dir.mkdir(parents=True, exist_ok=True)
    base_path = output_dir.resolve()
    
    extracted_paths: list[Path] = []
    created_dirs: set[Path] = set()
    tex_files_to_convert: list[Path] = []
    
    # 1. Extract raw files from the package
    with open(pkg_path, "rb") as pkg_file:
        for i, file_entry in enumerate(info.files):
            file_path = (base_path / file_entry.name).resolve()
            if not file_path.is_relative_to(base_path) or file_path == base_path:
                log(f"Skipping unsafe path in package: {file_entry.name}")
                continue
            for parent in file_path.parents:
                if parent == base_path or parent.exists():
                    break
                created_dirs.add(parent)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            log(f"[{i+1}/{len(info.files)}] Extracting: {file_entry.name}")
            pkg_file.seek(info.data_offset + file_entry.offset)
            data = pkg_file.read(file_entry.length)
            if len(data) < file_entry.length:
                raise ValueError(f"{PACKAGE_ERROR}: {file_entry.name} is cut off")
            
            with open(file_path, "wb") as f:
                f.write(data)
                
            extracted_paths.append(file_path)
            
            if file_path.suffix.lower() == ".tex":
                tex_files_to_convert.append(file_path)
                
    # 2. Convert .tex files to standard images if requested
    converted_image_paths: list[Path] = []
    converted_tex: dict[Path, list[Path]] = {}
    if extract_tex and tex_files_to_convert:
        log(f"Converting {len(tex_files_to_convert)} .tex file(s) to standard images...")
        for tex_path in tex_files_to_convert:
            try:
                log(f"Decoding texture: {tex_path.relative_to(base_path)}")
                imgs = extract_tex_file(tex_path, tex_path.parent, extract_all_mipmaps, log_callback=log)
                converted_image_paths.extend(imgs)
                converted_tex[tex_path] = imgs
            except Exception as e:
                log(f"Error converting texture {tex_path.name}: {e}")
                
    # Combine lists
    all_paths = list(dict.fromkeys(extracted_paths + converted_image_paths))

    # A copy of the main image at the top of the folder, picked before cleanup deletes scene.json.
    # Best effort: a wrong guess or a failure here must never fail the extraction.
    try:
        main_image = find_main_image(base_path, converted_tex)
        if main_image:
            main_copy = base_path / f"{wallpaper_output_name(pkg_path)}{main_image.suffix}"
            if main_copy not in all_paths:
                shutil.copyfile(main_image, main_copy)
                all_paths.append(main_copy)
                log(f"Main image: {main_copy.name}")
    except Exception as e:
        log(f"Couldn't pick the main image: {e}")
    
    # 3. Clean up non-image files if requested. Only files this run wrote are touched,
    # and a .tex is only removed once it was converted, so nothing is lost.
    if cleanup_non_images:
        log("Cleaning up non-image files...")
        converted = set(converted_tex)
        kept_paths: list[Path] = []
        for file_path in all_paths:
            if file_path.suffix.lower() in JUNK_EXTENSIONS or file_path in converted:
                try:
                    file_path.unlink()
                except OSError:
                    kept_paths.append(file_path)
            else:
                kept_paths.append(file_path)
                    
        # Remove the folders this run created that ended up empty, deepest first
        for directory in sorted(created_dirs, key=lambda d: len(d.parts), reverse=True):
            try:
                directory.rmdir()
            except OSError:
                pass
        all_paths = kept_paths

    log(f"Saved {len(all_paths)} file(s) to {output_dir}")
    failed = len(tex_files_to_convert) - len(converted_tex) if extract_tex else 0
    if failed:
        log(f"{failed} of {len(tex_files_to_convert)} texture(s) couldn't be converted")
        has_media = any(p.suffix.lower() in MEDIA_EXTENSIONS for p in all_paths)
        if not converted_tex and not has_media:
            raise ValueError("Couldn't decode any image in this wallpaper")
        
    return all_paths
