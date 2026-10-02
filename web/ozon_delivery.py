import json
import os
import urllib.error
import urllib.request


class OzonDeliveryError(RuntimeError):
    pass


class OzonDeliveryClient:
    BASE_URL = "https://api-seller.ozon.ru"

    def __init__(self, token=None, client_id=None, api_key=None):
        self.token = token or os.getenv("OZON_DELIVERY_TOKEN", "").strip()
        self.client_id = (
            client_id
            or os.getenv("OZON_CLIENT_ID", "").strip()
        )
        self.api_key = (
            api_key
            or os.getenv("OZON_API_KEY", "").strip()
        )

    @property
    def configured(self):
        return bool(
            self.token
            or (self.client_id and self.api_key)
        )

    @property
    def auth_mode(self):
        if self.client_id and self.api_key:
            return "seller_api"
        if self.token:
            return "oauth_bearer"
        return "not_configured"

    def _headers(self):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        if self.client_id and self.api_key:
            headers["Client-Id"] = self.client_id
            headers["Api-Key"] = self.api_key
            return headers

        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
            return headers

        raise OzonDeliveryError(
            "Ozon credentials are not configured. "
            "Set OZON_CLIENT_ID + OZON_API_KEY "
            "or OZON_DELIVERY_TOKEN."
        )

    def request(self, path, payload):
        url = self.BASE_URL + path
        body = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers=self._headers(),
        )

        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise OzonDeliveryError(
                f"Ozon Delivery API returned HTTP {exc.code}: {raw}"
            ) from exc
        except urllib.error.URLError as exc:
            raise OzonDeliveryError(
                f"Could not connect to Ozon Delivery API: {exc.reason}"
            ) from exc

    def check_delivery(self, payload):
        return self.request("/v1/delivery/check", payload)

    def checkout(self, payload):
        return self.request("/v2/delivery/checkout", payload)

    def list_points(self, payload):
        return self.request("/v1/delivery/point/list", payload)

    def point_info(self, payload):
        return self.request("/v1/delivery/point/info", payload)

    def create_order(self, payload):
        return self.request("/v2/order/create", payload)

    def cancel_order(self, payload):
        return self.request("/v1/order/cancel", payload)
