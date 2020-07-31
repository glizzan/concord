"""
Helps generate form fields for front end to use.

"""

def field_helper(type_of_field, overrides=None):
    """Always returns a dictionary with keys label, required, default, type, field_name. Optional
    additional fields include full_name (for permission fields).
    
    Overrides is an optional dictionary with keys existing in the dictionaries below and new values to
    use instead of the ones specified in this method."""

    form_field_dict = {}

    if type_of_field == "RoleListField":
        form_field_dict.update({
            "label": "What roles have this permission?",
            "required": False,
            "default": None,
            "type": "PermissionRoleField",   # adjust front end to expect type RoleListField?
            "value": None,
            "field_name": None,
            "full_name": None
        })

    if type_of_field == "ActorListField":
        form_field_dict.update({
            "label": "What actors have this permission?",
            "required": False,
            "default": None,
            "type": "PermissionActorField",   # adjust front end to expect type RoleListField?
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
