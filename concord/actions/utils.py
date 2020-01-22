import json


def can_jsonify(obj):
    try:
        json.dumps(obj)
        return True
    except (TypeError, OverflowError):
        return False


def get_state_change_object_given_name(state_change_name):

    import_elements = state_change_name.split(".")
    package_name = import_elements[0]
    relative_import = ".".join(import_elements[1:])

    import importlib, inspect
    state_changes_module = importlib.import_module(relative_import, package=package_name)
    return inspect.getmembers(state_changes_module) 
    