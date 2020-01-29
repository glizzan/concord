import json


def can_jsonify(obj):
    try:
        json.dumps(obj)
        return True
    except (TypeError, OverflowError):
        return False


def get_state_change_object_given_name(state_change_name):

    import_elements = state_change_name.split(".")

    package_name = ".".join(import_elements[:2])   # eg concord.communities
    relative_import = ".".join(import_elements[1:3])   # eg communites.state_changes
    state_change_object_name = import_elements[3]

    import importlib, inspect
    state_changes_module = importlib.import_module(relative_import, package=package_name)
    for member_tuple in inspect.getmembers(state_changes_module):  #member_tuple is (name, value) tuple
        if member_tuple[0] == state_change_object_name:
            return member_tuple[1]
