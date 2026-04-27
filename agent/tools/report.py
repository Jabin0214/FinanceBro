"""generate_report tool — builds an HTML file and queues it for delivery."""

import logging
import os
import tempfile
from uuid import uuid4

from agent.tools._state import current_user_id, queue_file
from agent.tools.portfolio import get_cached_portfolio

logger = logging.getLogger(__name__)

DEFINITION = {
    "name": "generate_report",
    "description": (
        "生成完整的 IBKR 持仓 HTML 报表文件并发送给用户。"
        "当用户明确要求报表、报告文件、完整持仓表格时调用。"
        "与 get_portfolio 的区别：此工具发送可下载的 HTML 文件，而不是文字回复。"
    ),
    "input_schema": {"type": "object", "properties": {}, "required": []},
}


def execute(_tool_input: dict) -> str:
    from report.html_report import build_html_file

    logger.info("generate_report — building HTML")
    data = get_cached_portfolio()
    user_id = current_user_id()

    report_date = data.get("report_date", "report").replace("-", "")
    tmp_path = os.path.join(
        tempfile.gettempdir(),
        f"ibkr_report_{report_date}_{user_id}_{uuid4().hex[:8]}.html",
    )
    build_html_file(data, tmp_path)

    queue_file(
        user_id,
        path=tmp_path,
        filename=f"ibkr_report_{report_date}.html",
        caption=f"📊 IBKR 持仓报告 {data.get('report_date', '')}",
    )
    return "报表已生成，正在发送给你。"
