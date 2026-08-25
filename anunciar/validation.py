"""Validação da identificação preenchida manualmente (sem API da Anthropic)."""


class IdentificationError(Exception):
    pass


REQUIRED_FIELDS = ["title_ml", "product_type", "full_name", "suggested_price_brl"]


def validate_identification(data: dict) -> None:
    missing = [k for k in REQUIRED_FIELDS if not data.get(k)]
    if missing:
        raise IdentificationError(
            f"Identificação incompleta, faltam campos obrigatórios: {missing}"
        )
