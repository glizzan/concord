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
        # FIXME: this is a hack to be fixed during ownership refactoring
        if hasattr(owner, "username"):
            owner_type = "ind"
        elif hasattr(owner, "is_community"):
            owner_type = "com"
        else:
            raise TypeError("Owner should only be user or community")
        return PermissionsItem.objects.create(
            permitted_object = permitted_object,
            change_type = self.permission_change_type,
            owner_type = owner_type,
            owner_content_type = ContentType.objects.get_for_model(owner),
            owner_object_id = owner.id)


def filter_permissions(*, target, state_change_objects):
    """Given a target and a list of state change objects potentially applicable to the 
    target, checks to see if the target's class is in each state change object's 
    get_allowable_targets list.  If it is, add to list using permissions display format."""

    settable_permissions = []

    target_class = target if inspect.isclass(target) else target.__class__

    for state_change_object_tuple in state_change_objects:
        state_change_object = state_change_object_tuple[1]
        if hasattr(state_change_object, "get_allowable_targets"):
            if target_class in state_change_object.get_allowable_targets():
                settable_permissions.append(state_change_object)

    return settable_permissions

def get_settable_permissions(* , target):
    """Gets a list of all permissions that may be set on the model."""

    state_change_objects = target.get_state_change_objects()
    settable_permissions = filter_permissions(target=target, 
        state_change_objects=state_change_objects)

    for parent in target.__class__.__bases__:

        if hasattr(parent, "get_state_change_objects"):
            parent_state_change_objects = parent.get_state_change_objects()
            permissions = filter_permissions(target=parent, state_change_objects=parent_state_change_objects)
            settable_permissions += permissions

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


def create_permission_outside_pipeline(permission_dict, condition_item, condition_template):
    '''Helper method used internally to bypass permissions pipeline when creating 
    a permission.'''
    from concord.permission_resources.models import PermissionsItem
    permission = PermissionsItem(permitted_object=condition_item)            
    if "permission_actors" in permission_dict:
        permission.actors.add_actors(actors=permission_dict["permission_actors"])
    if "permission_roles" in permission_dict:
        permission.roles = json.dumps(permission_dict["permission_roles"])
        # permission.roles.add_roles(roles=permission_dict["permission_roles"])
    permission.change_type = permission_dict["permission_type"]
    permission.configuration = permission_dict["permission_configuration"]
    permission.owner = condition_template.get_owner()
    permission.owner_type = condition_template.owner_type
    permission.save()


# Checks inputs of actors, roles, etc.
# FIXME: should be able to delete this once custom fields are implemented
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
    from concord.actions.state_changes import create_change_object
    change_object = create_change_object(action.change_type, action.change_data)

    # Then call check_configuration on the state_change, passing in the permission
    # configuration data, and return the result.
    return change_object.check_configuration(permission)