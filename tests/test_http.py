import pytest
import requests

import app


class Resp:
    def __init__(self, text, content_type="text/html"):
        self.text = text
        self.content = text.encode()
        self.headers = {"Content-Type": content_type}
        self.status_code = 200

    def raise_for_status(self):
        pass


def test_json_with_html_content_type_is_not_blocked():
    assert not app._is_blocked_response(Resp('{"config": {}, "periods": []}'))


@pytest.mark.parametrize("body", ["<html><body>blocked</body></html>",
                                  "<!DOCTYPE html><p>x</p>"])
def test_html_is_blocked(body):
    assert app._is_blocked_response(Resp(body))


def test_get_json_retries_then_succeeds(monkeypatch):
    calls = []

    def fake_get(url, **kw):
        calls.append(url)
        return Resp("<html>blocked</html>" if len(calls) < 3 else '{"periods": []}')

    monkeypatch.setattr(app.requests, "get", fake_get)
    assert app._http_get_json("http://x", retries=3, delay=0) == {"periods": []}
    assert len(calls) == 3


def test_get_json_fails_after_retries(monkeypatch):
    calls = []

    def fake_get(url, **kw):
        calls.append(url)
        raise requests.ConnectionError("down")

    monkeypatch.setattr(app.requests, "get", fake_get)
    with pytest.raises(RuntimeError):
        app._http_get_json("http://x", retries=3, delay=0)
    assert len(calls) == 3
