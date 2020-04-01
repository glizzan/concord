from django.apps import AppConfig


class ConditionalsConfig(AppConfig):
    name = 'concord.conditionals'
    verbose_name = "Conditionals"

    def get_state_changes_module(cls):
        import importlib
        return importlib.import_module(".conditionals.state_changes", package="concord")
