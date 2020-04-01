from django.apps import AppConfig


class PermissionResourcesConfig(AppConfig):
    name = 'concord.permission_resources'

    def get_state_changes_module(cls):
        import importlib
        return importlib.import_module(".permission_resources.state_changes", package="concord")

