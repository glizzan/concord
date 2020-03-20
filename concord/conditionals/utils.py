import json
from django.core.exceptions import ValidationError


def validate_condition(condition_type, condition_data, permission_data, target_type):
    '''Helper method to confirm that data passed to create a new condition (and permissions
    to be set on that condition) can actually be instantiated when the time comes.'''

    from concord.conditionals.client import BaseConditionalClient

    is_valid = True
    error_log = ''

    # validate condition type
    try:
        condition_model = BaseConditionalClient(system=True).condition_lookup_helper(lookup_string=condition_type)
    except:
        is_valid = False
        error_log += "Condition type " + condition_type + " is not a valid type. "
        return is_valid, error_log  # Not worth continuing to collect errors without a condition type

    # validate condition data
    try:
        import copy
        condition_data_to_validate = copy.deepcopy(condition_data)
        if type(condition_data) == str:
            condition_data = json.loads(condition_data)
        condition_data["action"] = 66666  # FIXME: fake to prevent a validation error but may cause unique error with more data
        # FIXME: shouldn't have to a) make a deep copy and b) fake the action field to validate :/
        
        condition_instance = condition_model(**condition_data)
        condition_instance.full_clean()
    except ValidationError as error:
        is_valid = False
        for key, value in error.message_dict.items():
            error_log += key + " : " + value[0]

    # validate permission data
    # TODO: will depend on how we redo permission data storage in condition

    # validate target type
    if target_type is not None and target_type not in ["gov", "own"]:
        is_valid = False
        error_log += "Target type must be 'gov', 'own' or 'none'."

    return is_valid, error_log