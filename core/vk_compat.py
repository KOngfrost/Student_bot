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

    StyleAdapter.opt = opt