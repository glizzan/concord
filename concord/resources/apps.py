from django.apps import AppConfig


class ResourcesConfig(AppConfig):
    name = 'concord.resources'
    verbose_name = "Resources"

    def get_state_changes_module(cls):
        import importlib
        return importlib.import_module(".resources.state_changes", package="concord")
