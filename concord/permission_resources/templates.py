""" Contains helper methods for generating templates from objects and vice versa."""

import json, random
from collections import namedtuple, OrderedDict

from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType


##########################
### Object to template ###
##########################


def get_basic_info(model_instance):
    model_type = model_instance.__class__.__name__
    info_dict = { "model_type": model_type, "original_pk": model_instance.pk }
    return info_dict


def get_universal_fields(model_instance):
    """Gets field set in PermissionedModel, which all templatizable objects should inherit from."""
    return { "foundational_permission_enabled": model_instance.foundational_permission_enabled,
             "governing_permission_enabled": model_instance.governing_permission_enabled  }


def json_serializable_community(community):
    dict_to_save = get_basic_info(community)
    dict_to_save.update({"fields": get_universal_fields(community)})
    dict_to_save["fields"].update({"name": community.name, 
        "roles": community.roles.get_roles_db_structure()})
    return dict_to_save


def json_serializable_condition(condition):
    dict_to_save = get_basic_info(condition)
    dict_to_save.update({"fields": get_universal_fields(condition)})
    dict_to_save["fields"].update({
        "condition_type": condition.condition_type,
        "condition_data": condition.condition_data,
        "permission_data": condition.permission_data,
        "target_type": condition.target_type
    })
    return dict_to_save


def json_serializable_permission(permission):
    dict_to_save = get_basic_info(permission)
    dict_to_save.update({"fields": get_universal_fields(permission)})
    dict_to_save["fields"].update({
        "is_active": permission.is_active,
        "inverse": permission.inverse,
        "actors": permission.actors.as_pks(),
        "roles": permission.roles.role_list,
        "change_type": permission.change_type,
        "configuration": permission.configuration
    })
    return dict_to_save  


def json_serializable_object(object_to_save):
    dict_to_save = get_basic_info(object_to_save)
    dict_to_save.update({"fields": get_universal_fields(object_to_save)})
    dict_to_save["fields"].update({ "name": object_to_save.name })
    return dict_to_save


##########################
### Template to Object ###
##########################


def get_model_given_name(model_name):

    if model_name.lower() == "community":
        from concord.communities.models import Community
        return Community
    if model_name.lower() == "conditiontemplate":
        from concord.conditionals.models import ConditionTemplate
        return ConditionTemplate
    if model_name.lower() == "permissionsitem":
        from concord.permission_resources.models import PermissionsItem
        return PermissionsItem
    if model_name.lower() == "resource":
        from concord.resources.models import Resource
        return Resource
    if model_name.lower() == "item":
        from concord.resources.models import Item
        return Item
    
    raise ValueError("model_name ", model_name, " does not correspond to template-able model")


def create_unsaved_instance_given_template(template):

    model = get_model_given_name(template["model_type"])

    if template["model_type"] == "Community":

        # FIXME: there's gotta be a cleaner way to handle roles (& the other customfields below)
        from concord.communities.customfields import RoleHandler
        role_handler = RoleHandler(
            members = template["fields"]["roles"]["members"],
            owners = template["fields"]["roles"]["owners"],
            governors = template["fields"]["roles"]["governors"],
            custom_roles = template["fields"]["roles"]["custom_roles"]
        )
        template["fields"]["roles"] = role_handler
        instance = model(**template["fields"])
        return instance

    if template["model_type"] == "PermissionsItem":
        from concord.permission_resources.customfields import ActorList, RoleList
        template["fields"]["actors"] = ActorList(actor_list=template["fields"]["actors"])
        template["fields"]["roles"] = RoleList(role_list=template["fields"]["roles"])
        instance = model(**template["fields"])
        return instance  

    if template["model_type"] in ["ConditionTemplate", "Resource", "Item"]:
        instance = model(**template["fields"])
        return instance


########################
### Template to text ###
########################


def capitalize_first_letter(text):
    """Helper method which capitalizes first letter in a string."""
    return text[0].upper() + text[1:]


def list_to_text(list_to_convert):
    """Given a list of strings, return them as list in format 'apple, banana and carrot'."""
    if len(list_to_convert) == 1:
        return str(list_to_convert[0])
    text = ""
    last_index = len(list_to_convert)-1
    for item in list_to_convert[:last_index]:
        text += str(item)
    text += " and " + str(list_to_convert[last_index])
    return text


def roles_to_text(roles):
    """Given a list of roles, returns in readable format."""

    if roles is None:
        return ""

    role_string = "roles " if len(roles) > 1 else "role "

    return "everyone with " + role_string + list_to_text(roles)


def actors_to_text(actor_info):
    """Given a list of actors, returns in a readable format."""

    if actor_info is None:
        return ""
    
    actor_string = "individuals " if len(actor_info) > 1 else "individual "

    return actor_string + list_to_text(actor_info)


def roles_and_actors(role):

    text = ""

    if len(role["roles"]) > 0:
        text += roles_to_text(role["roles"])
    
    if len(role["roles"]) > 0 and len(role["actors"]) > 0:
        text += " and "

    if len(role["actors"]) > 0:
        text += actors_to_text(role["actors"])

    if len(role["roles"]) == 0 and len(role["actors"]) == 0:
        return "no one"
    
    return text


def community_basic_info_to_text(template_model):
    """Gets basic community info such as name, owners, governors."""
    community = template_model.get_community()
    return "Community %s is owned by %s and governed by %s. " % (community.name, 
        roles_and_actors(community.roles.get_owners()),
        roles_and_actors(community.roles.get_governors()))


def conditions_to_text(conditions):
    """Takes a list of conditions and turns them into text."""

    from conditionals.client import PermissionConditionalClient
    pcc = PermissionConditionalClient(actor="system")

    condition_strings = []
    for condition in conditions:
        condition_object = pcc.condition_lookup_helper(lookup_string=condition.condition_type)
        permission_data = json.loads(condition.permission_data)
        people_and_role_list = roles_and_actors({ "roles": permission_data["permission_roles"], 
            "actors": permission_data["permission_actors"]})
        new_string = "on the condition that " + people_and_role_list + " " + condition_object.verb_name
        condition_strings.append(new_string)
    return list_to_text(condition_strings)


def community_governance_info_to_text(template_model):
    """Give details of how owners/governors operate on this community."""

    community = template_model.get_community()

    owner_condition, governor_condition = None, None
    for condition_key, condition in template_model.conditions.items():
        if condition.target_type == "own":
            owner_condition = condition
        if condition.target_type == "gov":
            governor_condition = condition
    
    text = ""

    if community.foundational_permission_enabled:
        text += "By default, the owners of the community must approve all actions"
    else:
        text += "By default, the owners do not need to approve actions in the community"

    if owner_condition:
        text += ", " + conditions_to_text([owner_condition]) + ". "
    else:
        text += ". "

    if community.governing_permission_enabled:
        text += "Unless otherwise specified, the governors of the community can take any action"
    else:
        text += "The governors of the community can take actions only when specified"

    if governor_condition:
        text += ", " + conditions_to_text([governor_condition]) + ". "
    else:
        text += ". "

    return text


def community_members_to_text(template_model):
    community = template_model.get_community()
    return "The members of this community are " + list_to_text(community.roles.members) + ". "


def community_roles_to_text(template_model):
    community = template_model.get_community()
    custom_roles = community.roles.get_custom_roles()
    
    if len(custom_roles) == 0:
        return None
    elif len(custom_roles) == 1:
        text = "There is 1 custom role in the community, "
    else:
        text = "There are %s custom roles in the community: " % str(len(custom_roles))

    custom_role_names = list(custom_roles.keys())
    text += list_to_text(custom_role_names) + ". "

    for role_name, role_members in custom_roles.items():
        conjoin_with = " are " if len(role_members) > 1 else " is "
        new_text = actors_to_text(role_members) + conjoin_with + "'" + role_name + "'. "
        text += capitalize_first_letter(new_text)

    return text


def permission_to_text(template_model, set_target=None):
    """X has/have permission to Y of Z."""
    from actions.utils import get_state_change_object_given_name

    text = ""

    for permission_key, permission in template_model.permissions.items():

        permitted_object = template_model.get_target_of_field(permission_key, "permitted_object")

        if hasattr(permitted_object, "name"):
            permitted_object_name = permitted_object.name
        else:
            permitted_object_name = permitted_object.get_change_type()

        if set_target == None or set_target == permitted_object:

            action = get_state_change_object_given_name(permission.change_type).description.lower()
            peopledict = {"roles": permission.roles.role_list, "actors": permission.actors.as_pks()}   
            new_text = roles_and_actors(peopledict) + " can " + action + " for " + permitted_object_name
            text += capitalize_first_letter(new_text)

            conditions_on_this_permission = []
            for condition_key, condition in template_model.conditions.items():
                conditioned_object = template_model.get_target_of_field(condition_key, "conditioned_object")
                if conditioned_object == permission:
                    conditions_on_this_permission.append(condition)
            
            if conditions_on_this_permission:
                text += ", " + conditions_to_text(conditions_on_this_permission)
                
            text += ". "

            # Look for nested permissions recursively.
            text += permission_to_text(template_model, set_target=permission)
                
    return text


def owned_objects_basic_info(template_model):

    num_objects = len(template_model.owned_objects)
    if num_objects == 0:
        return ""

    object_string = " objects, " if num_objects > 1 else " object, "

    text = "The community owns " + str(num_objects) + object_string

    obj_list = []
    for index, obj in template_model.owned_objects.items():
        obj_list.append(obj._meta.model.__name__ + " " + obj.name)
            
    text += list_to_text(obj_list) + ". "

    return text


def generate_text_from_template(template_model):

    text = OrderedDict()

    text.update({ "community_basic_info" : community_basic_info_to_text(template_model) }) 
    text.update({ "community_governance_info" : community_governance_info_to_text(template_model) }) 
    text.update({ "community_members_info" : community_members_to_text(template_model) }) 
    text.update({ "community_roles_info" : community_roles_to_text(template_model) })
    text.update({ "community_permissions_info" : permission_to_text(template_model, 
        set_target=template_model.get_community()) })
    
    text.update({ "owned_objects_basic_info" : owned_objects_basic_info(template_model) })
    for index, owned_object in template_model.owned_objects.items():
        text.update({ "owned_object_" + str(index) : permission_to_text(template_model, 
            set_target=owned_object) })

    return text
