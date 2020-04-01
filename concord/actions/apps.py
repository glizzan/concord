from django.apps import AppConfig


class ActionsConfig(AppConfig):
    name = 'concord.actions'
    verbose_name = "Actions"

    def get_state_changes_module(cls):
        import importlib
        return importlib.import_module(".actions.state_changes", package="concord")
