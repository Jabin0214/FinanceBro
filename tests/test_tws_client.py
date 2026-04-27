import threading

import ibkr.tws_client as tws_client
from ibkr.tws_client import TWSClient


def test_tws_client_connect_uses_readonly_api(monkeypatch):
    class FakeIB:
        def __init__(self):
            self.connect_kwargs = None

        def isConnected(self):
            return False

        def connectAsync(self, host, port, **kwargs):
            self.connect_kwargs = kwargs
            return object()

        def reqMarketDataType(self, market_data_type):
            self.market_data_type = market_data_type

    class FakeFuture:
        def result(self, timeout):
            return None

    def fake_run_coroutine_threadsafe(coro, loop):
        return FakeFuture()

    fake_ib = FakeIB()
    client = object.__new__(TWSClient)
    client._ib = fake_ib
    client._loop = object()
    client._connect_lock = threading.Lock()
    client._set_market_data_type = lambda: object()

    monkeypatch.setattr(
        tws_client.asyncio,
        "run_coroutine_threadsafe",
        fake_run_coroutine_threadsafe,
    )

    client.connect("ib-gateway", 4003, 10)

    assert fake_ib.connect_kwargs["clientId"] == 10
    assert fake_ib.connect_kwargs["timeout"] == 15
    assert fake_ib.connect_kwargs["readonly"] is True
