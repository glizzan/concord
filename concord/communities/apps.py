"""AppConfig for Community app."""

from concord.actions.apps import ConcordAppConfig


class CommunitiesConfig(ConcordAppConfig):
    """AppConfig for Community app."""
    name = 'concord.communities'
    verbose_name = "Communities"
