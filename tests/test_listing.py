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


class FakeMLFormat:
    def category_attributes(self, category_id):
        return [
            {
                "id": "FORMAT",
                "name": "Formato",
                "values": [
                    {"id": "1", "name": "Digital"},
                    {"id": "2", "name": "Físico"},
                ],
            }
        ]


def test_format_defaults_to_fisico_and_can_be_overridden():
    from anunciar.listing import build_attributes

    cfg = Config(DEFAULTS)
    attrs, _ = build_attributes(FakeMLFormat(), "MLB1", {}, cfg)
    assert {"id": "FORMAT", "value_id": "2"} in attrs
    attrs, _ = build_attributes(FakeMLFormat(), "MLB1", {"format_override": "Digital"}, cfg)
    assert {"id": "FORMAT", "value_id": "1"} in attrs


def test_package_attributes_carry_units_and_flag_missing_values():
    from anunciar.listing import build_package_attributes

    full = {"height_cm": 5, "width_cm": 20, "length_cm": 28, "weight_g": 600}
    attrs, notes = build_package_attributes(full)
    assert {"id": "SELLER_PACKAGE_WEIGHT", "value_name": "600 g"} in attrs
    assert {"id": "SELLER_PACKAGE_HEIGHT", "value_name": "5 cm"} in attrs
    assert notes == []
    attrs, notes = build_package_attributes({"height_cm": 5})
    assert len(attrs) == 1 and "width_cm" in notes[0]
