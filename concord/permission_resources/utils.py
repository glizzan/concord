import inspect, json
from collections import OrderedDict

from django.contrib.contenttypes.models import ContentType


class MockMetaPermission:
    """Sometimes metapermissions are created for permissions that do not
    themselves exist yet on a specific permitted object.  This mock 
    item exists so that the MetaPermissionsForm can treat it as though
    it's an instance."""
    
    def __init__(self, permitted_object_id, permitted_object_content_type, 
        permission_change_type):
        self.permitted_object_id = permitted_object_id
        self.permitted_object_content_type = permitted_object_content_type
        self.permission_change_type = permission_change_type
        # Helper methods for template use
        self.object_id = self.permitted_object_id
        self.content_type = self.permitted_object_content_type

    def get_permitted_object(self):
        ct = ContentType.objects.get_for_id(id=self.permitted_object_content_type)
        ct_class = ct.model_class()
        self.permitted_object = ct_class.objects.get(pk=self.permitted_object_id)
        return self.permitted_object

    def get_state_change_objects(self):
        import importlib, inspect
        relative_import = ".permission_resources.state_changes"
        state_changes_module = importlib.import_module(relative_import, package="concord")
        return inspect.getmembers(state_changes_module) 

    def get_owner(self):
        permitted_object = self.get_permitted_object()
        return permitted_object.get_owner()

    def create_self(self, owner):
        from concord.permission_resources.models import PermissionsItem
        permitted_object = self.get_permitted_object()
        if not hasattr(owner, "is_community") and owner.is_community:
            raise TypeError("Owner should only be user or community")
        return PermissionsItem.objects.create(
            permitted_object = permitted_object,
            change_type = self.permission_change_type,
            owner_content_type = ContentType.objects.get_for_model(owner),
            owner_object_id = owner.id)


def get_settable_permissions(* , target):
    """Gets a list of all permissions that may be set on the model."""
    # FIXME: this should call get_settable_classes instead, 

    settable_permissions = target.get_settable_state_changes()
    
    for parent in target.__class__.__bases__:
        if hasattr(parent, "get_settable_state_changes"):
            settable_permissions += parent.get_settable_state_changes()

    # Remove duplicates while preserving order
    return list(OrderedDict.fromkeys(settable_permissions))


def format_as_tuples(permissions):
    formatted_permissions = []
    for permission in permissions:
        formatted_permissions.append((permission.get_change_type(), 
            permission.description))
    return formatted_permissions

def format_as_list_of_strings(permissions):
    formatted_permissions = []
    for permission in permissions:
        formatted_permissions.append(permission.get_change_type())
    return formatted_permissions


def create_permissions_outside_pipeline(permission_dict, condition_item, owner):
    '''Helper method used internally to bypass permissions pipeline when creating 
    a permission.  A bit hinky since permission_dicts have up to two key-value pairs for each
    permission (one for roles, one for actors).'''
    from concord.permission_resources.models import PermissionsItem

    new_permissions = {}   # keys will be change_types, values the actual permission

    for field_name, field_value in permission_dict.items():

        change_type, perm_type = condition_item.permission_field_map(field_name)
        if change_type not in new_permissions:
            new_permissions[change_type] = PermissionsItem(permitted_object=condition_item, change_type=change_type,
                owner=owner)

        if perm_type == "roles":
            new_permissions[change_type].roles.add_roles(role_list=field_value)
        if perm_type == "actors":
            new_permissions[change_type].actors.add_actors(actors=field_value)

    for key, permission in new_permissions.items():
        permission.save()


# Checks inputs of actors, roles, etc.
# NOTE: should be able to delete this once custom fields are implemented (can we do so now?)
def check_permission_inputs(dict_of_inputs):
    """
    Decorator to help with type issues, example usage: 
    @check_permission_inputs(dict_of_inputs={'role_pair': 'role_pair', 'community': 'string_pk'})
    """
    def check_permission_inputs_decorator(func):
        def function_wrapper(*args, **kwargs):
            if type(dict_of_inputs) is not dict:
                raise TypeError("check_permission_inputs must be passed a dict.")
            for key, value in kwargs.items():
                input_type = dict_of_inputs[key]
                if input_type == "role_pair":
                    community, role = value.split("_")
                    int(community)
                    continue
                if input_type == "json":
                    json.loads(value)
                    continue
                if input_type == "string_pk":
                    int(value)
                    if type(value) == int:
                        raise TypeError("String_pk should be string, not int")
                    continue
                if input_type == "simple_string":
                    if "[" in value or "{" in value:
                        raise TypeError("Simple string cannot include [ or {")
                    continue
                raise ValueError("Check_permission_inputs was given unknown input_type")

            return func(*args, **kwargs)
        return function_wrapper
    return check_permission_inputs_decorator


def check_configuration(action, permission):

    # Does permission.configuration contain keys?  If not, the permission is not
    # configured, so the action passes.
    if not json.loads(permission.configuration):
        return True

    # If configuration exists, instantiate the action's change type with its
    # change data.  
    from concord.actions.customfields import create_change_object
    change_object = create_change_object(action.change.get_change_type(), 
        action.change.get_change_data())

    # Then call check_configuration on the state_change, passing in the permission
    # configuration data, and return the result.
    result, message = change_object.check_configuration(permission)
    if result == False and message:
        action.resolution.add_to_log(message)
    return result


def get_verb_given_permission_type(permission):
    from concord.actions.utils import get_state_change_object_given_name
    state_change_object = get_state_change_object_given_name(permission)
    return state_change_object.description.lower()
