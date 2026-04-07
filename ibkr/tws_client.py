"""
IBKR IB Gateway 连接管理器 — Phase 4

架构：
  ib_insync 的 IB 对象运行在独立的后台 asyncio 线程中，
  避免与 Telegram Bot 的主事件循环产生冲突。
  所有工具函数通过 run_coroutine_threadsafe() 以同步方式调用协程。

三种失败降级场景：
  1. IB Gateway 未启动 / 无法连接 → TWSNotConnectedError，工具层返回友好提示
  2. 延迟数据（无实时订阅）       → 正常返回，结果标注 data_type="delayed"
  3. 无期权数据订阅（Greeks 为空）→ 返回基础报价，标注 greeks_available=False

配置（.env）：
  IBKR_TWS_HOST      默认 127.0.0.1
  IBKR_TWS_PORT      默认 4001（实盘），模拟账户用 4002
  IBKR_TWS_CLIENT_ID 默认 10
"""

import asyncio
import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class TWSNotConnectedError(Exception):
    """IB Gateway 未连接或连接失败时抛出。"""
    pass


class TWSClient:
    """
    单例 IB Gateway 连接管理器。

    IB 对象在独立的后台线程（ib-insync-loop）中创建和使用，
    主线程/工具线程通过 run() 方法以同步方式调用异步操作。
    """

    _instance: Optional["TWSClient"] = None
    _creation_lock = threading.Lock()

    def __new__(cls):
        with cls._creation_lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst._initialized = False
                cls._instance = inst
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self._ib = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._connect_lock = threading.Lock()
        self._ready = threading.Event()

        t = threading.Thread(
            target=self._start_loop,
            name="ib-insync-loop",
            daemon=True,
        )
        t.start()

        if not self._ready.wait(timeout=10):
            raise RuntimeError("ib_insync 后台事件循环启动超时（10s）")

        logger.info("TWSClient 初始化完成")

    def _start_loop(self):
        """在后台线程中创建事件循环并初始化 IB 对象。"""
        from ib_insync import IB, util
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._ib = IB()
        self._ready.set()
        logger.info("ib_insync 后台事件循环已启动")
        self._loop.run_forever()

    # ── 连接管理 ─────────────────────────────────────────────────────────────

    def connect(self, host: str, port: int, client_id: int) -> None:
        """连接到 IB Gateway（已连接则跳过）。"""
        with self._connect_lock:
            if self._ib.isConnected():
                return
            logger.info("正在连接 IB Gateway %s:%d clientId=%d ...", host, port, client_id)
            future = asyncio.run_coroutine_threadsafe(
                self._ib.connectAsync(host, port, clientId=client_id, timeout=15),
                self._loop,
            )
            try:
                future.result(timeout=20)
            except Exception as e:
                raise TWSNotConnectedError(
                    f"无法连接 IB Gateway（{host}:{port}）：{e}\n"
                    "请确认 IB Gateway 已启动并开启 API 访问（Settings → API → Enable Socket Clients）"
                ) from e

            # 默认请求延迟数据作为 fallback，有实时订阅时 IBKR 会自动升级
            asyncio.run_coroutine_threadsafe(
                self._set_market_data_type(), self._loop
            ).result(timeout=5)

            logger.info("IB Gateway 连接成功")

    async def _set_market_data_type(self):
        # 3 = 延迟数据（免费）；有实时订阅时自动使用实时数据
        self._ib.reqMarketDataType(3)

    def ensure_connected(self) -> None:
        """确保已连接，未连接时自动重连。"""
        from config import IBKR_TWS_HOST, IBKR_TWS_PORT, IBKR_TWS_CLIENT_ID
        if not self._ib.isConnected():
            self.connect(IBKR_TWS_HOST, IBKR_TWS_PORT, IBKR_TWS_CLIENT_ID)

    def is_connected(self) -> bool:
        return self._ib is not None and self._ib.isConnected()

    def disconnect(self) -> None:
        if self._ib and self._ib.isConnected():
            self._ib.disconnect()
            logger.info("IB Gateway 已断开")

    # ── 协程执行器 ────────────────────────────────────────────────────────────

    def run(self, coro, timeout: float = 90):
        """
        在后台事件循环中运行协程，同步等待结果。
        调用前会自动确保连接有效。
        """
        self.ensure_connected()
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    @property
    def ib(self):
        """直接访问 ib_insync IB 对象（仅在后台线程内使用）。"""
        return self._ib


# ── 模块级单例入口 ────────────────────────────────────────────────────────────

_singleton: Optional[TWSClient] = None
_singleton_lock = threading.Lock()


def get_tws_client() -> TWSClient:
    """获取 TWSClient 单例，懒初始化。"""
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = TWSClient()
    return _singleton
