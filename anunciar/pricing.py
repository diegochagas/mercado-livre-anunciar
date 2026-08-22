"""Regras de preço validadas em código (independente do que o modelo sugerir)."""

from .config import Config


def normalize_ending(price: float, ending: str = ".90") -> float:
    """Força o final configurado (padrão ,90) escolhendo o valor mais próximo."""
    cents = float(ending)
    if price <= 0:
        raise ValueError(f"Preço inválido: {price}")
    reais = round(price)
    below = reais - 1 + cents
    above = reais + cents
    if below <= 0:
        return round(above, 2)
    return round(below if abs(below - price) <= abs(above - price) else above, 2)


def apply_rules(identification: dict, cfg: Config) -> tuple[float, list[str]]:
    """Valida a sugestão do modelo contra as regras do config.

    - Se houver anúncios no Brasil: preço não pode ficar acima do menor
      encontrado (undercut_strategy).
    - Item raro só encontrado no exterior: preço >= menor preço estrangeiro
      convertido x import_multiplier_min.
    - Preço final termina em ,90 (price_ending).
    """
    warnings: list[str] = []
    price = float(identification["suggested_price_brl"])
    research = identification.get("price_research") or []

    brazil = [
        r for r in research
        if r.get("is_brazil") and (r.get("price_brl") or 0) > 0
    ]
    foreign = [
        r for r in research
        if not r.get("is_brazil") and (r.get("price_brl") or 0) > 0
    ]

    if brazil:
        cheapest_br = min(r["price_brl"] for r in brazil)
        if price >= cheapest_br:
            ceiling = cheapest_br - max(1.0, round(cheapest_br * 0.02, 2))
            if ceiling <= 0:
                ceiling = cheapest_br * 0.95
            warnings.append(
                f"Sugestão R$ {price:.2f} não ficou abaixo do menor preço BR "
                f"encontrado (R$ {cheapest_br:.2f}); ajustada para R$ {ceiling:.2f} "
                f"({cfg.pricing['undercut_strategy']})."
            )
            price = ceiling

    if identification.get("is_imported_rare") and foreign and not brazil:
        floor = min(r["price_brl"] for r in foreign) * float(
            cfg.pricing["import_multiplier_min"]
        )
        if price < floor:
            warnings.append(
                f"Sugestão R$ {price:.2f} abaixo do piso de importação "
                f"(menor preço exterior x {cfg.pricing['import_multiplier_min']}); "
                f"elevada para R$ {floor:.2f}."
            )
            price = floor

    final = normalize_ending(price, cfg.pricing["price_ending"])
    if abs(final - price) > 0.005:
        warnings.append(
            f"Preço ajustado de R$ {price:.2f} para R$ {final:.2f} "
            f"(final {cfg.pricing['price_ending'].replace('.', ',')})."
        )
    return final, warnings
