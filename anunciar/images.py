"""Leitura da pasta de fotos.

As imagens NUNCA são alteradas para o anúncio — o upload ao Mercado Livre usa
os arquivos originais.
"""

from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


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
