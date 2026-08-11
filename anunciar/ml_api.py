"""Cliente HTTP da API do Mercado Livre.

Retry em 5xx (3 tentativas com backoff), refresh + retry único em 401.
"""

import json
import mimetypes
import time
from pathlib import Path

import requests

from . import tokens as tk

BASE = "https://api.mercadolibre.com"


class MLError(Exception):
    def __init__(self, message: str, status: int | None = None, body: dict | None = None):
        super().__init__(message)
        self.status = status
        self.body = body or {}

    def causes(self) -> list:
        return self.body.get("cause") or []

    def pretty(self) -> str:
        lines = [str(self)]
        if self.body:
            lines.append(json.dumps(self.body, indent=2, ensure_ascii=False))
        return "\n".join(lines)


class MLClient:
    def __init__(self, site_id: str = "MLB"):
        self.site_id = site_id
        self.session = requests.Session()

    # ------------------------------------------------------------------ core

    def request(
        self,
        method: str,
        path: str,
        *,
        auth: bool = True,
        retries: int = 3,
        **kwargs,
    ) -> requests.Response:
        url = path if path.startswith("http") else BASE + path
        refreshed = False
        attempt = 0
        while True:
            headers = dict(kwargs.pop("headers", {}) or {})
            if auth:
                headers["Authorization"] = f"Bearer {tk.get_access_token()}"
            resp = self.session.request(
                method, url, headers=headers, timeout=60, **{**kwargs}
            )
            if resp.status_code == 401 and auth and not refreshed:
                refreshed = True
                tk.refresh_tokens()
                continue
            if resp.status_code >= 500 and attempt < retries - 1:
                attempt += 1
                time.sleep(2**attempt)
                continue
            return resp

    def _json(self, resp: requests.Response, context: str) -> dict | list:
        try:
            body = resp.json()
        except ValueError:
            body = {"raw": resp.text}
        if resp.status_code >= 400:
            raise MLError(
                f"{context}: HTTP {resp.status_code}",
                status=resp.status_code,
                body=body if isinstance(body, dict) else {"raw": body},
            )
        return body

    def get(self, path: str, *, auth: bool = True, **kwargs):
        return self._json(self.request("GET", path, auth=auth, **kwargs), f"GET {path}")

    def post(self, path: str, payload: dict, **kwargs):
        return self._json(
            self.request("POST", path, json=payload, **kwargs), f"POST {path}"
        )

    def put(self, path: str, payload: dict, **kwargs):
        return self._json(
            self.request("PUT", path, json=payload, **kwargs), f"PUT {path}"
        )

    # ------------------------------------------------------------- endpoints

    def me(self) -> dict:
        return self.get("/users/me")

    def domain_discovery(self, query: str, limit: int = 3) -> list:
        q = requests.utils.quote(query)
        return self.get(
            f"/sites/{self.site_id}/domain_discovery/search?q={q}&limit={limit}"
        )

    def site_categories(self) -> list:
        return self.get(f"/sites/{self.site_id}/categories")

    def category(self, category_id: str) -> dict:
        return self.get(f"/categories/{category_id}")

    def category_attributes(self, category_id: str) -> list:
        return self.get(f"/categories/{category_id}/attributes")

    def category_sale_terms(self, category_id: str) -> list:
        return self.get(f"/categories/{category_id}/sale_terms")

    def listing_types(self) -> list:
        return self.get(f"/sites/{self.site_id}/listing_types")

    def upload_picture(self, path: Path) -> dict:
        mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
        with open(path, "rb") as fh:
            resp = self.request(
                "POST",
                "/pictures/items/upload",
                files={"file": (path.name, fh, mime)},
            )
        return self._json(resp, f"upload {path.name}")

    def create_item(self, payload: dict) -> dict:
        return self.post("/items", payload)

    def set_description(self, item_id: str, text: str) -> dict:
        return self.post(f"/items/{item_id}/description", {"plain_text": text})

    def update_item(self, item_id: str, payload: dict) -> dict:
        return self.put(f"/items/{item_id}", payload)
