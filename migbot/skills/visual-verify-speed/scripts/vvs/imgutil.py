"""Side-by-side images and a small perceptual hash (Pillow; without Pillow both degrade to None)."""
from __future__ import annotations

import os

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover
    Image = None
    ImageDraw = None
    ImageFont = None

HEIGHT = 1400
FONTS = ("/System/Library/Fonts/Hiragino Sans GB.ttc", "/System/Library/Fonts/STHeiti Medium.ttc",
         "/System/Library/Fonts/PingFang.ttc", "/Library/Fonts/Arial Unicode.ttf",
         "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
         "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf")
_font = None


def font():
    """A CJK-capable font for the panel titles; PIL's default font when none is installed (titles fall back to ASCII)."""
    global _font
    if _font is None:
        import os
        for path in FONTS:
            if os.path.exists(path):
                try:
                    _font = ImageFont.truetype(path, 26)
                    break
                except Exception:
                    continue
        if _font is None:
            _font = False
    return _font or None


def available() -> bool:
    return Image is not None


def _load(path: str):
    im = Image.open(path)
    return im.convert("RGB")


def side_by_side(android_png: str | None, harmony_png: str | None, out: str, title: str = "",
                 density_a: float | None = None, density_h: float | None = None) -> str | None:
    """Android left, HarmonyOS right. With both densities the two panels share one dp scale (equal dp = equal
    pixels, top-aligned, a grid line every 50 dp) so positions can be compared by eye; without densities both
    panels get the same height. A missing side is an empty panel."""
    if Image is None:
        return None
    ims = [_load(p) if p else None for p in (android_png, harmony_png)]
    dens = (density_a, density_h)
    dp_mode = all(dens) and all(im is not None for im in ims)
    if dp_mode:
        tallest = max(im.height / d for im, d in zip(ims, dens))
        s = HEIGHT / tallest  # output pixels per dp
        panels = [im.resize((max(1, round(im.width / d * s)), max(1, round(im.height / d * s)))) for im, d in zip(ims, dens)]
    else:
        s = None
        panels = []
        for im in ims:
            panels.append(im.resize((max(1, round(im.width * HEIGHT / im.height)), HEIGHT)) if im is not None else None)
    w0 = next((p.width for p in panels if p is not None), 650)
    panels = [p if p is not None else Image.new("RGB", (w0, HEIGHT), (235, 235, 235)) for p in panels]
    gap, head, ruler = 24, 44, (40 if dp_mode else 0)
    height = max(p.height for p in panels)
    canvas = Image.new("RGB", (ruler + panels[0].width + panels[1].width + gap, height + head), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    canvas.paste(panels[0], (ruler, head))
    canvas.paste(panels[1], (ruler + panels[0].width + gap, head))
    f = font()
    if f is None:  # no CJK font: keep the title ASCII so it does not render as boxes
        title = "".join(ch for ch in (title or "") if ord(ch) < 128)
    draw.text((ruler + 8, 8), "Android  " + (title or ""), fill=(0, 0, 0), font=f)
    right = "HarmonyOS" + ("" if harmony_png else "  (missing)")
    if dp_mode:
        right += f"   同一 dp 比例（安卓 {density_a}x / 鸿蒙 {density_h}x）"
    draw.text((ruler + panels[0].width + gap + 8, 8), right, fill=(0, 0, 0), font=f)
    if dp_mode:
        over = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(over)
        for dp in range(50, int(height / s) + 1, 50):
            y = head + round(dp * s)
            od.line([(ruler, y), (canvas.width, y)], fill=(255, 0, 0, 70 if dp % 100 else 120), width=1)
            if dp % 100 == 0:
                od.text((2, y - 10), str(dp), fill=(200, 0, 0, 255))
        canvas = Image.alpha_composite(canvas.convert("RGBA"), over).convert("RGB")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    if out.lower().endswith(".png"):
        canvas.save(out, format="PNG")
    else:
        canvas.save(out, format="JPEG", quality=85)
    return out


def ahash(path: str, top_crop: float = 0.05, size: int = 8) -> str | None:
    """Average hash of the app area (status bar cropped), hex string."""
    if Image is None or not path:
        return None
    try:
        im = _load(path)
    except Exception:
        return None
    top = int(im.height * top_crop)
    im = im.crop((0, top, im.width, im.height)).convert("L").resize((size, size * 2))
    px = list(im.getdata())
    avg = sum(px) / len(px)
    bits = "".join("1" if p >= avg else "0" for p in px)
    return "%0*x" % (len(bits) // 4, int(bits, 2))


def hamming(a: str | None, b: str | None) -> int | None:
    if not a or not b or len(a) != len(b):
        return None
    return bin(int(a, 16) ^ int(b, 16)).count("1")
