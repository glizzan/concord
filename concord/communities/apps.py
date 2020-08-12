"""AppConfig for Community app."""

import importlib

from django.apps import AppConfig


class CommunitiesConfig(AppConfig):
    """AppConfig for Community app."""
    name = 'concord.communities'
    verbose_name = "Communities"

    def get_concord_module(self, module_name):
        """Helper method to let utils easily access specific files."""
        return importlib.import_module(".communities." + module_name, package="concord")
