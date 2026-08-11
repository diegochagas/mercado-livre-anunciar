"""Leitura da pasta de fotos.

As imagens NUNCA são alteradas para o anúncio — o upload ao Mercado Livre usa os
arquivos originais. Apenas para a chamada de identificação (API da Anthropic),
que tem limite de ~5MB/8000px por imagem, uma cópia temporária reduzida pode ser
gerada; os originais permanecem intocados.
"""

import base64
import mimetypes
import tempfile
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# limites da API da Anthropic para imagens
_MAX_BYTES = 4_500_000
_MAX_SIDE = 7500


def list_images(folder: Path) -> list[Path]:
    """Imagens da pasta em ordem alfabética (a 1ª vira a foto de capa)."""
    if not folder.is_dir():
        raise SystemExit(f"Pasta não encontrada: {folder}")
    images = sorted(
        (p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS),
        key=lambda p: p.name.lower(),
    )
    if not images:
        raise SystemExit(
            f"Nenhuma imagem (jpg/jpeg/png/webp) encontrada em {folder}."
        )
    return images


def _downscale_for_api(path: Path) -> Path:
    """Cópia temporária reduzida só para a identificação. Original intocado."""
    from PIL import Image

    tmpdir = Path(tempfile.mkdtemp(prefix="anunciar-api-"))
    out = tmpdir / (path.stem + ".jpg")
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((2000, 2000))
        im.save(out, "JPEG", quality=85)
    return out


def image_blocks(images: list[Path]) -> list[dict]:
    """Blocos de conteúdo (base64) para a API da Anthropic, na ordem da pasta."""
    blocks = []
    for path in images:
        send_path = path
        try:
            from PIL import Image

            with Image.open(path) as im:
                width, height = im.size
            too_big = (
                path.stat().st_size > _MAX_BYTES
                or max(width, height) > _MAX_SIDE
            )
        except Exception:
            too_big = path.stat().st_size > _MAX_BYTES
        if too_big:
            send_path = _downscale_for_api(path)

        media_type = mimetypes.guess_type(str(send_path))[0] or "image/jpeg"
        data = base64.standard_b64encode(send_path.read_bytes()).decode("utf-8")
        blocks.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": data,
                },
            }
        )
    return blocks
