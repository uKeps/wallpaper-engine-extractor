"""Core parser and extractor for Wallpaper Engine .pkg files."""

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from src.tex_parser import extract_tex_file


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


def read_pascal_string(file: BinaryIO) -> str:
    """Read a 4-byte length prefixed string from a binary file."""
    length_bytes = file.read(4)
    if len(length_bytes) < 4:
        return ""
    length = read_uint32(length_bytes)
    return read_string(file.read(length))


def parse_package(pkg_path: Path) -> PackageInfo:
    """Parse the .pkg file header and file metadata table."""
    if not pkg_path.is_file():
        raise FileNotFoundError(f"Package file not found: {pkg_path}")
        
    with open(pkg_path, "rb") as f:
        root = read_pascal_string(f)
        num_files_bytes = f.read(4)
        if len(num_files_bytes) < 4:
            raise ValueError("Malformed .pkg file: cannot read file count")
        num_files = read_uint32(num_files_bytes)
        
        files: list[FileEntry] = []
        for _ in range(num_files):
            name = read_pascal_string(f)
            offset_bytes = f.read(4)
            length_bytes = f.read(4)
            if len(offset_bytes) < 4 or len(length_bytes) < 4:
                raise ValueError("Malformed .pkg file: truncated file entry table")
                
            offset = read_uint32(offset_bytes)
            length = read_uint32(length_bytes)
            files.append(FileEntry(name=name, offset=offset, length=length))
            
        data_offset = f.tell()
        
    return PackageInfo(root=root, files=files, data_offset=data_offset)


def clean_empty_directories(directory: Path) -> None:
    """Recursively delete empty subdirectories."""
    for root, dirs, files in os.walk(directory, topdown=False):
        for name in dirs:
            dir_path = Path(root) / name
            try:
                if not os.listdir(dir_path):
                    dir_path.rmdir()
            except OSError:
                pass


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
        cleanup_non_images: If True, delete non-image files and keep only converted wallpapers.
        log_callback: Optional callable for logging progress (e.g. log_callback(message)).
        
    Returns:
        List of paths to the extracted/converted files.
    """
    pkg_path = Path(pkg_path)
    if output_dir is None:
        # Default to a folder next to the .pkg
        output_dir = pkg_path.parent / f"{pkg_path.stem}_extracted"
    else:
        output_dir = Path(output_dir)
        
    output_dir.mkdir(parents=True, exist_ok=True)
    
    def log(msg: str):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)
            
    log(f"Reading package metadata for {pkg_path.name}...")
    info = parse_package(pkg_path)
    log(f"Found {len(info.files)} files inside package root: '{info.root}'")
    
    base_path = output_dir / info.root
    base_path.mkdir(parents=True, exist_ok=True)
    
    extracted_paths: list[Path] = []
    tex_files_to_convert: list[Path] = []
    
    # 1. Extract raw files from the package
    with open(pkg_path, "rb") as pkg_file:
        for i, file_entry in enumerate(info.files):
            file_path = base_path / file_entry.name
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            log(f"[{i+1}/{len(info.files)}] Extracting: {file_entry.name}")
            pkg_file.seek(info.data_offset + file_entry.offset)
            data = pkg_file.read(file_entry.length)
            
            with open(file_path, "wb") as f:
                f.write(data)
                
            extracted_paths.append(file_path)
            
            if file_path.suffix.lower() == ".tex":
                tex_files_to_convert.append(file_path)
                
    # 2. Convert .tex files to standard images if requested
    converted_image_paths: list[Path] = []
    if extract_tex and tex_files_to_convert:
        log(f"Converting {len(tex_files_to_convert)} .tex file(s) to standard images...")
        for tex_path in tex_files_to_convert:
            try:
                log(f"Decoding texture: {tex_path.relative_to(base_path)}")
                imgs = extract_tex_file(tex_path, tex_path.parent, extract_all_mipmaps)
                converted_image_paths.extend(imgs)
            except Exception as e:
                log(f"Error converting texture {tex_path.name}: {e}")
                
    # Combine lists
    all_paths = extracted_paths + converted_image_paths
    
    # 3. Clean up non-image files if requested
    if cleanup_non_images:
        log("Cleaning up non-image files...")
        # DELETE these known shader/script/config extensions
        # Everything else (including .raw, .bmp, .png, .jpg) is KEPT
        junk_extensions = {
            ".json", ".lua", ".vs", ".fs", ".glsl", ".vert", ".frag",
            ".hlsl", ".glsl", ".fx", ".cfg", ".txt", ".xml", ".tex"
        }
        kept_paths: list[Path] = []
        
        # Scan every file in the output tree
        for root, _, files in os.walk(base_path):
            for filename in files:
                file_path = Path(root) / filename
                if file_path.suffix.lower() in junk_extensions:
                    try:
                        file_path.unlink()
                    except OSError:
                        pass
                else:
                    kept_paths.append(file_path)
                    
        # Remove empty folders
        clean_empty_directories(output_dir)
        all_paths = kept_paths
        log(f"Cleanup complete. Kept {len(all_paths)} file(s).")
        
    return all_paths
