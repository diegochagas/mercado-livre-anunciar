"""Invariante: anúncio sempre com disponibilidade imediata (sem MANUFACTURING_TIME)."""

from anunciar.config import DEFAULTS, Config
from anunciar.listing import build_sale_terms


class FakeML:
    def category_sale_terms(self, category_id):
        return [
            {"id": "MANUFACTURING_TIME", "name": "Disponibilidade de estoque"},
            {"id": "WARRANTY_TYPE", "values": [{"id": "6150835", "name": "Sem garantia"}]},
        ]


def test_sale_terms_never_send_manufacturing_time():
    terms, _ = build_sale_terms(FakeML(), "MLB1", Config(DEFAULTS))
    assert "MANUFACTURING_TIME" not in {t["id"] for t in terms}
