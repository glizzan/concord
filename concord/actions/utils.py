import json, inspect, random
from django.apps import apps


def can_jsonify(obj):
    try:
        json.dumps(obj)
        return True
    except (TypeError, OverflowError):
        return False


def get_state_change_object_given_name(state_change_name):

    name_elements = state_change_name.split(".")
    if name_elements[0] == "concord":
        # Name fed in has format concord.app.state_changes.state_change_object
        app_name = name_elements[1]
        change_name = name_elements[3]
    else:
        # Name fed in has format app_name.state_changes.state_change_object 
        app_name = name_elements[0]
        change_name = name_elements[2]

    # Import state changes
    app_config = apps.get_app_config(app_name)
    state_changes_module = app_config.get_state_changes_module()
    state_changes = inspect.getmembers(state_changes_module) 

    # Get matching state change
    for member_tuple in state_changes:   #member_tuple is (name, value) tuple 
        if member_tuple[0] == change_name:
            return member_tuple[1]


def get_possible_state_changes(app_name):
    """Get all state changes in a given app."""
    app_config = apps.get_app_config(app_name)
    state_changes_module = app_config.get_state_changes_module()
    state_changes = inspect.getmembers(state_changes_module) 
    return state_changes


def get_matching_state_changes(model_name, state_changes):
    """Iterate through a list of state changes and check for matches."""
    matching_state_changes = []
    for member_tuple in state_changes:  #member_tuple is (name, value) tuple 
        if hasattr(member_tuple[1], "can_set_on_model") and member_tuple[1].can_set_on_model(model_name):
            if member_tuple[0] != "BaseStateChange":
                matching_state_changes.append(member_tuple[1])
    return matching_state_changes


def get_parent_matches(model_to_match, model_to_get_parent_of):
    matching_state_changes = []
    for parent in  model_to_get_parent_of.__bases__:
        if hasattr(parent, "get_settable_state_changes"):   # only checks parents which are PermissionedModels
            state_changes = get_possible_state_changes(parent._meta.app_label)
            matching_state_changes += get_matching_state_changes(model_to_match.__name__, state_changes)
            # Get parent matches
            matching_state_changes += get_parent_matches(model_to_match, parent)
    return matching_state_changes


def get_state_change_objects_which_can_be_set_on_model(model_class, app_name):
    """When given a model and its containing app, returns all state changes that apply to that model."""
    
    # Find the app_name & import its state_changes module, then get the actual statate change objects
    state_changes = get_possible_state_changes(app_name)
    matching_state_changes = get_matching_state_changes(model_class.__name__, state_changes)

    # Get parent matches
    matching_state_changes += get_parent_matches(model_class, model_class)

    return matching_state_changes


def replace_fields(*, commands, action_to_change, trigger_action, previous_actions_and_results):
    """Takes in a set of replacement commands and executes them using the other parameters.  
    
    Example command: "REPLACE change PARAMETER 'member_pk_list' WITH previous_action unique_id action PARAMETER actor"
    
    Syntax must be exactly correct, so be careful!"""

    for command in commands:

        # Parse command

        command = command.replace("REPLACE ", "")  # Initial REPLACE command is just there for readability
        target_string, source_string = command.split(" WITH ")

        target_tokens = target_string.split(" PARAMETER ")
        target = target_tokens[0]
        target_parameter = target_tokens[1] if len(target_tokens) > 1 else None
    
        source_tokens = source_string.split(" PARAMETER ")
        source = source_tokens[0]
        source_parameter = source_tokens[1] if len(source_tokens) > 1 else None

        # Get data to replace with

        if "previous_action" in source:
            source_type, unique_id, action_or_result = source.split(" ")
            source_data = previous_actions_and_results[int(unique_id)][action_or_result]
        elif source == "trigger_action":
            source_data = trigger_action

        if source_parameter:
            source_data = getattr(source_data, source_parameter)

        # Replace on target object

        if target_parameter:
            field_to_change = getattr(action_to_change, target)
            setattr(field_to_change, target_parameter, source_data)
        else:
            setattr(action_to_change, target, source_data)

        # TODO: not 100% sure this will work but I think it will, since Python is all referency?

    return action_to_change     


class MockAction(object):
    """Mock Actions are used in place of the Action django model in templates.  They are easier to serialize,
    lack db-dependent fields like created_at, and crucially allow us to replace certain fields or subfields
    with references to either the trigger action, or action results from previous actions in an action container."""

    is_mock = True

    def __init__(self, change, actor, target, dependent_fields=None, resolution=None, unique_id=None):

        self.change = change
        self.target = target
        self.actor = actor
        self.dependent_fields = dependent_fields if dependent_fields else []

        if not resolution:
            from concord.actions.customfields import Resolution
            resolution = Resolution(status="draft")
        self.resolution = resolution

        if not unique_id:       
            unique_id = random.randrange(1, 100000)
        self.unique_id = unique_id

    def add_command_to_dependent_fields(self, command):
        self.dependent_fields.append(command)

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

        if is_valid:
            from concord.actions.permissions import has_permission
            processed_action = has_permission(action=action)
            status, log = processed_action.resolution.status, processed_action.resolution.log
        else:
            status, log = "invalid", action.change.validation_error.message

        action_log[index] = { "action": action, "status": status, "log": log }

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


class ClientInterface(object):

    def __init__(self, default_actor=None, system=False):
        
        if not default_actor or system:
            raise ValidationError("When creating interface, must supply default actor or set system to true")

        if default_actor:
            self.communities = CommunityClient(actor=default_actor)
            self.conditions = ConditionalClient(actor=default_actor)
            self.permissions = PermissionResourceClient(actor=default_actor)
            self.resources = ResourceClient(actor=default_actor)
        elif system:
            self.communities = CommunityClient(system=True)
            self.conditions = ConditionalClient(system=True)
            self.permissions = PermissionResourceClient(system=True)
            self.resources = ResourceClient(system=True)    
