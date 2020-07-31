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
    """Get all state changes in a given app, plus core state changes."""

    # Get core state changes
    state_changes = []
    for core_app_name in ["permission_resources", "actions", "conditionals"]:
        app_config = apps.get_app_config(core_app_name)
        state_changes_module = app_config.get_state_changes_module()
        state_changes += inspect.getmembers(state_changes_module)

    # Get state changes from calling app
    app_config = apps.get_app_config(app_name)
    state_changes_module = app_config.get_state_changes_module()
    state_changes += inspect.getmembers(state_changes_module) 

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
    
    # Find the app_name & import its state_changes module, then get the actual state change objects
    state_changes = get_possible_state_changes(app_name)
    matching_state_changes = get_matching_state_changes(model_class.__name__, state_changes)

    # Get parent matches
    matching_state_changes += get_parent_matches(model_class, model_class)

    return list(set(matching_state_changes)) # Make sure there are no duplicates


def replacer(key, value, context):
    """Given the value provided by mock_action, looks for fields that need replacing by finding strings with the right
    format, those that begin and end with {{ }}.  Uses information in context object to replace those fields. In
    the special case of finding something referencing nested_trigger_action (always(?) in the context of a 
    condition being set) it replaces nested_trigger_action with trigger_action."""

    if type(value) == str and value[0:2] == "{{" and value[-2:] == "}}":

        command = value.replace("{{", "").replace("}}", "").strip()
        tokens = command.split(".")

        if tokens[0] == "supplied_fields":
            """Always two tokens long, with format supplied_fields.field_name."""
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
            
            return new_value

        if tokens[0] == "previous":
            """Always three or four tokens long, with format previous.position.action_or_result, for example
            previous.0.action, or previous.position.action_or_result.attribute, for
            example previous.1.result.pk """

            position = int(tokens[1])
            action, result = context.get_action_and_result_for_position(position)
            source = action if tokens[2] == "action" else result

            if len(tokens) == 4:
                return getattr(source, tokens[3])
            else:
                return source

        if tokens[0] == "nested_trigger_action":
            """In this special case, we merely replace nested_trigger_action with trigger_action
            so that when this object is passed through replace_fields again, later, it will
            *then* replace with *that* trigger_action.  (Yes, it's a HACK, don't judge me.)"""
            return value.replace("nested_trigger_action", "trigger_action")

    return ...


def replace_fields(*, action_to_change, mock_action, context):
    """Takes in the action to change and the mock_action, and looks for field on the mock_action which indicate
    that fields on the action to change need to be replaced.  For the change field, and the change field only,
    also look for fields to replace within.

    FIXME: we might have an issue when a previous result doesn't exist because it was rejected,
        but we're continuing on with our mock actions to get more data - need to fail gracefully
    """

    for key, value in vars(mock_action).items():

        # for all attributes on the mock_action, check if they need to be replaced
        new_value = replacer(key, value, context)
        if new_value is not ...:
            setattr(action_to_change, key, new_value)
        
        # if the attribute is the change object, check the parameters to change obj to see if they need to be replaced
        if key == "change":

            for change_key, change_value in vars(value).items():

                new_value = replacer(change_key, change_value, context)
                if new_value is not ...:
                    # set parameter of change object to new value
                    change_obj_on_action_to_change = getattr(action_to_change, key)
                    setattr(change_obj_on_action_to_change, change_key, new_value)  

                # if change obj parameter is permission_data check the elements to see if *they* need to be replaced
                if change_key == "permission_data":

                    for index, permission_dict in enumerate(change_value): # permission data is list of dicts
                        for dict_key, dict_value in permission_dict.items():
                            new_value = replacer(dict_key, dict_value, context)
                            if new_value is not ...:
                                change_obj_on_action_to_change = getattr(action_to_change, key)
                                permission_data_on_change_obj = getattr(change_obj_on_action_to_change, "permission_data")
                                permission_data_on_change_obj[index][dict_key] = new_value # set keyed value of dict parameter of change object to new value

    action_to_change.fields_replaced = True  # indicates that action has passed through replace_fields and is safe to use
    return action_to_change


class MockAction(object):
    """Mock Actions are used in place of the Action django model in templates.  They are easier to serialize,
    lack db-dependent fields like created_at, and crucially allow us to replace certain fields or subfields
    with references to either the trigger action, or action results from previous actions in an action container."""

    is_mock = True

    def __init__(self, change, actor, target, resolution=None, unique_id=None):

        self.change = change
        self.target = target
        self.actor = actor

        if not resolution:
            from concord.actions.customfields import Resolution
            resolution = Resolution(external_status="draft")
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
        action.resolution.external_status = "sent" 

        if is_valid:
            from concord.actions.permissions import has_permission
            processed_action = has_permission(action=action)
            status, status_log = processed_action.resolution.status, processed_action.resolution.get_status_string()
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
