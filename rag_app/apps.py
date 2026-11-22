from django.apps import AppConfig


class RagAppConfig(AppConfig):
    name = 'rag_app'

    def ready(self):
        from . import signals  # noqa: F401
