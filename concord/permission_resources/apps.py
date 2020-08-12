"""AppConfig for Permission Resource."""

import importlib

from django.apps import AppConfig


class PermissionResourcesConfig(AppConfig):
    """AppConfig for Permission Resource."""
    name = 'concord.permission_resources'

    def get_concord_module(self, module_name):
        """Helper method to let utils easily access specific files."""
        return importlib.import_module(".permission_resources." + module_name, package="concord")
