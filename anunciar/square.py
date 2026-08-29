"""Composição da foto (já com fundo removido) em quadrado com fundo branco."""

import io

from PIL import Image


def to_square_white_jpeg(cutout_png: bytes, size: int = 1200, margin_ratio: float = 0.06) -> bytes:
    """PNG RGBA (fundo já removido) -> JPEG size x size, produto centralizado
    sobre fundo branco com uma margem. Amplia ou reduz conforme necessário
    para sempre bater exatamente em `size`."""
    im = Image.open(io.BytesIO(cutout_png)).convert("RGBA")
    bbox = im.getbbox()
    if bbox:
        im = im.crop(bbox)

    usable = max(1, int(size * (1 - margin_ratio * 2)))
    scale = min(usable / im.width, usable / im.height)
    new_w = max(1, round(im.width * scale))
    new_h = max(1, round(im.height * scale))
    im = im.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("RGB", (size, size), (255, 255, 255))
    x = (size - im.width) // 2
    y = (size - im.height) // 2
    canvas.paste(im, (x, y), im)

    out = io.BytesIO()
    canvas.save(out, "JPEG", quality=92)
    return out.getvalue()
