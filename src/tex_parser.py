"""Parser and extractor for Wallpaper Engine .tex files."""

import struct
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# Try to import Pillow for advanced image conversions (optional)
try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPG_SIGNATURE = b"\xFF\xD8\xFF"
BMP_SIGNATURE = b"BM"


class TextureFormat(Enum):
    PNG = "png"
    JPG = "jpg"
    BMP = "bmp"
    RAW = "raw"


def detect_format(data: bytes) -> tuple[TextureFormat, bytes]:
    """Detect the image format of the raw texture bytes."""
    if data[:8] == PNG_SIGNATURE:
        return TextureFormat.PNG, data
    if data[:3] == JPG_SIGNATURE:
        return TextureFormat.JPG, data
    if data[:2] == BMP_SIGNATURE:
        return TextureFormat.BMP, data
    return TextureFormat.RAW, data


def decompress_rle(data: bytes, expected_size: int) -> bytes:
    """Decompress Wallpaper Engine custom RLE compressed BGRA data."""
    result = bytearray()
    i = 0
    
    while i < len(data) and len(result) < expected_size:
        count = data[i]
        i += 1
        
        if count & 0x80:
            # RLE run
            count = (count & 0x7F) + 1
            if i < len(data):
                value = data[i]
                i += 1
                result.extend([value] * count)
        else:
            # Literal run
            count += 1
            if i + count <= len(data):
                result.extend(data[i:i+count])
                i += count
            else:
                result.extend(data[i:])
                i = len(data)
                
    return bytes(result[:expected_size])


def create_bmp(width: int, height: int, bgra_data: bytes) -> bytes:
    """Construct a 32-bit BMP file in memory from raw BGRA pixel data (no external libraries)."""
    bpp = 32
    row_size = ((width * bpp + 31) // 32) * 4
    image_size = row_size * height
    file_size = 54 + image_size
    
    bmp = bytearray()
    
    # BMP Header
    bmp.extend(b"BM")                      # Signature
    bmp.extend(struct.pack("<I", file_size))# File Size
    bmp.extend(struct.pack("<H", 0))        # Reserved 1
    bmp.extend(struct.pack("<H", 0))        # Reserved 2
    bmp.extend(struct.pack("<I", 54))       # Pixel Data Offset
    
    # DIB Header (BITMAPINFOHEADER)
    bmp.extend(struct.pack("<I", 40))       # Header Size
    bmp.extend(struct.pack("<i", width))    # Width
    bmp.extend(struct.pack("<i", -height))   # Height (negative for top-down)
    bmp.extend(struct.pack("<H", 1))        # Color Planes
    bmp.extend(struct.pack("<H", bpp))      # Bits per Pixel (32 for BGRA)
    bmp.extend(struct.pack("<I", 0))        # Compression Method (0 = BI_RGB)
    bmp.extend(struct.pack("<I", image_size))# Image Size
    bmp.extend(struct.pack("<i", 0))        # Horizontal Resolution
    bmp.extend(struct.pack("<i", 0))        # Vertical Resolution
    bmp.extend(struct.pack("<I", 0))        # Colors in palette
    bmp.extend(struct.pack("<I", 0))        # Important colors
    
    # Normalize pixel data size
    if len(bgra_data) < image_size:
        bgra_data = bgra_data + b"\x00" * (image_size - len(bgra_data))
    else:
        bgra_data = bgra_data[:image_size]
        
    bmp.extend(bgra_data)
    return bytes(bmp)


@dataclass
class TextureData:
    width: int
    height: int
    data_size: int
    data: bytes
    format: TextureFormat


@dataclass
class TexInfo:
    version: str
    texture_count: int
    width: int
    height: int
    textures: list[TextureData]


def read_cstring(data: bytes, offset: int, max_len: int = 4) -> str:
    """Read a null-terminated ASCII string from bytes at a given offset."""
    end = offset
    for i in range(max_len):
        if offset + i >= len(data) or data[offset + i] == 0:
            end = offset + i
            break
    else:
        end = offset + max_len
    return data[offset:end].decode("ascii", errors="replace")


def parse_tex(tex_path: Path) -> TexInfo:
    """Parse a .tex file header and extract texture blocks metadata.
    
    Uses a dynamic scanning strategy instead of hardcoded offsets,
    making it compatible with all known Wallpaper Engine TEX versions.
    """
    if not tex_path.is_file():
        raise FileNotFoundError(f"TEX file not found: {tex_path}")
    
    with open(tex_path, "rb") as f:
        data = f.read()
        
    if len(data) < 64:
        raise ValueError("File is too small to be a valid Wallpaper Engine .tex file")
        
    if data[0:4] != b"TEXV":
        raise ValueError(f"Invalid TEXV magic header: {data[0:4]!r}")
        
    version = read_cstring(data, 4, 8)  # read up to 8 chars for version string
    
    texb_pos = data.find(b"TEXB")
    if texb_pos == -1:
        raise ValueError("TEXB data marker not found")
    
    # --- Read base dimensions from TEXI section ---
    # Width and height are always near offset 0x22 and 0x26 in the TEXI block
    width = struct.unpack("<I", data[0x22:0x26])[0]
    height = struct.unpack("<I", data[0x26:0x2A])[0]
    
    # --- Dynamic mipmap discovery ---
    # Instead of relying on a mipmap count field (which changes between versions),
    # we scan for the first mipmap by searching for the (width, height) bytes
    # immediately following the TEXB marker, then walk each subsequent mipmap.
    textures: list[TextureData] = []
    
    if width == 0 or height == 0:
        # Fallback: no valid dimensions, cannot discover mipmaps
        return TexInfo(version=version, texture_count=0, width=0, height=0, textures=[])
    
    # Search for the first mipmap header = (width_bytes + height_bytes) pattern
    width_bytes = struct.pack("<I", width)
    height_bytes = struct.pack("<I", height)
    target = width_bytes + height_bytes
    
    pos = data.find(target, texb_pos)
    if pos == -1:
        # Couldn't find exact match — try with half-size (some wallpapers store first mipmap smaller)
        return TexInfo(version=version, texture_count=0, width=width, height=height, textures=[])
    
    # Walk through mipmaps starting from discovered position
    mip_width = width
    mip_height = height
    
    while pos + 20 <= len(data) and mip_width >= 1 and mip_height >= 1:
        cur_width = struct.unpack("<I", data[pos:pos+4])[0]
        cur_height = struct.unpack("<I", data[pos+4:pos+8])[0]
        
        # Validate: must match expected dimensions
        if cur_width != mip_width or cur_height != mip_height:
            break
        
        data_size = struct.unpack("<I", data[pos+16:pos+20])[0]
        
        if data_size == 0 or pos + 20 + data_size > len(data):
            break
        
        tex_data = data[pos+20 : pos+20+data_size]
        tex_format, _ = detect_format(tex_data)
        
        textures.append(
            TextureData(
                width=cur_width,
                height=cur_height,
                data_size=data_size,
                data=tex_data,
                format=tex_format,
            )
        )
        
        pos += data_size + 20
        # Each mipmap is half the size
        mip_width = max(1, mip_width // 2)
        mip_height = max(1, mip_height // 2)
        
    return TexInfo(
        version=version,
        texture_count=len(textures),
        width=width,
        height=height,
        textures=textures,
    )


def extract_tex_file(tex_path: Path, output_dir: Path | None = None, extract_all_mipmaps: bool = False) -> list[Path]:
    """Extract textures from a Wallpaper Engine .tex file to standard image formats.
    
    Args:
        tex_path: Path to the .tex file.
        output_dir: Optional output directory. Defaults to the same directory as the .tex file.
        extract_all_mipmaps: If True, extract all mipmap sizes. Otherwise, only extract the largest (original) resolution.
        
    Returns:
        List of paths to the extracted image files.
    """
    tex_path = Path(tex_path)
    if output_dir is None:
        output_dir = tex_path.parent
    else:
        output_dir = Path(output_dir)
        
    output_dir.mkdir(parents=True, exist_ok=True)
    
    info = parse_tex(tex_path)
    extracted_paths: list[Path] = []
    base_name = tex_path.stem
    
    # We loop through textures. Mipmap 0 is always the largest.
    for i, texture in enumerate(info.textures):
        if i > 0 and not extract_all_mipmaps:
            break  # Skip smaller mipmaps unless requested
            
        # Determine output format and final bytes
        if texture.format in (TextureFormat.PNG, TextureFormat.JPG):
            # Already standard compressed formats
            ext = texture.format.value
            out_bytes = texture.data
        else:
            # RAW format (RLE-compressed BGRA data)
            expected_pixels = texture.width * texture.height
            expected_bytes = expected_pixels * 4
            
            try:
                decompressed = decompress_rle(texture.data, expected_bytes)
                
                if HAS_PILLOW:
                    # Save as PNG using Pillow to preserve transparency correctly and save space
                    ext = "png"
                    img = Image.frombytes("RGBA", (texture.width, texture.height), decompressed, "raw", "BGRA")
                    output_path = output_dir / f"{base_name}_{texture.width}x{texture.height}.{ext}"
                    img.save(output_path, "PNG")
                    extracted_paths.append(output_path)
                    continue
                else:
                    # Fallback: Save as a standard 32-bit BMP
                    ext = "bmp"
                    out_bytes = create_bmp(texture.width, texture.height, decompressed)
            except Exception as e:
                # If decompression fails, write raw file as a fallback
                ext = "raw"
                out_bytes = texture.data
                print(f"Warning: Failed to decompress RAW RLE texture in {tex_path.name}: {e}")
                
        suffix = f"_{texture.width}x{texture.height}" if extract_all_mipmaps else ""
        output_path = output_dir / f"{base_name}{suffix}.{ext}"
        
        with open(output_path, "wb") as f:
            f.write(out_bytes)
            
        extracted_paths.append(output_path)
        
    return extracted_paths
