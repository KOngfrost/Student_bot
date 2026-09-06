def patch_vkbottle_logging() -> None:
    from vkbottle.modules import StyleAdapter

    if hasattr(StyleAdapter, "opt"):
        return

    def opt(self, exception=None, **_kwargs):
        adapter = self

        class ErrorProxy:
            def error(self, message):
                adapter.error(message, exc_info=exception)

        return ErrorProxy()

    # Осознанный monkeypatch: у StyleAdapter из vkbottle нет метода opt
    StyleAdapter.opt = opt  # type: ignore[attr-defined]
