import json
import os
import urllib.error
import urllib.request


class OzonDeliveryError(RuntimeError):
    pass


class OzonDeliveryClient:
    BASE_URL = "https://api-seller.ozon.ru"

    def __init__(self, token=None):
        self.token = token or os.getenv("OZON_DELIVERY_TOKEN", "").strip()

    @property
    def configured(self):
        return bool(self.token)

    def request(self, path, payload):
        if not self.token:
            raise OzonDeliveryError(
                "OZON_DELIVERY_TOKEN is not configured"
            )

        url = self.BASE_URL + path
        body = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
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
