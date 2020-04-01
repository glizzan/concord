from django.apps import AppConfig


class CommunitiesConfig(AppConfig):
    name = 'concord.communities'
    verbose_name = "Communities"

    def get_state_changes_module(cls):
        import importlib
        return importlib.import_module(".communities.state_changes", package="concord")

