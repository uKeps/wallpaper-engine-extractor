"""Parser and extractor for Wallpaper Engine .tex files.

The layout follows RePKG (github.com/notscuffed/repkg), which is the reference
implementation: RePKG.Application/Texture/Tex*Reader.cs.

    "TEXV0005\\0" "TEXI0001\\0"
    TEXI: format, flags, textureWidth, textureHeight, imageWidth, imageHeight, unk (7 x int32)
    TEXB: "TEXB000N\\0", imageCount, [v3+: freeImageFormat], [v4: isVideoMp4]
          per image: mipmapCount, then per mipmap:
            v1:    width, height, byteCount, bytes
            v2/v3: width, height, isLZ4, decompressedSize, byteCount, bytes
            v4:    1, 2, conditionJson\\0, 1, then the v2/v3 fields (only for MP4 textures)
    TEXS (only when flags has IsGif): "TEXS000N\\0", frameCount, [v3: gifWidth, gifHeight], frames
"""

import io
import math
import struct
from dataclasses import dataclass, field
from pathlib import Path

# Try to import Pillow for advanced image conversions (optional)
try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

# TexFormat (RePKG.Core/Texture/Enums/TexFormat.cs)
RGBA8888, DXT5, DXT3, DXT1, RG88, R8 = 0, 4, 6, 7, 8, 9
TEX_FORMATS = {RGBA8888: "RGBA8888", DXT5: "DXT5", DXT3: "DXT3", DXT1: "DXT1", RG88: "RG88", R8: "R8"}

# TexFlags (RePKG.Core/Texture/Enums/TexFlags.cs)
FLAG_IS_GIF = 4
FLAG_IS_VIDEO = 32

# FreeImageFormat (RePKG.Core/Texture/Enums/FreeImageFormat.cs); -1 means raw pixels in the TEXI format.
# Extensions indexed by format id, as in RePKG's MipmapFormatExtensions.GetFileExtension.
FIF_UNKNOWN, FIF_MP4 = -1, 35
FIF_EXTENSIONS = (
    "bmp ico jpg jng koa lbm mng pbm pbm pcd pcx pgm pgm png ppm ppm ras tga tif wbmp "
    "psd cut xbm xpm dds gif hdr g3 sgi exr j2k jp2 pfm pict raw mp4"
).split()
IMAGE_SIGNATURES = ((b"\x89PNG\r\n\x1a\n", "png"), (b"\xFF\xD8\xFF", "jpg"), (b"GIF8", "gif"), (b"BM", "bmp"))

# Safety limits, same values as RePKG.Application/Constants.cs
MAX_IMAGES = 100
MAX_MIPMAPS = 32
MAX_FRAMES = 100_000
MAX_MIPMAP_BYTES = 250_000_000


@dataclass
class Mipmap:
    width: int
    height: int
    data: bytes  # LZ4 already undone; still in the texture's pixel format


@dataclass
class Frame:
    image_id: int
    frametime: float
    x: float
    y: float
    width: float
    width_y: float
    height_x: float
    height: float


@dataclass
class TexInfo:
    container: str  # "TEXB0001".."TEXB0004"
    format: int
    flags: int
    texture_width: int
    texture_height: int
    image_width: int
    image_height: int
    image_format: int
    images: list[list[Mipmap]]
    frames: list[Frame] = field(default_factory=list)
    gif_width: int = 0
    gif_height: int = 0

    @property
    def is_gif(self) -> bool:
        return bool(self.flags & FLAG_IS_GIF)

    @property
    def is_video(self) -> bool:
        return bool(self.flags & FLAG_IS_VIDEO) or self.image_format == FIF_MP4


class _Reader:
    """Bounds-checked little-endian cursor; every overrun is a ValueError."""

    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def take(self, size: int, what: str) -> bytes:
        if size < 0 or self.pos + size > len(self.data):
            raise ValueError(
                f"Truncated or corrupt .tex file: {what} needs {size} bytes at offset {self.pos}, "
                f"file is {len(self.data)} bytes"
            )
        chunk = self.data[self.pos:self.pos + size]
        self.pos += size
        return chunk

    def i32(self, what: str) -> int:
        return struct.unpack("<i", self.take(4, what))[0]

    def count(self, what: str, limit: int) -> int:
        value = self.i32(what)
        if not 0 <= value <= limit:
            raise ValueError(f"Corrupt .tex file: {what} is {value} (allowed 0..{limit})")
        return value

    def cstring(self, what: str, max_len: int | None = 16) -> str:
        end_limit = len(self.data) if max_len is None else self.pos + max_len + 1
        end = self.data.find(b"\0", self.pos, end_limit)
        if end == -1:
            raise ValueError(f"Truncated or corrupt .tex file: unterminated {what} at offset {self.pos}")
        text = self.data[self.pos:end].decode("ascii", errors="replace")
        self.pos = end + 1
        return text


def lz4_decompress(src: bytes, size: int) -> bytes:
    """Decompress one LZ4 block into exactly `size` bytes (pure Python)."""
    out = bytearray()
    i, n = 0, len(src)
    while i < n:
        token = src[i]
        i += 1
        literal_len = token >> 4
        if literal_len == 15:
            while True:
                if i >= n:
                    raise ValueError("Corrupt LZ4 data: truncated literal length")
                extra = src[i]
                i += 1
                literal_len += extra
                if extra != 255:
                    break
        if i + literal_len > n or len(out) + literal_len > size:
            raise ValueError("Corrupt LZ4 data: literal run overflows")
        out += src[i:i + literal_len]
        i += literal_len
        if i >= n:
            break  # The last sequence carries literals only
        if i + 2 > n:
            raise ValueError("Corrupt LZ4 data: truncated match offset")
        offset = src[i] | src[i + 1] << 8
        i += 2
        if offset == 0 or offset > len(out):
            raise ValueError(f"Corrupt LZ4 data: invalid match offset {offset}")
        match_len = token & 15
        if match_len == 15:
            while True:
                if i >= n:
                    raise ValueError("Corrupt LZ4 data: truncated match length")
                extra = src[i]
                i += 1
                match_len += extra
                if extra != 255:
                    break
        match_len += 4
        if len(out) + match_len > size:
            raise ValueError("Corrupt LZ4 data: match overflows the decompressed size")
        start = len(out) - offset
        if match_len <= offset:
            out += out[start:start + match_len]
        else:
            # Overlapping match: the last `offset` bytes repeat as a pattern
            pattern = bytes(out[start:])
            repeats, rest = divmod(match_len, offset)
            out += pattern * repeats + pattern[:rest]
    if len(out) != size:
        raise ValueError(f"Corrupt LZ4 data: got {len(out)} bytes, expected {size}")
    return bytes(out)


def _read_mipmap(r: _Reader, version: int) -> Mipmap:
    if version == 4:
        # Unknown editor parameters; RePKG rejects anything but 1, 2, <json>, 1.
        params = (r.i32("mipmap param1"), r.i32("mipmap param2"))
        r.cstring("mipmap condition JSON", max_len=None)
        params += (r.i32("mipmap param3"),)
        if params != (1, 2, 1):
            raise ValueError(f"Unsupported TEXB0004 mipmap parameters: {params}")
    width, height = r.i32("mipmap width"), r.i32("mipmap height")
    is_lz4, decompressed_size = False, 0
    if version >= 2:
        is_lz4 = r.i32("mipmap LZ4 flag") == 1
        decompressed_size = r.i32("mipmap decompressed size")
    byte_count = r.i32("mipmap byte count")
    if byte_count > MAX_MIPMAP_BYTES:
        raise ValueError(f"Corrupt .tex file: mipmap byte count {byte_count} exceeds {MAX_MIPMAP_BYTES}")
    data = r.take(byte_count, "mipmap data")
    if is_lz4:
        if not 0 <= decompressed_size <= MAX_MIPMAP_BYTES:
            raise ValueError(f"Corrupt .tex file: LZ4 decompressed size {decompressed_size} is out of range")
        data = lz4_decompress(data, decompressed_size)
    return Mipmap(width, height, data)


def parse_tex(data: bytes) -> TexInfo:
    """Parse a whole .tex file (bytes) into its header, images, mipmaps and frames."""
    r = _Reader(data)
    magic = r.cstring("TEXV magic")
    if not magic.startswith("TEXV"):
        raise ValueError(f"Not a Wallpaper Engine texture: bad magic {magic[:16]!r}")
    magic = r.cstring("TEXI magic")
    if not magic.startswith("TEXI"):
        raise ValueError(f"Not a Wallpaper Engine texture: bad TEXI magic {magic[:16]!r}")

    fmt, flags, tex_w, tex_h, img_w, img_h, _unk = struct.unpack("<7i", r.take(28, "TEXI header"))
    if fmt not in TEX_FORMATS:
        raise ValueError(f"Unknown texture format {fmt}")

    container = r.cstring("TEXB magic")
    if container not in ("TEXB0001", "TEXB0002", "TEXB0003", "TEXB0004"):
        raise ValueError(f"Unsupported image container {container[:16]!r}")
    version = int(container[4:])
    image_count = r.count("image count", MAX_IMAGES)
    image_format = FIF_UNKNOWN
    if version >= 3:
        image_format = r.i32("FreeImage format")
    if version == 4:
        is_mp4 = r.i32("MP4 flag") == 1
        if image_format == FIF_UNKNOWN and is_mp4:
            image_format = FIF_MP4
        if image_format != FIF_MP4:
            version = 3  # TEXB0004 without MP4 uses the TEXB0003 mipmap layout
    if not FIF_UNKNOWN <= image_format <= FIF_MP4:
        raise ValueError(f"Unknown FreeImage format {image_format}")

    images = []
    for _ in range(image_count):
        mipmap_count = r.count("mipmap count", MAX_MIPMAPS)
        images.append([_read_mipmap(r, version) for _ in range(mipmap_count)])

    info = TexInfo(container, fmt, flags, tex_w, tex_h, img_w, img_h, image_format, images)

    if info.is_gif:
        texs = r.cstring("TEXS magic")
        if texs not in ("TEXS0001", "TEXS0002", "TEXS0003"):
            raise ValueError(f"Unsupported frame container {texs[:16]!r}")
        frame_count = r.count("frame count", MAX_FRAMES)
        if texs == "TEXS0003":
            info.gif_width, info.gif_height = r.i32("GIF width"), r.i32("GIF height")
        layout = "<if6i" if texs == "TEXS0001" else "<i7f"
        info.frames = [Frame(*struct.unpack(layout, r.take(32, "frame"))) for _ in range(frame_count)]
        # TEXS0001/0002 don't store the GIF size; RePKG takes it from the first frame.
        if (info.gif_width == 0 or info.gif_height == 0) and info.frames:
            info.gif_width, info.gif_height = int(info.frames[0].width), int(info.frames[0].height)

    return info


# --- Pixel decoding -------------------------------------------------------

_IDX2 = [bytes((b & 3, b >> 2 & 3, b >> 4 & 3, b >> 6)) for b in range(256)]
_IDX3 = [bytes((v & 7, v >> 3 & 7, v >> 6 & 7, v >> 9)) for v in range(4096)]
_NIBBLES = [bytes(((b & 15) * 17, (b >> 4) * 17)) for b in range(256)]


def _rgb565(v: int) -> tuple[int, int, int]:
    r, g, b = v >> 11 & 31, v >> 5 & 63, v & 31
    return r << 3 | r >> 2, g << 2 | g >> 4, b << 3 | b >> 2


def _color_palette(block: bytes, dxt1: bool) -> list[bytes]:
    """The 4 RGBA colors of a DXT color block (libsquish rounding, as in RePKG's DXT.cs)."""
    a, b = block[0] | block[1] << 8, block[2] | block[3] << 8
    c0, c1 = _rgb565(a), _rgb565(b)
    if dxt1 and a <= b:
        mid = bytes((x + y) // 2 for x, y in zip(c0, c1)) + b"\xff"
        return [bytes(c0) + b"\xff", bytes(c1) + b"\xff", mid, bytes(4)]
    c2 = bytes((2 * x + y) // 3 for x, y in zip(c0, c1)) + b"\xff"
    c3 = bytes((x + 2 * y) // 3 for x, y in zip(c0, c1)) + b"\xff"
    return [bytes(c0) + b"\xff", bytes(c1) + b"\xff", c2, c3]


def _dxt5_alphas(a0: int, a1: int) -> bytes:
    if a0 > a1:
        return bytes([a0, a1] + [((7 - i) * a0 + i * a1) // 7 for i in range(1, 7)])
    return bytes([a0, a1] + [((5 - i) * a0 + i * a1) // 5 for i in range(1, 5)] + [0, 255])


def decode_dxt(data: bytes, width: int, height: int, fmt: int) -> bytes:
    """Pure-Python DXT1/3/5 decoder returning RGBA bytes (the no-Pillow fallback)."""
    bw, bh = (width + 3) // 4, (height + 3) // 4
    block_size = 8 if fmt == DXT1 else 16
    color_at = 0 if fmt == DXT1 else 8
    row = bw * 16  # bytes per output row, padded to whole blocks
    out = bytearray(row * bh * 4)
    palettes: dict[bytes, list[bytes]] = {}
    alphas: dict[bytes, bytes] = {}
    o = 0
    for by in range(bh):
        for bx in range(bw):
            c = o + color_at
            key = data[c:c + 4]
            palette = palettes.get(key)
            if palette is None:
                palette = palettes[key] = _color_palette(key, fmt == DXT1)
            indices = _IDX2[data[c + 4]] + _IDX2[data[c + 5]] + _IDX2[data[c + 6]] + _IDX2[data[c + 7]]
            pixels = bytearray(b"".join(map(palette.__getitem__, indices)))
            if fmt == DXT3:
                pixels[3::4] = b"".join(map(_NIBBLES.__getitem__, data[o:o + 8]))
            elif fmt == DXT5:
                akey = data[o:o + 2]
                codes = alphas.get(akey)
                if codes is None:
                    codes = alphas[akey] = _dxt5_alphas(data[o], data[o + 1])
                bits = int.from_bytes(data[o + 2:o + 8], "little")
                idx = _IDX3[bits & 4095] + _IDX3[bits >> 12 & 4095] + _IDX3[bits >> 24 & 4095] + _IDX3[bits >> 36]
                pixels[3::4] = bytes(map(codes.__getitem__, idx))
            dst = by * 4 * row + bx * 16
            for y in range(4):
                out[dst + y * row:dst + y * row + 16] = pixels[y * 16:y * 16 + 16]
            o += block_size
    return crop_rgba(bytes(out), bw * 4, bh * 4, width, height)


def crop_rgba(rgba: bytes, width: int, height: int, new_width: int, new_height: int) -> bytes:
    """Keep the top-left new_width x new_height pixels."""
    if (new_width, new_height) == (width, height):
        return rgba
    stride = width * 4
    return b"".join(rgba[y * stride:y * stride + new_width * 4] for y in range(new_height))


def decode_pixels(fmt: int, width: int, height: int, data: bytes) -> bytes:
    """Decode one raw mipmap into RGBA bytes."""
    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid mipmap size {width}x{height}")
    pixels = width * height
    if fmt in (DXT1, DXT3, DXT5):
        need = ((width + 3) // 4) * ((height + 3) // 4) * (8 if fmt == DXT1 else 16)
    else:
        need = pixels * {RGBA8888: 4, RG88: 2, R8: 1}[fmt]
    if len(data) < need:
        raise ValueError(
            f"Mipmap data too short for {width}x{height} {TEX_FORMATS[fmt]}: {len(data)} of {need} bytes"
        )
    data = data[:need]

    if fmt == RGBA8888:
        return data
    if fmt in (DXT1, DXT3, DXT5):
        if HAS_PILLOW:
            n = {DXT1: 1, DXT3: 2, DXT5: 3}[fmt]
            return Image.frombytes("RGBA", (width, height), data, "bcn", n).tobytes()
        return decode_dxt(data, width, height, fmt)

    # R8 is grayscale; RG88 is gray in G and alpha in R (RePKG's RG88 pixel type).
    rgba = bytearray(pixels * 4)
    if fmt == R8:
        rgba[0::4] = rgba[1::4] = rgba[2::4] = data
        rgba[3::4] = b"\xff" * pixels
    else:
        rgba[0::4] = rgba[1::4] = rgba[2::4] = data[1::2]
        rgba[3::4] = data[0::2]
    return bytes(rgba)


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


def _save_rgba(rgba: bytes, width: int, height: int, output_dir: Path, name: str) -> Path:
    """Save RGBA pixels as PNG with Pillow, or as a hand-built 32-bit BMP without it."""
    if HAS_PILLOW:
        path = output_dir / f"{name}.png"
        Image.frombytes("RGBA", (width, height), rgba).save(path, "PNG")
        return path
    bgra = bytearray(rgba)
    bgra[0::4], bgra[2::4] = rgba[2::4], rgba[0::4]
    path = output_dir / f"{name}.bmp"
    path.write_bytes(create_bmp(width, height, bytes(bgra)))
    return path


def _image_extension(data: bytes, image_format: int) -> str:
    """File extension for an embedded image: trust the magic bytes, else the FreeImage id."""
    for signature, ext in IMAGE_SIGNATURES:
        if data.startswith(signature):
            return ext
    return FIF_EXTENSIONS[image_format]


def _crop_size(info: TexInfo, mip: Mipmap) -> tuple[int, int]:
    """Visible size of a mipmap: textures are padded (e.g. to powers of two) beyond imageWidth x imageHeight."""
    if min(info.texture_width, info.texture_height, info.image_width, info.image_height) <= 0:
        return mip.width, mip.height
    return (
        min(mip.width, max(1, info.image_width * mip.width // info.texture_width)),
        min(mip.height, max(1, info.image_height * mip.height // info.texture_height)),
    )


def _save_gif(info: TexInfo, path: Path) -> Path:
    """Assemble the TEXS frames into an animated GIF (RePKG's TexToImageConverter.ConvertToGif)."""
    sheets = []
    for image in info.images:
        if not image:
            raise ValueError("Animated texture has an image without mipmaps")
        mip = image[0]
        if info.image_format == FIF_UNKNOWN:
            rgba = decode_pixels(info.format, mip.width, mip.height, mip.data)
            sheets.append(Image.frombytes("RGBA", (mip.width, mip.height), rgba))
        else:
            sheets.append(Image.open(io.BytesIO(mip.data)).convert("RGBA"))

    frames, durations = [], []
    for f in info.frames:
        if not 0 <= f.image_id < len(sheets):
            raise ValueError(f"GIF frame points to missing image {f.image_id}")
        # Rotated frames store their size in height_x/width_y instead of width/height.
        width = f.width if f.width != 0 else f.height_x
        height = f.height if f.height != 0 else f.width_y
        x, y = int(min(f.x, f.x + width)), int(min(f.y, f.y + height))
        frame = sheets[f.image_id].crop((x, y, x + int(abs(width)), y + int(abs(height))))
        # Quarter turns, clockwise like RePKG's ImageSharp Rotate; Pillow rotates counter-clockwise.
        angle = math.atan2((height > 0) - (height < 0), (width > 0) - (width < 0))
        degrees = round(-(angle - math.pi / 4) * 180 / math.pi)
        if degrees % 360:
            frame = frame.rotate(-degrees, expand=True)
        frames.append(frame)
        durations.append(round(f.frametime * 100) * 10)  # GIF delays are in centiseconds

    frames[0].save(path, save_all=True, append_images=frames[1:], duration=durations, loop=0, disposal=2)
    return path


def extract_tex_file(
    tex_path: Path,
    output_dir: Path | None = None,
    extract_all_mipmaps: bool = False,
    log_callback=None,
) -> list[Path]:
    """Extract textures from a Wallpaper Engine .tex file to standard image formats.

    Args:
        tex_path: Path to the .tex file.
        output_dir: Optional output directory. Defaults to the same directory as the .tex file.
        extract_all_mipmaps: If True, extract all mipmap sizes. Otherwise, only extract the largest (original) resolution.
        log_callback: Optional callable for logging warnings (e.g. log_callback(message)).

    Returns:
        List of paths to the extracted image (or video) files.
    """
    tex_path = Path(tex_path)
    if not tex_path.is_file():
        raise FileNotFoundError(f"TEX file not found: {tex_path}")
    output_dir = tex_path.parent if output_dir is None else Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    log = log_callback or print

    info = parse_tex(tex_path.read_bytes())
    base_name = tex_path.stem
    if not info.images or not info.images[0]:
        raise ValueError(f"{tex_path.name} contains no image data")

    if info.is_video:
        data = info.images[0][0].data
        if data[4:8] != b"ftyp":
            raise ValueError(f"{tex_path.name} is a video texture without an MP4 header")
        path = output_dir / f"{base_name}.mp4"
        path.write_bytes(data)
        return [path]

    extracted_paths: list[Path] = []
    for i, image in enumerate(info.images):
        for j, mip in enumerate(image):
            if j > 0 and not extract_all_mipmaps:
                break  # Skip smaller mipmaps unless requested
            name = base_name + (f"_{i}" if i else "")
            if info.image_format != FIF_UNKNOWN:
                # Embedded image file (PNG/JPG/...), written as-is
                if extract_all_mipmaps:
                    name += f"_{mip.width}x{mip.height}"
                path = output_dir / f"{name}.{_image_extension(mip.data, info.image_format)}"
                path.write_bytes(mip.data)
            else:
                width, height = _crop_size(info, mip)
                rgba = crop_rgba(decode_pixels(info.format, mip.width, mip.height, mip.data),
                                 mip.width, mip.height, width, height)
                if extract_all_mipmaps:
                    name += f"_{width}x{height}"
                path = _save_rgba(rgba, width, height, output_dir, name)
            extracted_paths.append(path)

    if info.is_gif and info.frames:
        if HAS_PILLOW:
            extracted_paths.append(_save_gif(info, output_dir / f"{base_name}.gif"))
        else:
            log(f"Pillow is not installed: saved the sprite sheet of {tex_path.name} but skipped the animated GIF.")

    return extracted_paths
