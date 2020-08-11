import importlib

from django.apps import AppConfig


class ResourcesConfig(AppConfig):
    name = 'concord.resources'
    verbose_name = "Resources"

    def get_concord_module(self, module_name):
        """Helper method to let utils easily access specific files."""
        return importlib.import_module(".resources." + module_name, package="concord")
