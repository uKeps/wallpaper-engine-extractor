import os
import struct
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from builders import (
    COLOR_BLOCK_3, COLOR_ROW_3, DXT5_ALPHA_5, DXT5_CODES_5, COLOR_BLOCK,
    dxt_block, dxt_block_rgba, lz4_compress, lz4_sequence, mip, read_image, tex_bytes,
)
from src import tex_parser as tp

PILLOW_MODES = [False] + ([True] if tp.HAS_PILLOW else [])
CONTAINERS = ["TEXB0001", "TEXB0002", "TEXB0003", "TEXB0004"]
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"not-really-a-png"
JPG_BYTES = b"\xFF\xD8\xFF\xE0" + b"not-really-a-jpg"
MP4_BYTES = b"\0\0\0\x18ftypisom" + b"\0" * 20


def sample(fmt: int, width: int, height: int) -> tuple[bytes, bytes]:
    """(encoded payload, expected RGBA) for a width x height texture in `fmt`."""
    n = width * height
    if fmt == tp.RGBA8888:
        data = bytes((i * 7) % 256 for i in range(n * 4))
        return data, data
    if fmt == tp.R8:
        data = bytes((i * 13) % 256 for i in range(n))
        return data, b"".join(bytes((v, v, v, 255)) for v in data)
    if fmt == tp.RG88:
        data = bytes((i * 5) % 256 for i in range(n * 2))
        return data, b"".join(bytes((data[i + 1],) * 3 + (data[i],)) for i in range(0, n * 2, 2))
    name = tp.TEX_FORMATS[fmt]
    block = dxt_block(name)
    pixels = dxt_block_rgba(name)
    data = block * (((width + 3) // 4) * ((height + 3) // 4))
    expected = b"".join(bytes(pixels[(y % 4) * 4 + x % 4]) for y in range(height) for x in range(width))
    return data, expected


def gif_tex(texs="TEXS0003", rotated=False):
    # 4x2 sheet: left 2x2 red, right 2x2 blue
    red, blue = bytes((255, 0, 0, 255)) * 2, bytes((0, 0, 255, 255)) * 2
    sheet = (red + blue) * 2
    if rotated:
        # stored rotated: width=0, height_x=-2 / height=0, width_y=2 -> needs a quarter turn
        frames = [(0, 0.1, 4, 0, 0, 2, -2, 0)]
    else:
        frames = [(0, 0.1, 0, 0, 2, 0, 0, 2), (0, 0.25, 2, 0, 2, 0, 0, 2)]
    return tex_bytes(flags=tp.FLAG_IS_GIF, size=(4, 2), images=[[mip(4, 2, sheet)]],
                     texs=texs, frames=frames, gif_size=(2, 2))


@contextmanager
def pillow(enabled: bool):
    with mock.patch.object(tp, "HAS_PILLOW", enabled):
        yield


class TempDirCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def extract(self, data: bytes, name="tex", **kwargs) -> list[Path]:
        path = self.tmp / f"{name}.tex"
        path.write_bytes(data)
        out = self.tmp / f"out_{name}"
        return tp.extract_tex_file(path, out, **kwargs)


class Lz4Test(unittest.TestCase):
    def test_literals_only(self):
        for n in (0, 1, 14, 15, 16, 269, 270, 271, 600):
            data = bytes(range(256)) * 3
            data = data[:n]
            self.assertEqual(tp.lz4_decompress(lz4_sequence(data), n), data)

    def test_match_and_final_literals(self):
        src = lz4_sequence(b"abcdefgh", 8, 8) + lz4_sequence(b"XYZ")
        self.assertEqual(tp.lz4_decompress(src, 19), b"abcdefghabcdefghXYZ")

    def test_overlapping_matches(self):
        # offset 1 repeats one byte; offset 3 repeats a 3-byte pattern past its own end
        src = lz4_sequence(b"a", 1, 9) + lz4_sequence(b"xyz", 3, 10) + lz4_sequence(b"!")
        self.assertEqual(tp.lz4_decompress(src, 24), b"a" * 10 + b"xyz" + b"xyzxyzxyzx" + b"!")

    def test_long_match_length(self):
        for match_len in (18, 19, 20, 273, 274, 1000):
            src = lz4_sequence(b"ab", 2, match_len) + lz4_sequence(b"")
            self.assertEqual(tp.lz4_decompress(src, 2 + match_len), (b"ab" * 600)[:2 + match_len])

    def test_round_trip(self):
        data = os.urandom(300) + b"\0" * 5000 + bytes(range(256)) * 20 + os.urandom(50) + b"tail-tail-tail"
        compressed = lz4_compress(data)
        self.assertLess(len(compressed), len(data))
        self.assertEqual(tp.lz4_decompress(compressed, len(data)), data)

    def test_corrupt_inputs(self):
        good = lz4_sequence(b"abcd", 4, 8) + lz4_sequence(b"e")
        cases = {
            "offset zero": lz4_sequence(b"abcd", 0, 4),
            "offset before start": lz4_sequence(b"abcd", 5, 4),
            "truncated offset": lz4_sequence(b"abcd", 4, 4)[:-1],
            "truncated literal": bytes([0x50]) + b"ab",
            "truncated length": bytes([0xF0]),
        }
        for name, src in cases.items():
            with self.subTest(name), self.assertRaises(ValueError):
                tp.lz4_decompress(src, 13)
        with self.assertRaises(ValueError):
            tp.lz4_decompress(good, 12)  # output larger than declared
        with self.assertRaises(ValueError):
            tp.lz4_decompress(good, 14)  # output smaller than declared


class DxtTest(unittest.TestCase):
    def test_hand_encoded_blocks(self):
        for name, fmt in (("DXT1", tp.DXT1), ("DXT3", tp.DXT3), ("DXT5", tp.DXT5)):
            for use_pillow in PILLOW_MODES:
                with self.subTest(name, pillow=use_pillow), pillow(use_pillow):
                    rgba = tp.decode_pixels(fmt, 4, 4, dxt_block(name))
                    self.assertEqual(rgba, b"".join(bytes(p) for p in dxt_block_rgba(name)))

    def test_dxt1_three_color_mode(self):
        for use_pillow in PILLOW_MODES:
            with self.subTest(pillow=use_pillow), pillow(use_pillow):
                rgba = tp.decode_pixels(tp.DXT1, 4, 4, COLOR_BLOCK_3)
                self.assertEqual(rgba, b"".join(bytes(COLOR_ROW_3[k % 4]) for k in range(16)))
                # Equal endpoints are 3-color mode too, so index 3 is still transparent
                rgba = tp.decode_pixels(tp.DXT1, 4, 4, struct.pack("<HH", 0xF800, 0xF800) + bytes([0xFF] * 4))
                self.assertEqual(rgba, bytes(4) * 16)

    def test_dxt5_five_step_alpha(self):
        rgba = tp.decode_dxt(DXT5_ALPHA_5 + COLOR_BLOCK, 4, 4, tp.DXT5)
        self.assertEqual(list(rgba[3::4]), [DXT5_CODES_5[k % 8] for k in range(16)])

    def test_sizes_not_multiple_of_four(self):
        for use_pillow in PILLOW_MODES:
            for w, h in ((1, 1), (2, 2), (6, 5)):
                with self.subTest(size=(w, h), pillow=use_pillow), pillow(use_pillow):
                    data, expected = sample(tp.DXT5, w, h)
                    self.assertEqual(tp.decode_pixels(tp.DXT5, w, h, data), expected)

    @unittest.skipUnless(tp.HAS_PILLOW, "Pillow not installed")
    def test_pure_python_matches_pillow_on_random_blocks(self):
        for fmt in (tp.DXT1, tp.DXT3, tp.DXT5):
            data = os.urandom(16 * 16 * (8 if fmt == tp.DXT1 else 16))
            with self.subTest(tp.TEX_FORMATS[fmt]):
                self.assertEqual(tp.decode_dxt(data, 64, 64, fmt), tp.decode_pixels(fmt, 64, 64, data))


class ExtractTexTest(TempDirCase):
    def test_every_container_and_format(self):
        for use_pillow in PILLOW_MODES:
            for container in CONTAINERS:
                for fmt, name in tp.TEX_FORMATS.items():
                    for lz4 in ((False,) if container == "TEXB0001" else (False, True)):
                        label = f"{container}_{name}_{lz4}_{use_pillow}"
                        with self.subTest(label), pillow(use_pillow):
                            data, expected = sample(fmt, 8, 8)
                            tex = tex_bytes(fmt=fmt, size=(8, 8), images=[[mip(8, 8, data, lz4)]], container=container)
                            paths = self.extract(tex, label)
                            self.assertEqual(len(paths), 1)
                            self.assertEqual(paths[0].suffix, ".png" if use_pillow else ".bmp")
                            self.assertEqual(paths[0].name, f"{label}{paths[0].suffix}")
                            self.assertEqual(read_image(paths[0]), (8, 8, expected))

    def test_embedded_png_and_jpg(self):
        cases = [(13, PNG_BYTES, ".png"), (2, JPG_BYTES, ".jpg"), (13, JPG_BYTES, ".jpg"), (17, b"tga-data", ".tga")]
        for container in ("TEXB0003", "TEXB0004"):
            for fif, payload, ext in cases:
                with self.subTest(container=container, fif=fif, ext=ext):
                    tex = tex_bytes(size=(4, 4), images=[[mip(4, 4, payload, lz4=True)]], container=container, fif=fif)
                    paths = self.extract(tex, f"img_{container}_{fif}{ext[1:]}")
                    self.assertEqual([p.suffix for p in paths], [ext])
                    self.assertEqual(paths[0].read_bytes(), payload)

    def test_padded_texture_is_cropped(self):
        for use_pillow in PILLOW_MODES:
            for fmt in (tp.RGBA8888, tp.DXT1):
                with self.subTest(fmt=fmt, pillow=use_pillow), pillow(use_pillow):
                    data, full = sample(fmt, 8, 8)
                    tex = tex_bytes(fmt=fmt, size=(8, 8), image_size=(6, 5), images=[[mip(8, 8, data)]])
                    path, = self.extract(tex, f"pad_{fmt}_{use_pillow}")
                    expected = b"".join(full[y * 32:y * 32 + 24] for y in range(5))
                    self.assertEqual(read_image(path), (6, 5, expected))

    def test_mipmaps(self):
        big, big_px = sample(tp.RGBA8888, 8, 8)
        small, small_px = sample(tp.R8, 4, 4)
        small = bytes(small_px)  # second mipmap stored as RGBA too
        tex = tex_bytes(size=(8, 8), image_size=(6, 6), images=[[mip(8, 8, big), mip(4, 4, small)]])
        with pillow(False):
            self.assertEqual([p.name for p in self.extract(tex, "one")], ["one.bmp"])
            paths = self.extract(tex, "all", extract_all_mipmaps=True)
        self.assertEqual([p.name for p in paths], ["all_6x6.bmp", "all_3x3.bmp"])
        self.assertEqual(read_image(paths[1])[:2], (3, 3))

    def test_mp4_texture(self):
        for container, kwargs in (("TEXB0004", {"mp4": True}), ("TEXB0004", {"fif": 35}), ("TEXB0003", {"flags": 32})):
            with self.subTest(container=container, **kwargs):
                tex = tex_bytes(size=(4, 4), images=[[mip(4, 4, MP4_BYTES, lz4=True)]], container=container, **kwargs)
                paths = self.extract(tex, f"video_{len(kwargs)}_{list(kwargs)[0]}", extract_all_mipmaps=True)
                self.assertEqual([p.suffix for p in paths], [".mp4"])
                self.assertEqual(paths[0].read_bytes(), MP4_BYTES)

    def test_mp4_texture_without_mp4_header(self):
        tex = tex_bytes(size=(4, 4), images=[[mip(4, 4, b"garbage" * 4)]], container="TEXB0004", mp4=True)
        with self.assertRaises(ValueError):
            self.extract(tex)

    def test_gif_sheet_without_pillow(self):
        logs = []
        with pillow(False):
            paths = self.extract(gif_tex(), "anim", log_callback=logs.append)
        self.assertEqual([p.name for p in paths], ["anim.bmp"])
        self.assertEqual(read_image(paths[0])[:2], (4, 2))
        self.assertTrue(any("Pillow" in line and "GIF" in line for line in logs))

    @unittest.skipUnless(tp.HAS_PILLOW, "Pillow not installed")
    def test_gif_frames_with_pillow(self):
        from PIL import Image
        for texs in ("TEXS0001", "TEXS0002", "TEXS0003"):
            with self.subTest(texs):
                paths = self.extract(gif_tex(texs), f"anim{texs}")
                self.assertEqual([p.suffix for p in paths], [".png", ".gif"])
                with Image.open(paths[1]) as gif:
                    self.assertEqual((gif.n_frames, gif.size), (2, (2, 2)))
                    colors, durations = [], []
                    for i in range(2):
                        gif.seek(i)
                        colors.append(gif.convert("RGB").getpixel((0, 0)))
                        durations.append(gif.info["duration"])
                self.assertEqual(colors, [(255, 0, 0), (0, 0, 255)])
                self.assertEqual(durations, [100, 250])

    @unittest.skipUnless(tp.HAS_PILLOW, "Pillow not installed")
    def test_gif_rotated_frame(self):
        from PIL import Image
        paths = self.extract(gif_tex(rotated=True), "rot")
        with Image.open(paths[1]) as gif:
            self.assertEqual(gif.size, (2, 2))
            self.assertEqual(gif.convert("RGB").getpixel((1, 1)), (0, 0, 255))

    def test_multiple_images_get_index_suffix(self):
        data, _ = sample(tp.RGBA8888, 4, 4)
        tex = tex_bytes(size=(4, 4), images=[[mip(4, 4, data)], [mip(4, 4, data)]])
        with pillow(False):
            self.assertEqual([p.name for p in self.extract(tex, "multi")], ["multi.bmp", "multi_1.bmp"])


class CorruptTexTest(TempDirCase):
    def valid_files(self):
        data, _ = sample(tp.DXT5, 8, 8)
        yield tex_bytes(fmt=tp.DXT5, size=(8, 8), images=[[mip(8, 8, data, lz4=True), mip(4, 4, data[:16])]])
        yield tex_bytes(size=(4, 4), images=[[mip(4, 4, MP4_BYTES)]], container="TEXB0004", mp4=True)
        yield gif_tex()
        yield tex_bytes(size=(4, 4), images=[[mip(4, 4, b"\0" * 64)]], container="TEXB0001")

    def test_every_truncation_raises_value_error(self):
        for n, tex in enumerate(self.valid_files()):
            tp.parse_tex(tex)  # the full file is fine
            for cut in range(len(tex)):
                with self.subTest(file=n, cut=cut), self.assertRaises(ValueError):
                    tp.parse_tex(tex[:cut])

    def test_bad_fields(self):
        good = tex_bytes(size=(4, 4), images=[[mip(4, 4, b"\0" * 64)]])
        header_at = 18  # after "TEXV0005\0TEXI0001\0"
        texb_at = header_at + 28 + 9
        def patch(offset, value):
            return good[:offset] + struct.pack("<i", value) + good[offset + 4:]
        cases = {
            "bad magic": b"XXXV0005" + good[8:],
            "unknown format": patch(header_at, 3),
            "unknown container": good.replace(b"TEXB0003", b"TEXB0009"),
            "image count": patch(texb_at, 1000),
            "negative image count": patch(texb_at, -1),
            "FreeImage format": patch(texb_at + 4, 99),
            "mipmap count": patch(texb_at + 8, 33),
            "huge byte count": patch(texb_at + 12 + 16, 0x7FFFFFFF),
            "byte count past end": patch(texb_at + 12 + 16, 65),
        }
        for name, tex in cases.items():
            with self.subTest(name), self.assertRaises(ValueError):
                tp.parse_tex(tex)

    def test_huge_lz4_size_is_rejected_before_allocating(self):
        tex = tex_bytes(size=(4, 4), images=[[mip(4, 4, b"\0" * 64, lz4=True)]])
        at = tex.index(struct.pack("<ii", 1, 64)) + 4
        with self.assertRaises(ValueError):
            tp.parse_tex(tex[:at] + struct.pack("<i", 0x7FFFFFFF) + tex[at + 4:])

    def test_short_pixel_data(self):
        for fmt in tp.TEX_FORMATS:
            tex = tex_bytes(fmt=fmt, size=(64, 64), images=[[mip(64, 64, b"\0" * 8)]])
            with self.subTest(tp.TEX_FORMATS[fmt]), pillow(False), self.assertRaises(ValueError):
                self.extract(tex, f"short{fmt}")

    def test_huge_dimensions_do_not_allocate(self):
        tex = tex_bytes(fmt=tp.DXT1, size=(4, 4), images=[[mip(0x7FFFFFF, 0x7FFFFFF, b"\0" * 8)]])
        with pillow(False), self.assertRaises(ValueError):
            self.extract(tex)

    def test_gif_frame_points_to_missing_image(self):
        tex = tex_bytes(flags=tp.FLAG_IS_GIF, size=(4, 4), images=[[mip(4, 4, b"\0" * 64)]],
                        texs="TEXS0002", frames=[(5, 0.1, 0, 0, 2, 0, 0, 2)])
        if tp.HAS_PILLOW:
            with self.assertRaises(ValueError):
                self.extract(tex)


if __name__ == "__main__":
    unittest.main()
