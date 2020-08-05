from django.apps import AppConfig


class ActionsConfig(AppConfig):
    """AppConfig for Actions modeule."""
    name = 'concord.actions'
    verbose_name = "Actions"

    def get_state_changes_module(cls):
        """Helper method used elsewhere to easily access state changes."""
        import importlib
        return importlib.import_module(".actions.state_changes", package="concord")
