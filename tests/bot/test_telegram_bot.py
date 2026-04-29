from bot import telegram_bot


class _FakeBuilder:
    def __init__(self, app):
        self.app = app
        self.token_value = None

    def token(self, token):
        self.token_value = token
        return self

    def build(self):
        self.app.token_value = self.token_value
        return self.app


class _FakeApplication:
    def __init__(self):
        self.handlers = []
        self.token_value = None

    @classmethod
    def builder(cls):
        app = cls()
        return _FakeBuilder(app)

    def add_handler(self, handler):
        self.handlers.append(handler)


def test_build_app_wires_token_handlers_and_jobs(monkeypatch):
    jobs = []
    monkeypatch.setattr(telegram_bot, "Application", _FakeApplication)
    monkeypatch.setattr(telegram_bot, "TELEGRAM_BOT_TOKEN", "telegram-token")
    monkeypatch.setattr(telegram_bot, "setup_jobs", lambda app: jobs.append(app))

    app = telegram_bot.build_app()

    assert app.token_value == "telegram-token"
    assert len(app.handlers) == 9
    assert jobs == [app]
