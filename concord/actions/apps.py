import importlib

from django.apps import AppConfig


class ConcordAppConfig(AppConfig):
    """BaseConfig module for other Concord apps to descend from."""
    is_core = False

    def get_concord_module(self, module_name):
        """Loads a module from the app or, if module not found, returns None. Core modules from the
        Concord library must be treated differently than modules defined in the implementation."""
        try:
            if "concord." in self.name:
                name = self.name.split(".")[1]
                return importlib.import_module("." + name + "." + module_name, package="concord")
            else:
                return importlib.import_module(self.name + "." + module_name)
        except ModuleNotFoundError as error:
            return None

    def get_all_modules(self):
        modules = []
        for module_name in ["client", "customfields", "models", "state_changes", "utils", "filter_conditions"]:
            module = self.get_concord_module(module_name)
            if module:
                modules.append(module)
        return modules


class ActionsConfig(ConcordAppConfig):
    """AppConfig for Actions modeule."""
    name = 'concord.actions'
    verbose_name = "Actions"
