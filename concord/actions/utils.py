import json, inspect
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

