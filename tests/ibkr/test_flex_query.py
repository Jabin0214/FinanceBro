import pytest
import requests

from ibkr import flex_query


class _Response:
    status_code = 403
    url = "https://example.test?t=secret-token"

    def raise_for_status(self):
        raise requests.HTTPError(f"403 Client Error: Forbidden for url: {self.url}")


def test_raise_for_status_hides_token_bearing_url():
    with pytest.raises(RuntimeError) as exc:
        flex_query._raise_for_status(_Response(), "请求")

    message = str(exc.value)
    assert "HTTP 403" in message
    assert "secret-token" not in message
    assert "https://example.test" not in message
