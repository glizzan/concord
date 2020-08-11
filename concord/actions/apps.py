import importlib

from django.apps import AppConfig


class ActionsConfig(AppConfig):
    """AppConfig for Actions modeule."""
    name = 'concord.actions'
    verbose_name = "Actions"

    def get_concord_module(self, module_name):
        """Helper method to let utils easily access specific files."""
        return importlib.import_module(".actions." + module_name, package="concord")
