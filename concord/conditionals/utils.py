import json
from django.core.exceptions import ValidationError


def reformat_condition_data(condition_data):
    """
    There are two ways to get data from a condition or condition template - by referencing the field directly,
    and getting a dictionary of key-value pairs, or by calling get_configurable_fields or 
    get_configurable_fields_with_data, which get you a more elaborate dict with information useful on the front
    end.

    If we give out data two ways, we may get data back two ways.  This method changes the fieds dict back into 
    key_value pairs so they can be validated and saved.
    """

    if not condition_data:
        return {}

    if type(condition_data) == str:
        condition_data = json.loads(condition_data)

    needs_reformatting = all("type" in item for item in condition_data)
    if not needs_reformatting:
        return condition_data
   
    new_condition_data = {}
    for item in condition_data:
        if item['type'] == "BooleanField":
            if item['value'] == None:
                continue   # Boolean fields can't store null values, so keep whatever default the db provides
            item['value'] = True if item['value'] == "true" else item['value']
            item['value'] = False if item['value'] == "false" else item['value']
        if item['type'] in ["FloatField", "IntegerField"]: # Should probably treat floatfield differently
            item['value'] = int(item['value'])  # FIXME: implement try/catch and return as error?
        new_condition_data.update({ item['name'] : item['value'] })
    
    return new_condition_data


def reformat_permission_data(permission_data):
    """
    Permission data typically recieved as: 
    [{'name': 'Roles who can vote', 'type': 'PermissionRoleField', 'required': False, 'value': 'romans'}, 
    {'name': 'People who can vote', 'type': 'PermissionActorField', 'required': False, 'value': None}]

    Needs to be stored as a single dict with key-value pairs:
    Changes.Conditionals.AddVote + "_actors" : value
    """

    if not permission_data:
        return {}

    if type(permission_data) == str:
        permission_data = json.loads(permission_data)

    needs_reformatting = all("type" in item for item in permission_data)
    if not needs_reformatting:
        return permission_data

    new_permission_data = {}
    for item in permission_data:
        if item["value"] in [None, []]:
            continue   # Don't save empty values
        new_permission_data.update({ item["field_name"]: item["value"] })
    return new_permission_data


# FIXME: CPREFACTOR
def validate_condition(condition_type, condition_data, permission_data, target_type):
    '''Helper method to confirm that data passed to create a new condition (and permissions
    to be set on that condition) can actually be instantiated when the time comes.'''

    from concord.conditionals.client import BaseConditionalClient

    is_valid = True
    error_log = ''

    import copy  # FIXME: shouldn't have to make a deep copy
    if type(condition_data) == str:
        new_condition_data = json.loads(condition_data)
    else:
        new_condition_data = copy.deepcopy(condition_data)
    if type(permission_data) == str:
        new_permission_data = json.loads(permission_data)
    else:
        new_permission_data = copy.deepcopy(permission_data)

    
    # validate condition type
    try:
        condition_model = BaseConditionalClient(system=True).condition_lookup_helper(lookup_string=condition_type)
    except:
        is_valid = False
        error_log += "Condition type " + condition_type + " is not a valid type. "
        return is_valid, error_log  # Not worth continuing to collect errors without a condition type

    # validate condition data
    try:

        new_condition_data["action"] = 66666  # FIXME: fake to prevent a validation error but may cause unique error with more data
        condition_instance = condition_model(**new_condition_data)
        condition_instance.full_clean()

    except ValidationError as error:
        is_valid = False
        for key, value in error.message_dict.items():
            error_log += key + " : " + value[0]

    # validate permission data
    try:
        # how to validate?
        pass 
    except ValidationError as Error:
        is_valid = False

    # validate target type
    if target_type is not None and target_type not in ["gov", "own"]:
        is_valid = False
        error_log += "Target type must be 'gov', 'own' or 'none'."

    return is_valid, error_log