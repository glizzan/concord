import importlib

from django.apps import AppConfig


class ConditionalsConfig(AppConfig):
    name = 'concord.conditionals'
    verbose_name = "Conditionals"

    def get_concord_module(self, module_name):
        """Helper method to let utils easily access specific files."""
        return importlib.import_module(".conditionals." + module_name, package="concord")
