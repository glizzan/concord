"""AppConfig for resources."""

from concord.actions.apps import ConcordAppConfig


class ResourcesConfig(ConcordAppConfig):
    """AppConfig for resources."""
    name = 'concord.resources'
    verbose_name = "Resources"
