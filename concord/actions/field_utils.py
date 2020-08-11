"""
This module contains helper methods which generate form fields, primarily for front end use.
"""


def field_helper(type_of_field, overrides=None):
    """Always returns a dictionary with keys: label, required, default, type, field_name, value. Optional
    additional fields include full_name (for permission fields).

    Args:
        type_of_field: str
            A string corresponding exactly to a field type. Options are: "RoleListField", "ActorListField"
        overrides: dict
            Dictionary with keys corresponding to the form_field_dict keys and a value the caller wishes to use
            to override the value defined below.
    """

    form_field_dict = {}

    if type_of_field == "RoleListField":
        form_field_dict.update({
            "label": "What roles have this permission?",
            "required": False,
            "default": None,
            "type": "PermissionRoleField",
            "value": None,
            "field_name": None,
            "full_name": None
        })

    if type_of_field == "ActorListField":
        form_field_dict.update({
            "label": "What actors have this permission?",
            "required": False,
            "default": None,
            "type": "PermissionActorField",
            "value": None,
            "field_name": None,
            "full_name": None
        })

    if form_field_dict == {}:
        raise ValueError("Couldn't find field of type: ", type_of_field)

    if overrides:
        for key, value in overrides.items():
            form_field_dict[key] = value

    return form_field_dict
