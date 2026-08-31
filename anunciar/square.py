"""Composição da foto (já tirada sobre o quadro branco físico) em quadrado."""

import io

from PIL import Image


def to_square_white_jpeg(photo_bytes: bytes, size: int = 1200) -> bytes:
    """Foto (produto sobre o quadro branco) -> JPEG size x size, redimensionada
    para caber inteira, centralizada sobre fundo branco (letterbox)."""
    im = Image.open(io.BytesIO(photo_bytes)).convert("RGB")

    scale = min(size / im.width, size / im.height)
    new_w = max(1, round(im.width * scale))
    new_h = max(1, round(im.height * scale))
    im = im.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("RGB", (size, size), (255, 255, 255))
    x = (size - im.width) // 2
    y = (size - im.height) // 2
    canvas.paste(im, (x, y))

    out = io.BytesIO()
    canvas.save(out, "JPEG", quality=92)
    return out.getvalue()
