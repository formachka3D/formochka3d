import json
import os
import time
import urllib.error
import urllib.request
import requests
from urllib.parse import urljoin


class OzonDeliveryError(RuntimeError):
    pass


class OzonDeliveryClient:
    BASE_URL = "https://api-delivery.ozon.ru"
    TOKEN_URL = "https://xapi.ozon.ru/oauth/token"
    DEFAULT_SCOPE = ["delivery-api.all"]

    def __init__(self, token=None, client_id=None, client_secret=None):
        self.token = (token or os.getenv("OZON_DELIVERY_TOKEN", "")).strip()
        self.client_id = (
            client_id
            or os.getenv("OZON_DELIVERY_CLIENT_ID", "").strip()
        )
        self.client_secret = (
            client_secret
            or os.getenv("OZON_DELIVERY_CLIENT_SECRET", "").strip()
        )
        self._token_expires_at = 0

    @property
    def configured(self):
        return bool(
            self.token
            or (self.client_id and self.client_secret)
        )

    @property
    def auth_mode(self):
        if self.token:
            return "oauth_bearer"
        if self.client_id and self.client_secret:
            return "oauth_client_credentials"
        return "not_configured"

    def _get_access_token(self):
        if self.token and (
            not self._token_expires_at
            or time.time() < self._token_expires_at - 30
        ):
            return self.token

        if not (self.client_id and self.client_secret):
            raise OzonDeliveryError(
                "Ozon Delivery credentials are not configured. "
                "Set OZON_DELIVERY_CLIENT_ID and "
                "OZON_DELIVERY_CLIENT_SECRET."
            )

        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
            "scope": self.DEFAULT_SCOPE,
        }
        body = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(
            self.TOKEN_URL,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read().decode("utf-8")
                data = json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise OzonDeliveryError(
                f"Ozon OAuth returned HTTP {exc.code}: {raw}"
            ) from exc
        except urllib.error.URLError as exc:
            raise OzonDeliveryError(
                f"Could not connect to Ozon OAuth: {exc.reason}"
            ) from exc

        token = (data.get("access_token") or "").strip()
        if not token:
            raise OzonDeliveryError(
                "Ozon OAuth response did not contain access_token."
            )

        expires_in = data.get("expires_in")
        try:
            expires_value = float(expires_in)
            now = time.time()
            # Ozon may return an absolute Unix timestamp.
            self._token_expires_at = (
                expires_value
                if expires_value > now
                else now + expires_value
            )
        except (TypeError, ValueError):
            self._token_expires_at = time.time() + 900

        self.token = token
        return token

    def _headers(self):
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self._get_access_token()}",
        }

    def request(self, path, payload):
        url = self.BASE_URL.rstrip("/") + path
        headers = self._headers()
        session = requests.Session()
        for _ in range(4):
            try:
                response = session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=25,
                    allow_redirects=False,
                )
            except requests.RequestException as exc:
                raise OzonDeliveryError(
                    f"Could not connect to Ozon Delivery API: {exc}"
                ) from exc

            if response.status_code in (302, 307):
                location = response.headers.get("Location")
                if not location:
                    raise OzonDeliveryError(
                        f"Ozon Delivery redirect HTTP {response.status_code} had no Location"
                    )
                url = urljoin(url, location)
                continue

            if response.status_code >= 400:
                raise OzonDeliveryError(
                    f"Ozon Delivery API returned HTTP {response.status_code}: {response.text[:1500]}"
                )
            if not response.content:
                return {}
            try:
                return response.json()
            except ValueError as exc:
                raise OzonDeliveryError(
                    "Ozon Delivery API returned invalid JSON"
                ) from exc

        raise OzonDeliveryError("Too many Ozon Delivery redirects")

    def check_auth(self):
        self._get_access_token()
        return True

    def check_delivery(self, payload):
        return self.request("/v1/delivery/check", payload)

    def checkout(self, payload):
        return self.request("/v2/delivery/checkout", payload)

    def list_points(self, payload):
        return self.request("/v1/delivery-point/list", payload)

    def point_info(self, payload):
        return self.request("/v1/delivery-point/info", payload)

    def create_order(self, payload):
        return self.request("/v2/order/create", payload)

    def cancel_order(self, payload):
        return self.request("/v1/order/cancel", payload)


    def all_points(self, max_pages=50, limit=100):
        """Return active delivery point details, paginated and safe for UI selection."""
        points = []
        cursor = None
        seen = set()
        for _ in range(max_pages):
            page = self.list_points({"pagination": {"cursor": cursor, "limit": limit}})
            rows = page.get("delivery_points") or []
            ids = [r.get("delivery_point_id") for r in rows if isinstance(r, dict) and isinstance(r.get("delivery_point_id"), int)]
            if ids:
                info = self.point_info({"delivery_point_ids": ids})
                for p in info.get("delivery_points") or []:
                    if isinstance(p, dict) and p.get("is_active", True):
                        points.append(p)
            nxt = page.get("next_cursor")
            if not nxt or nxt in seen:
                break
            seen.add(nxt)
            cursor = nxt
        return points
