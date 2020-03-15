import json


def can_jsonify(obj):
    try:
        json.dumps(obj)
        return True
    except (TypeError, OverflowError):
        return False


def get_state_change_object_given_name(state_change_name):

    concord, app_name, state_changes, object_name = state_change_name.split(".")

    package_to_anchor_to = ".".join([concord, app_name])
    module_to_import = "." + state_changes  # note initial period

    import importlib, inspect
    state_changes_module = importlib.import_module(module_to_import, package=package_to_anchor_to)
    for member_tuple in inspect.getmembers(state_changes_module):  
        #member_tuple is (name, value) tuple
        if member_tuple[0] == object_name:
            return member_tuple[1]
