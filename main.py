import logging
from bot.telegram_bot import build_app

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)

if __name__ == "__main__":
    app = build_app()
    print("🤖 FinanceBro 启动中...")
    app.run_polling(drop_pending_updates=True)
