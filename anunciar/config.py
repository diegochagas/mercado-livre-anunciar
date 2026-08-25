"""Configuração do anunciar: ~/.config/anunciar/config.toml com padrões editáveis."""

import copy
import tomllib
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "anunciar"
CONFIG_PATH = CONFIG_DIR / "config.toml"
TOKENS_PATH = CONFIG_DIR / "tokens.json"
LOGS_DIR = CONFIG_DIR / "logs"
CACHE_PATH = CONFIG_DIR / "cache.json"

DEFAULTS = {
    "listing": {
        "site_id": "MLB",
        "condition": "used",
        "listing_type": "premium",
        "available_quantity": 1,
        "warranty": "none",
        "availability_days": 1,
        "default_status": "paused",
    },
    "shipping": {
        "free_shipping_threshold": 200.00,
        "flex": False,
    },
    "pricing": {
        "price_ending": ".90",
        "import_multiplier_min": 2.5,
        "import_multiplier_max": 3.0,
        "undercut_strategy": "slightly_below_cheapest_similar_condition",
    },
    "description": {
        "rare_import_line": "ITEM RARO, importado do {país}. Item de colecionador!",
        "closing_line": (
            "As fotos são do item real que será enviado. "
            "Envio com embalagem protegida."
        ),
    },
}

DEFAULT_CONFIG_TOML = '''# Configuração do anunciar — todos os valores podem ser editados.
# Veja config.example.toml no repositório para a versão comentada.

[listing]
site_id = "MLB"
condition = "used"
listing_type = "premium"
available_quantity = 1
warranty = "none"
availability_days = 1
default_status = "paused"

[shipping]
free_shipping_threshold = 200.00
flex = false

[pricing]
price_ending = ".90"
import_multiplier_min = 2.5
import_multiplier_max = 3.0
undercut_strategy = "slightly_below_cheapest_similar_condition"

[description]
rare_import_line = "ITEM RARO, importado do {país}. Item de colecionador!"
closing_line = "As fotos são do item real que será enviado. Envio com embalagem protegida."
'''


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


class Config:
    """Acesso por atributo às seções do TOML: cfg.listing['site_id'] etc."""

    def __init__(self, data: dict):
        self._data = data

    def __getattr__(self, section: str) -> dict:
        try:
            return self._data[section]
        except KeyError:
            raise AttributeError(section)

    @property
    def data(self) -> dict:
        return self._data


def load_config(path: str | None = None) -> Config:
    if path is None:
        if not CONFIG_PATH.exists():
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_PATH.write_text(DEFAULT_CONFIG_TOML, encoding="utf-8")
            print(f"Config padrão criada em {CONFIG_PATH}")
        config_file = CONFIG_PATH
    else:
        config_file = Path(path).expanduser()
        if not config_file.exists():
            raise SystemExit(f"Config não encontrada: {config_file}")

    with open(config_file, "rb") as fh:
        user_data = tomllib.load(fh)
    return Config(_deep_merge(DEFAULTS, user_data))
