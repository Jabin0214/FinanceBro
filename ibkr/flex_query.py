"""
IBKR Flex Query 报表获取

使用前需要在 IBKR Account Management 配置：
1. Reports → Flex Queries → Create new query
2. 勾选需要的字段：Open Positions、Cash Report、Account Information
3. 记录 Query ID 和 Flex Web Service Token
"""

import time
import logging
import requests
import xml.etree.ElementTree as ET
from config import IBKR_FLEX_TOKEN, IBKR_FLEX_QUERY_ID
from ibkr.parser import parse_flex_xml

logger = logging.getLogger(__name__)

BASE_URL = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService"
MAX_RETRIES = 5
RETRY_INTERVAL = 3  # seconds


def fetch_flex_report() -> dict:
    """
    从 IBKR 获取 Flex Query 报表，返回结构化数据。
    分两步：先发请求取得 reference code，再拿报告。
    """
    reference_code = _request_report()
    xml_content = _download_report(reference_code)
    return parse_flex_xml(xml_content)


def _request_report() -> str:
    """第一步：触发报表生成，返回 reference code。"""
    logger.info("正在请求 IBKR Flex Query 报表...")
    resp = requests.get(
        f"{BASE_URL}/SendRequest",
        params={"t": IBKR_FLEX_TOKEN, "q": IBKR_FLEX_QUERY_ID, "v": "3"},
        timeout=30,
    )
    resp.raise_for_status()

    root = ET.fromstring(resp.text)
    status = root.findtext(".//Status")
    if status != "Success":
        error_msg = root.findtext(".//ErrorMessage") or resp.text
        raise RuntimeError(f"Flex Query 请求失败：{error_msg}")

    code = root.findtext(".//ReferenceCode")
    logger.info(f"获取到 reference code: {code}")
    return code


def _download_report(reference_code: str) -> str:
    """第二步：轮询下载报表（IBKR 需要几秒生成）。"""
    for attempt in range(1, MAX_RETRIES + 1):
        time.sleep(RETRY_INTERVAL)
        logger.info(f"下载报表，第 {attempt} 次尝试...")

        resp = requests.get(
            f"{BASE_URL}/GetStatement",
            params={"q": reference_code, "t": IBKR_FLEX_TOKEN, "v": "3"},
            timeout=30,
        )
        resp.raise_for_status()

        # 还没准备好时会返回 Status = Warn
        if "<Status>Warn</Status>" in resp.text:
            logger.info("报表尚未生成，等待中...")
            continue

        try:
            root = ET.fromstring(resp.text)
            status = root.findtext(".//Status")
            if status and status != "Success":
                error_msg = root.findtext(".//ErrorMessage") or resp.text
                raise RuntimeError(f"Flex Query 下载失败：{error_msg}")
        except ET.ParseError:
            # 正常报表 XML 不一定带 Status，无法解析状态时交给后续 parser 处理
            pass

        return resp.text

    raise RuntimeError("IBKR 报表下载超时，请稍后重试")
