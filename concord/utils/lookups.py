import inspect, logging
from django.apps import apps
from django.contrib.auth.models import User


logger = logging.getLogger(__name__)


def get_all_apps(return_as="app_configs"):
    """Get all apps that are part of Concord and the app that is using it.  Returns as list of app_configs by
    default, but can also be returned as app name string by passing 'strings' to return_as."""
    relevant_apps = []
    for name, app in apps.app_configs.items():
        if hasattr(app, "get_concord_module"):
            if return_as == "app_configs":
                relevant_apps.append(app)
            elif return_as == "strings":
                relevant_apps.append(name)
    return relevant_apps


def get_all_convertible_classes():
    convertible_classes = []
    for app in get_all_apps():
        if hasattr(app, "get_all_modules"):
            modules = app.get_all_modules()
            for module in modules:
                module_classes = inspect.getmembers(module)  # returns (name, value) tuple
                for name, value in module_classes:
                    if hasattr(value, "is_convertible") and value.is_convertible:
                        convertible_classes.append(value)
    return convertible_classes + [User]  # FIXME: may need to do a proxy :/


def get_concord_class(class_name):
    for class_obj in get_all_convertible_classes():
        if class_obj.__name__ == class_name:  # may not work, may need to pass name from get_all_convertible_classes
            return class_obj


def get_all_permissioned_models():
    """Gets all non-abstract permissioned models in the system."""
    permissioned_models = []
    for app in get_all_apps():
        for model in app.get_models():
            if hasattr(model, "foundational_permission_enabled") and not model._meta.abstract:
                permissioned_models.append(model)
    return permissioned_models


def get_all_community_models():
    """Gets all non-abstract permissioned models with attr is_community equal to True."""
    community_models = []
    for model in get_all_permissioned_models():
        if hasattr(model, "is_community") and model.is_community:
            community_models.append(model)
    return community_models


def get_all_concord_models():
    models = []
    for app in get_all_apps():
        module = app.get_concord_module("concord_models")
        members = inspect.getmembers(module)  # get_members returns (name, value) tuple
        for name, value in members:
            if hasattr(value, "concord_object_mixin") and value.__name__ != "ConcordObjectMixin":
                models.append(value)
    return models


def get_all_clients():
    """Gets all clients descended from Base Client in Concord and the app using it."""
    clients = []
    for app in get_all_apps():
        client_module = app.get_concord_module("client")
        client_members = inspect.getmembers(client_module)  # get_members returns (name, value) tuple
        for name, value in client_members:
            if hasattr(value, "is_client") and value.is_client and name != "BaseClient":
                clients.append(value)
    return clients


def get_acceptance_conditions():
    """Gets all possible condition models in Concord and the app using it."""
    conditions = []
    existing_apps = get_all_apps()
    for app in existing_apps:
        for model in app.get_models():
            if hasattr(model, "is_condition") and model.is_condition and not model._meta.abstract:
                conditions.append(model)
    return conditions


def get_filter_conditions():
    """Gets all possible filter_conditions in Concord and the app using it."""
    all_conditions = []
    for app in get_all_apps():
        conditions_module = app.get_concord_module("filter_conditions")
        conditions = inspect.getmembers(conditions_module)  # get_members returns (name, value) tuple
        all_conditions += [value for (name, value) in conditions if getattr(value, 'unique_name', None)]
    return all_conditions


def get_all_conditions():
    """Gets all possible filter and acceptance condition models in Concord and the app using it."""
    return get_acceptance_conditions() + get_filter_conditions()


def get_all_state_changes():
    """Gets all possible state changes in Concord and the app using it."""
    all_state_changes = []
    for app in get_all_apps():
        state_changes_module = app.get_concord_module("state_changes")
        state_changes = inspect.getmembers(state_changes_module)  # get_members returns (name, value) tuple
        all_state_changes += [value for (name, value) in state_changes if "StateChange" in name]
    return all_state_changes


def get_all_foundational_state_changes():
    """Gets all state changes in Concord and app using it that are foundational."""
    return [change for change in get_all_state_changes() if change.is_foundational]


def get_all_templates():
    """Get all classes with TemplateLibraryObject as parent defined in template_library files, either in Concord
    or app using Concord."""

    template_classes = []

    from django.conf import settings
    for app_with_template_library in ['actions'] + settings.TEMPLATE_LIBARIES:
        app_config = apps.get_app_config(app_with_template_library)
        library_module = app_config.get_concord_module("template_library")
        module_classes = inspect.getmembers(library_module)
        for (module_class_name, module_class) in module_classes:
            if hasattr(module_class, "is_template_object") and module_class.is_template_object and \
                    not inspect.isabstract(module_class):
                template_classes.append(module_class)

    return template_classes


def process_field_type(field):
    """Helper method to inspect field and return appropriate type."""
    if field.name in ["actor", "commentor", "author"]:
        return "ActorField"
    if field.name in ["foundational_permission_enabled", "governing_permission_enabled"]:
        return
    field_type_map = {
        "PositiveIntegerField": "IntegerField",
        "BooleanField": "BooleanField",
        "CharField": "CharField",
        "RoleListField": "RoleListField",
        "ActorListField": "ActorListField",
        "GenericForeignKey": "ObjectField",
        "ForeignKey": "ObjectField"
    }
    return field_type_map.get(field.__class__.__name__)


def get_all_dependent_fields():
    """Goes through all PermissionedModels, plus Action, and gets a list of fields.
    TODO: also get their type, for use on front-end validation?"""

    dependent_field_dict = {}
    from concord.actions.models import Action
    models = [Action] + get_all_permissioned_models()

    for model in models:
        field_list = []
        for field in model._meta.get_fields():
            if "content_type" in field.name or "object_id" in field.name:
                continue
            field_type = process_field_type(field)
            if field_type:
                field_list.append({"value": field.name, "text": field.name, "type": field_type})
        dependent_field_dict.update({model.__name__.lower(): field_list})

    return dependent_field_dict


def get_state_changes_for_app(app_name):
    """Given an app name, gets state_changes as list of state change objects."""
    app_config = apps.get_app_config(app_name)
    state_changes_module = app_config.get_concord_module("state_changes")
    state_changes = inspect.getmembers(state_changes_module)  # get_members returns (name, value) tuple
    return [value for (name, value) in state_changes if "StateChange" in name]


def get_state_change_object(state_change_name):
    """Given a full name string, gets the state change object."""

    name_elements = state_change_name.split(".")

    if name_elements[0] == "concord":  # format: concord.app.state_changes.state_change_object
        app_name = name_elements[1]
        change_name = name_elements[3]
    else:                              # format: app_name.state_changes.state_change_object
        app_name = name_elements[0]
        change_name = name_elements[2]

    for state_change_object in get_state_changes_for_app(app_name):
        if state_change_object.__name__ == change_name:
            return state_change_object


def get_state_changes_settable_on_model(model_class):
    """Gets all state changes a given model can be set on.  If state_changes is not passed in, checks against
    all possible state_changes."""
    state_changes = get_all_state_changes()
    matching_state_changes = []

    for change in state_changes:
        if hasattr(change, "can_set_on_model") and change.can_set_on_model(model_class.__name__) \
                and change.__name__ != "BaseStateChange":
            matching_state_changes.append(change)

    return matching_state_changes


def get_default_permissions():
    """Get default permissions for permissioned models."""
    default_permissions = {}
    for app in get_all_apps():
        default_permissions_module = app.get_concord_module("default_permissions")
        members = inspect.getmembers(default_permissions_module)
        if members:
            for name, value in members:
                if name == "DEFAULT_PERMISSIONS":
                    for model_type, permissions in value.items():
                        if model_type not in default_permissions:
                            default_permissions[model_type] = []
                        default_permissions[model_type] += permissions
    return default_permissions
