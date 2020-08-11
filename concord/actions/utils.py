import json, inspect, random, logging, importlib
from django.apps import apps


logger = logging.getLogger(__name__)


######################
### Lookup Helpers ###
######################


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


def get_state_changes_settable_on_model(model_name, state_changes=None):
    """Gets all state changes a given model can be set on.  If state_changes is not passed in, checks against
    all possible state_changes."""
    state_changes = state_changes if state_changes else get_all_state_changes()
    matching_state_changes = []
    for change in state_changes:
        if hasattr(change, "can_set_on_model") and change.can_set_on_model(model_name) \
                and change.__name__ != "BaseStateChange":
            matching_state_changes.append(change)
    return matching_state_changes


def get_parent_state_changes(model_class):
    """Gets state changes for parents of the given model class and, recurisvely, for all ancestors."""
    state_changes = []
    for parent in model_class.__bases__:
        if hasattr(parent, "get_settable_state_changes"):   # only checks parents which are PermissionedModels
            state_changes += get_state_changes_for_app(parent._meta.app_label)
        state_changes += get_parent_state_changes(parent)
    return state_changes


def get_state_changes_settable_on_model_and_parents(model_class):
    """When given a model, returns all state changes that apply to the model, include state changes belonging to
    parent models."""

    state_changes = get_state_changes_for_app(model_class._meta.app_label)
    state_changes += get_parent_state_changes(model_class)
    state_changes = list(set(state_changes))

    return get_state_changes_settable_on_model(model_class.__name__, state_changes=state_changes)


class Attributes(object):
    """Hack to allow nested attributes on Changes."""
    ...


class Changes(object):
    """Helper object which lets developers easily access change types."""

    def __init__(self):

        for change in get_all_state_changes():

            tokens = change.get_change_type().split(".")
            app_name = (tokens[1] if "concord" in tokens else tokens[0]).capitalize()
            change_name = (tokens[3] if "concord" in tokens else tokens[2]).replace("StateChange", "")

            app_name = "Permissions" if app_name == "Permission_resources" else app_name

            if not hasattr(self, app_name):
                setattr(self, app_name, Attributes())

            app_attr = getattr(self, app_name)
            setattr(app_attr, change_name, change.get_change_type())


class Client(object):
    """Helper object which lets developers easily access all clients at once.

    If supplied with actor and/or target, will instantiate clients with that actor and target.

    limit_to is a list of client names, if supplied actors and targets will only be supplied to 
    the specified clients.    
    """

    community_client_override = None

    def __init__(self, actor=None, target=None, limit_to=None):

        self.client_names = []

        for client_class in get_all_clients():

            client_attribute_name = client_class.__name__.replace("Client", "")

            if not limit_to or client_attribute_name in limit_to:
                client_instance = client_class(actor=actor, target=target)
            else:
                client_instance = client_class()

            if client_attribute_name == "Community":       # Helps deal with multiple community groups
                client_attribute_name = "Concord" + client_attribute_name

            setattr(self, client_attribute_name, client_instance)
            self.client_names.append(client_attribute_name)

    def get_clients(self):
        return [getattr(self, client_name) for client_name in self.client_names]

    def update_actor_on_all(self, actor):
        for client in self.get_clients():
            client.set_actor(actor=actor)

    def update_target_on_all(self, target):
        for client in self.get_clients():
            client.set_target(target=target)

    @property
    def Community(self):
        """Projects that use Concord may create a new model and client, descending from the Community model and
        CommunityClient. To handle this scenario, we look for Clients with an attribute community_model and, if
        something other than the CommunityClient exists, we use that. Users can override this behavior by 
        explicitly setting community_client_override to whatever client they want to use."""

        if self.community_client_override:
            return self.community_client_override
        
        community_clients = [client for client in self.get_clients() if hasattr(client, "community_model")]

        if len(community_clients) == 1:
            return community_clients[0]

        for client in community_clients:
            if client.__class__.__name__ != "CommunityClient":
                return client


############################
### Replace Fields Utils ###
############################


def replacer(key, value, context):
    """Given the value provided by mock_action, looks for fields that need replacing by finding strings with the right
    format, those that begin and end with {{ }}.  Uses information in context object to replace those fields. In
    the special case of finding something referencing nested_trigger_action (always(?) in the context of a 
    condition being set) it replaces nested_trigger_action with trigger_action."""

    logging.debug(f"Replacing {key} with placeholder value: {value}")

    if type(value) == str and value[0:2] == "{{" and value[-2:] == "}}":

        command = value.replace("{{", "").replace("}}", "").strip()
        tokens = command.split(".")

        if tokens[0] == "supplied_fields":
            """Always two tokens long, with format supplied_fields.field_name."""
            logging.debug(f"Supplied Fields: Replacing {key} {value} with {context.supplied_fields[tokens[1]]}")
            return context.supplied_fields[tokens[1]]

        if tokens[0] == "trigger_action":
            """Variable length - can be just the trigger action itself, an immediate attribute, or the
            attribute of an attribute, for example trigger_action.change.role_name."""

            if len(tokens) == 1:
                new_value = context.trigger_action

            if len(tokens) == 2:
                new_value = getattr(context.trigger_action, tokens[1])
            
            if len(tokens) == 3:
                intermediate = getattr(context.trigger_action, tokens[1])
                new_value = getattr(intermediate, tokens[2])
            
            logging.debug(f"trigger_action: Replacing {key} {value} with {new_value}")
            return new_value

        if tokens[0] == "previous":
            """Always three or four tokens long, with format previous.position.action_or_result, for example
            previous.0.action, or previous.position.action_or_result.attribute, for
            example previous.1.result.pk """

            position = int(tokens[1])
            action, result = context.get_action_and_result_for_position(position)
            source = action if tokens[2] == "action" else result
            new_value = getattr(source, tokens[3]) if len(tokens) == 4 else source

            logging.debug(f"previous: Replacing {key} {value} with {new_value}")
            return new_value

        if tokens[0] == "nested_trigger_action":
            """In this special case, we merely replace nested_trigger_action with trigger_action
            so that when this object is passed through replace_fields again, later, it will
            *then* replace with *that* trigger_action.  (Yes, it's a HACK, don't judge me.)"""
            logging.debug(f"nested_trigger_action: Replacing {key} {value} with 'trigger_action'")
            return value.replace("nested_trigger_action", "trigger_action")

    return ...


def replace_fields(*, action_to_change, mock_action, context):
    """Takes in the action to change and the mock_action, and looks for field on the mock_action which indicate
    that fields on the action to change need to be replaced.  For the change field, and the change field only,
    also look for fields to replace within.

    FIXME: we might have an issue when a previous result doesn't exist because it was rejected,
        but we're continuing on with our mock actions to get more data - need to fail gracefully
    """

    logger.debug(f"Replacing fields on {action_to_change} with {mock_action}")

    for key, value in vars(mock_action).items():

        # for all attributes on the mock_action, check if they need to be replaced
        new_value = replacer(key, value, context)
        if new_value is not ...:
            setattr(action_to_change, key, new_value)
            logger.debug(f"Replaced {key} on {action_to_change} with {new_value}")
        
        # if the attribute is the change object, check the parameters to change obj to see if they need to be replaced
        if key == "change":

            for change_key, change_value in vars(value).items():

                new_value = replacer(change_key, change_value, context)
                if new_value is not ...:
                    # set parameter of change object to new value
                    change_obj_on_action_to_change = getattr(action_to_change, key)
                    setattr(change_obj_on_action_to_change, change_key, new_value)  
                    logger.debug(f"Replaced change obj attr {change_key} on {action_to_change} with {new_value}")

                # if change obj parameter is permission_data check the elements to see if *they* need to be replaced
                if change_key == "permission_data":

                    for index, permission_dict in enumerate(change_value): # permission data is list of dicts
                        for dict_key, dict_value in permission_dict.items():
                            new_value = replacer(dict_key, dict_value, context)
                            if new_value is not ...:
                                change_obj_on_action_to_change = getattr(action_to_change, key)
                                permission_data_on_change_obj = getattr(change_obj_on_action_to_change, "permission_data")
                                permission_data_on_change_obj[index][dict_key] = new_value # set keyed value of dict parameter of change object to new value
                                logger.debug(f"Replaced {dict_key} with {new_value} in permdata on {action_to_change}")

    action_to_change.fields_replaced = True  # indicates that action has passed through replace_fields and is safe to use
    return action_to_change


#########################
### Mock Action Utils ###
#########################


class MockAction(object):
    """Mock Actions are used in place of the Action django model in templates.  They are easier to serialize,
    lack db-dependent fields like created_at, and crucially allow us to replace certain fields or subfields
    with references to either the trigger action, or action results from previous actions in an action container."""

    is_mock = True

    def __init__(self, change, actor, target, resolution=None, unique_id=None):

        self.change = change
        self.target = target
        self.actor = actor
        self.status = "created"
        self.pk = 0  # Note that this is an invalid PK

        if not resolution:
            from concord.actions.customfields import Resolution
            resolution = Resolution()
        self.resolution = resolution

        if not unique_id:       
            unique_id = random.randrange(1, 100000)
        self.unique_id = unique_id

    def __repr__(self):
        return f"MockAction(change={self.change}, actor={self.actor}, target={self.target})"
    
    def __str__(self):
        return self.__repr__()

    def create_action_object(self, container_pk, save=True):
        from concord.actions.models import Action
      
        action = Action(actor=self.actor, target=self.target, change=self.change, container=container_pk)
        if save:
            action.save()

        return action


def check_permissions_for_action_group(list_of_actions):
    """Takes in a list of MockActions, generated by clients in mock mode, and runs them 
    through permissions pipeline."""

    action_log = {}

    for index, action in enumerate(list_of_actions):

        is_valid = action.change.validate(actor=action.actor, target=action.target)
        action.status = "created"

        if is_valid:
            from concord.actions.permissions import has_permission
            processed_action = has_permission(action=action)
            processed_action.status = processed_action.resolution.generate_status()
            status, status_log = processed_action.status, processed_action.resolution.get_status_string()
        else:
            status, status_log = "invalid", action.change.validation_error.message

        action_log[index] = { "action": action, "status": status, "log": status_log }

    status_list = [action["status"] for index, action in action_log.items()]
    if all([status == "approved" for status in status_list]):
        summary_status = "approved"
    elif all([status == "rejected" for status in status_list]):
        summary_status = "rejected"
    elif "waiting" in status_list:
        summary_status = "waiting"
    else:
        raise ValueError("Unexpected value in status list: " + ", ".join(status_list))

    return summary_status, action_log
