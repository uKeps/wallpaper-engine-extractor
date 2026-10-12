"""Builders for synthetic .tex / .pkg / LZ4 test fixtures (layout per RePKG's readers)."""

import struct
from pathlib import Path


def lz4_length(n: int) -> bytes:
    """Extra length bytes for a 4-bit length field that saturated at 15."""
    out = bytearray()
    while n >= 255:
        out.append(255)
        n -= 255
    out.append(n)
    return bytes(out)


def lz4_sequence(literals: bytes, offset: int | None = None, match_len: int = 0) -> bytes:
    """One LZ4 sequence; offset=None makes it the final literals-only sequence."""
    lit_n = len(literals)
    m = match_len - 4 if offset is not None else 0
    out = bytearray([min(lit_n, 15) << 4 | min(m, 15)])
    if lit_n >= 15:
        out += lz4_length(lit_n - 15)
    out += literals
    if offset is not None:
        out += struct.pack("<H", offset)
        if m >= 15:
            out += lz4_length(m - 15)
    return bytes(out)


def lz4_compress(data: bytes) -> bytes:
    """Tiny greedy LZ4 block encoder (test-only). Overlapping matches happen on runs."""
    out = bytearray()
    table: dict[bytes, int] = {}
    i = anchor = 0
    n = len(data)
    while i + 12 <= n:  # LZ4 rule: the last 5 bytes are literals, last match starts 12 before the end
        key = data[i:i + 4]
        ref = table.get(key)
        table[key] = i
        if ref is not None and i - ref <= 65535:
            m = 4
            while i + m < n - 5 and data[ref + m] == data[i + m]:
                m += 1
            out += lz4_sequence(data[anchor:i], i - ref, m)
            i += m
            anchor = i
        else:
            i += 1
    out += lz4_sequence(data[anchor:])
    return bytes(out)


def mip(width, height, data, lz4=False):
    return (width, height, data, lz4)


def tex_bytes(
    fmt=0, flags=0, size=(4, 4), image_size=None, images=(), container="TEXB0003",
    fif=-1, mp4=False, texs=None, frames=(), gif_size=(0, 0),
):
    """Assemble a .tex file. images = [[mip(...), ...], ...]."""
    tw, th = size
    iw, ih = image_size or size
    out = bytearray(b"TEXV0005\0TEXI0001\0")
    out += struct.pack("<7i", fmt, flags, tw, th, iw, ih, 0)
    out += container.encode() + b"\0" + struct.pack("<i", len(images))
    version = int(container[4:])
    if version >= 3:
        out += struct.pack("<i", fif)
    if version == 4:
        out += struct.pack("<i", 1 if mp4 else 0)
    v4_layout = version == 4 and (fif == 35 or (fif == -1 and mp4))
    for image in images:
        out += struct.pack("<i", len(image))
        for w, h, data, lz4 in image:
            if v4_layout:
                out += struct.pack("<ii", 1, 2) + b'{"cond":1}\0' + struct.pack("<i", 1)
            out += struct.pack("<ii", w, h)
            payload = lz4_compress(data) if lz4 else data
            if version >= 2:
                out += struct.pack("<ii", 1 if lz4 else 0, len(data))
            out += struct.pack("<i", len(payload)) + payload
    if texs:
        out += texs.encode() + b"\0" + struct.pack("<i", len(frames))
        if texs == "TEXS0003":
            out += struct.pack("<ii", *gif_size)
        layout = "<if6i" if texs == "TEXS0001" else "<i7f"
        for frame in frames:
            out += struct.pack(layout, *frame)
    return bytes(out)


def pkg_bytes(entries: dict[str, bytes], magic="PKGV0024") -> bytes:
    """Assemble a .pkg archive from {name: data}."""
    def pstr(s):
        b = s.encode()
        return struct.pack("<I", len(b)) + b

    header = bytearray(pstr(magic) + struct.pack("<I", len(entries)))
    blob = bytearray()
    for name, data in entries.items():
        header += pstr(name) + struct.pack("<II", len(blob), len(data))
        blob += data
    return bytes(header + blob)


def read_image(path: Path) -> tuple[int, int, bytes]:
    """(width, height, RGBA bytes) of a written .bmp (always) or .png/.gif (needs Pillow)."""
    data = Path(path).read_bytes()
    if data[:2] == b"BM":
        offset, = struct.unpack_from("<I", data, 10)
        width, height = struct.unpack_from("<ii", data, 18)
        bgra = data[offset:offset + width * abs(height) * 4]
        if height > 0:  # bottom-up: flip so rows always come back top-down
            stride = width * 4
            bgra = b"".join(bgra[y:y + stride] for y in range(len(bgra) - stride, -1, -stride))
        height = abs(height)
        rgba = bytearray(bgra)
        rgba[0::4], rgba[2::4] = bgra[2::4], bgra[0::4]
        return width, height, bytes(rgba)
    from PIL import Image
    with Image.open(path) as img:
        return img.width, img.height, img.convert("RGBA").tobytes()


# A hand-encoded DXT color block: c0 = pure red (0xF800), c1 = pure blue (0x001F),
# row indices 0,1,2,3 in every row -> red, blue, 2/3 red + 1/3 blue, 1/3 red + 2/3 blue.
RED, BLUE = (255, 0, 0), (0, 0, 255)
COLOR_BLOCK = struct.pack("<HH", 0xF800, 0x001F) + bytes([0b11100100] * 4)
COLOR_ROW = [RED, BLUE, (170, 0, 85), (85, 0, 170)]
# Same endpoints swapped (c0 <= c1): DXT1 3-color mode, index 3 is transparent black.
COLOR_BLOCK_3 = struct.pack("<HH", 0x001F, 0xF800) + bytes([0b11100100] * 4)
COLOR_ROW_3 = [BLUE + (255,), RED + (255,), (127, 0, 127, 255), (0, 0, 0, 0)]
# DXT3 explicit alpha: pixel k of the block gets alpha nibble k (0..15) -> k * 17.
DXT3_ALPHA = bytes([0x10, 0x32, 0x54, 0x76, 0x98, 0xBA, 0xDC, 0xFE])
# DXT5 alpha: a0=255 > a1=0 (7-step mode); pixel k uses index k % 8.
DXT5_ALPHA = bytes([255, 0]) + (sum(k % 8 << 3 * k for k in range(16))).to_bytes(6, "little")
DXT5_CODES = [255, 0] + [((7 - i) * 255) // 7 for i in range(1, 7)]
# a0=0 <= a1=255 (5-step mode, index 6 = 0, index 7 = 255)
DXT5_ALPHA_5 = bytes([0, 255]) + (sum(k % 8 << 3 * k for k in range(16))).to_bytes(6, "little")
DXT5_CODES_5 = [0, 255] + [(i * 255) // 5 for i in range(1, 5)] + [0, 255]


def dxt_block_rgba(fmt_name: str) -> list[tuple[int, int, int, int]]:
    """Expected 16 RGBA pixels (row-major) of the matching hand-encoded block."""
    pixels = []
    for k in range(16):
        r, g, b = COLOR_ROW[k % 4]
        a = {"DXT1": 255, "DXT3": k * 17, "DXT5": DXT5_CODES[k % 8]}[fmt_name]
        pixels.append((r, g, b, a))
    return pixels


def dxt_block(fmt_name: str) -> bytes:
    return {"DXT1": COLOR_BLOCK, "DXT3": DXT3_ALPHA + COLOR_BLOCK, "DXT5": DXT5_ALPHA + COLOR_BLOCK}[fmt_name]
