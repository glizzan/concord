import json
from collections import namedtuple, OrderedDict

from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType

from concord.permission_resources.client import PermissionResourceClient


def get_universal_fields(model_instance):
    """Gets field set in PermissionedModel, which all templatizable objects should inherit from."""
    field_dict = {
        "fields": {
            "foundational_permission_enabled": model_instance.foundational_permission_enabled,
            "governing_permission_enabled": model_instance.governing_permission_enabled 
            },
        "related_fields": []
    }
    if model_instance.__class__.__name__ != "Community":    # community owns itself and has no data in owner field
        field_dict["related_fields"].append({
            "related_field_old_id": model_instance.owner_content_type.model + "_" + str(model_instance.owner_object_id),
            "related_field_type": "GenericForeignKey",
            "related_field_data": {
                        "owner_content_type": model_instance.owner_content_type,
                        "owner_object_id": model_instance.owner_object_id
                    }
        })
    return field_dict


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


def instance_to_template(model_instance):

    model_type = model_instance.__class__.__name__
    serializable_dict = { "model_type": model_type, "original_pk": model_instance.pk }
    serializable_dict.update(get_universal_fields(model_instance))

    if model_type == "Community":
        serializable_dict["fields"].update({"name": model_instance.name, 
            "roles": model_instance.roles.get_roles_db_structure()})

    if model_type == "ConditionTemplate":
        serializable_dict["fields"].update({
            "condition_type": model_instance.condition_type,
            "condition_data": model_instance.condition_data,
            "permission_data": model_instance.permission_data,
            "conditioning_choices": model_instance.conditioning_choices
        })
        model_name = "PermissionsItem" if model_instance.conditioning_choices == "permission" else "Community"
        serializable_dict["related_fields"].append({
            "related_field_old_id": model_name + "_" + str(model_instance.conditioned_object),
            "related_field_type": "ConditionedObject",
            "related_field_data": { "conditioned_object": model_instance.conditioned_object }
        })    

    if model_type == "PermissionsItem":
        serializable_dict["fields"].update({
            "is_active": model_instance.is_active,
            "inverse": model_instance.inverse,
            "actors": model_instance.actors.as_pks(),
            "roles": model_instance.roles.get_roles(),
            "change_type": model_instance.change_type,
            "configuration": model_instance.configuration
        })
        serializable_dict["related_fields"].append({
            "related_field_old_id": model_instance.permitted_object_content_type.model + "_" + str(model_instance.permitted_object_id),
            "related_field_type": "GenericForeignKey",
            "related_field_data": 
                    { "permitted_object_content_type": model_instance.permitted_object_content_type,
                      "permitted_object_id": model_instance.permitted_object_id }
        })                  

    if model_type in ["Resource", "Item"]:  # Models with no extra templateable fields beyond "name"
        serializable_dict["fields"].update({ "name": model_instance.name }) 

    return serializable_dict


# FIXME: this will be more effective with custom validators on model fields
def validate_template(template):
    """This method takes a template and checks whether the corresponding object could be created given
    from the template. It does not create the object."""

    model = get_model_given_name(template["model_type"])

    try:
        instance = model(**template["fields"]) 
    except TypeError as error:
        return error

    try:
        instance.full_clean()
    except (TypeError, ValidationError) as error:
        return error
    
    return True


def generate_template_set(*, actor, community, optional_object_list=None):
    """Generates a template given a community and an optional list of objects owned by the community.
    If no object list is passed in, the template set will not contained anything owned by the community."""
    from concord.permission_resources.client import PermissionResourceClient
    from concord.conditionals.client import CommunityConditionalClient, PermissionConditionalClient
    permissionClient = PermissionResourceClient(actor=actor)
    commConditionalClient = CommunityConditionalClient(actor=actor)
    permConditionalClient = PermissionConditionalClient(actor=actor)

    template_set = { "community": instance_to_template(community), "owned_objects": [], 
        "permissions": [], "condition_templates": [] }

    optional_object_list = optional_object_list or []  # yay mutable defaults :/
    for owned_object in optional_object_list:
        template_set["owned_objects"].append(instance_to_template(owned_object))

    objects_to_check = [community] + optional_object_list

    while len(objects_to_check) > 0:

        current_object = objects_to_check.pop(0)  

        # Check permission
        permissions = permissionClient.get_permissions_on_object(object=current_object)
        for permission in permissions:
            template_set["permissions"].append(instance_to_template(permission))
        objects_to_check += permissions

        # Check for conditionals set on it
        if current_object.__class__.__name__ == "Community":
            commConditionalClient.set_target(target=current_object)
            govConditionTemplate = commConditionalClient.get_condition_template_for_governor()
            ownerConditionTemplate = commConditionalClient.get_condition_template_for_owner()
            for conditionTemplate in [govConditionTemplate, ownerConditionTemplate]:
                if conditionTemplate:
                    template_set["condition_templates"].append(instance_to_template(conditionTemplate))
                    objects_to_check.append(conditionTemplate)
        elif current_object.__class__.__name__ == "PermissionsItem":
            permConditionalClient.set_target(target=current_object)
            conditionTemplate = permConditionalClient.get_condition_template()
            if conditionTemplate:
                template_set["condition_templates"].append(instance_to_template(conditionTemplate))
                objects_to_check.append(conditionTemplate)

    return template_set


def create_instance_from_template(template):

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
        instance.save()
        return instance

    if template["model_type"] == "PermissionsItem":
        from concord.permission_resources.customfields import ActorList, RoleList
        template["fields"]["actors"] = ActorList(actor_list=template["fields"]["actors"])
        template["fields"]["roles"] = RoleList(role_pair_list=template["fields"]["roles"])
        # FIXME: assumes role_pair_list, want to be more flexible but that requires refactoring RoleList
        instance = model(**template["fields"])
        instance.save()
        return instance  

    if template["model_type"] in ["ConditionTemplate", "Resource", "Item"]:
        instance = model(**template["fields"])
        instance.save()
        return instance


def check_related_fields_in_map(current_template, template_map):
    """Goes through related fields in a template and checks that they're in the template map,
    returning True only if they are all present."""
    for related_field in current_template["related_fields"]:
        if related_field["related_field_old_id"].lower() not in template_map:
            # print(related_field["related_field_old_id"], " not in map")
            return False
    return True


def merge_related_fields_with_fields(current_template):
    for related_field in current_template["related_fields"]:
        for fieldname, fieldvalue in related_field["related_field_data"].items():
            current_template["fields"].update({ fieldname: fieldvalue })    
    return current_template


def get_old_id(template):
    return template["model_type"].lower() + "_" + str(template["original_pk"])


def generate_objects_from_template_set(template_set):
    """Takes in a template set and generates objects from it.  Uses template_map to keep track of
    relationships by mapping from the old object_id + content_type pairs (which were taken from the
    templated object) to the new object."""

    template_map = {}
    instances_to_return = []

    # create community and add to template map
    new_community = create_instance_from_template(template_set["community"])
    template_map[get_old_id(template_set["community"])] = new_community.pk
    instances_to_return.append(new_community)

    # we need to use a loop as dependency order of permissions & conditionals is variable
    objects_to_create = template_set["owned_objects"] + template_set["permissions"] + template_set["condition_templates"] 
    while len(objects_to_create) > 0:

        current_template = objects_to_create.pop(0)
        model = get_model_given_name(current_template["model_type"])

        all_related_fields_in_map = check_related_fields_in_map(current_template, template_map)

        if all_related_fields_in_map:

            # Fix references in template
            for related_field in current_template["related_fields"]:
                old_id_key = related_field["related_field_old_id"].lower()
                if related_field["related_field_type"] == "GenericForeignKey":
                    for key, value in related_field["related_field_data"].items():
                        if "_id" in key:
                            related_field["related_field_data"][key] = template_map[old_id_key]
                if related_field["related_field_type"] == "ConditionedObject":
                    related_field["related_field_data"]["conditioned_object"] = template_map[old_id_key]

            # update fields which reference role pairs, assuming for now a simple 1:1 community switch
            # (this will need to be updated when nested/federated communities are added)
            if current_template["model_type"] == "PermissionsItem":
                RolePair = namedtuple('RolePair', 'community_pk role_name')
                for index, rolepair in enumerate(current_template["fields"]["roles"]):
                    current_template["fields"]["roles"][index] = RolePair(community_pk=new_community.pk,
                        role_name=rolepair.role_name)
            if current_template["model_type"] == "ConditionTemplate":
                permission_dict = json.loads(current_template["fields"]["permission_data"])
                new_roles = []
                for item in permission_dict["permission_roles"]:
                    new_pair = str(new_community.pk) + "_" + item.split("_")[1]
                    new_roles.append(new_pair)
                permission_dict["permission_roles"] = new_roles
                current_template["fields"]["permission_data"] = json.dumps(permission_dict)

            # Merge related_fields back into fields
            current_template = merge_related_fields_with_fields(current_template)

            # Create instance
            model_instance = model(**current_template["fields"])

            # then add to template_map
            template_map[get_old_id(current_template)] = model_instance.pk

            instances_to_return.append(model_instance)

            # FIXME: think about how to handle actors here?

        else:
            objects_to_create.append(current_template)

    return instances_to_return


######################################################
### Converting template sets to user-viewable text ###
######################################################


def list_to_text(list_to_convert):
    """Given a list of strings, return them as list in format 'apple, banana and carrot'."""
    if len(list_to_convert) == 1:
        return list_to_convert[0]
    text = ""
    last_index = len(list_to_convert)-1
    for item in list_to_convert[:last_index]:
        text += item
    text += " and " + list_to_convert[last_index]
    return text


def roles_to_text(role_info):
    """Given a list of role pairs, returns in readable format."""

    if role_info is None:
        return ""

    role_string = "roles " if role_info > 1 else "role "

    role_list = [role_info.role_name for rolepair in role_info]

    return "everyone with " + role_string + list_to_text(role_list)


def actors_to_text(actor_info):
    """Given a list of actors, returns in a readable format."""

    if actor_info is None:
        return ""
    
    actor_string = "the individuals " if actor_info > 1 else "the individual "

    return actor_string + list_to_text(actor_info)


def roles_and_actors(role):

    text = ""

    if role["roles"] > 0:
        text += roles_to_text(role["roles"])
    
    if role["roles"] > 0 and role["actors"] > 0:
        text += " and "

    if role["actors"] > 0:
        text += actors_to_text(role["actors"])

    if role["roles"] == 0 and role["actors"] == 0:
        return "no one"
    
    return text


def community_basic_info_to_text(template_set):
    """Gets basic community info such as name, owners, governors."""
    community_fields = template_set["community"]["fields"]
    return "Community %s is owned by %s and governed by %s. " % (community_fields["name"],
        roles_and_actors(community_fields["roles"]["owners"]),
        roles_and_actors(community_fields["roles"]["governors"]))


def community_governance_info_to_text(template_set):
    """Give details of how owners/governors operate on this community."""

    owner_condition, governor_condition = None, None
    for condition in template_set["condition_templates"]:
        target = get_conditioned_object(condition)
        if target == template_set["community"]:
            if conditioning_choices == "community_owner":
                owner_condition = condition
            elif conditioning_choices == "community_governor":
                governor_condition = condition

    if template_set["community"]["foundational_permission_enabled"]:
        text = "By default, the owners of the community must approve all actions"
    else:
        text = "By default, the owners do not need to approve actions in the community"

    if owner_condition:
        text += ", " + conditions_to_text(owner_condition) + ". "
    else:
        text += ". "

    if template_set["community"]["governing_permission_enabled"]:
        text = "Unless otherwise specified, the governors of the community can take any action"
    else:
        text = "The governors of the community can take actions only when specified"

    if governor_condition:
        text += ", " + conditions_to_text(governor_condition) + ". "
    else:
        text += ". "

    return text


def community_members_to_text(template_set):
    community_fields = template_set["community"]["fields"]
    return "The members of this community are " + list_to_text(community_fields["roles"]["members"])


def community_roles_to_text(template_set):
    
    community_fields = template_set["community"]["fields"]
    
    if len(community_fields["roles"]["custom_roles"]) == 0:
        return None
    elif len(community_fields["roles"]["custom_roles"]) == 1:
        text = "There is 1 custom role in the community, "
    else:
        text = "There are %s custom roles in the community: " % str(len(community_fields["roles"]["custom_roles"]))

    text += list_to_text(community_fields["roles"]["custom_roles"].keys()) + ". "

    for role_name, role_members in community_fields["roles"]["custom_roles"].items():
        conjoin_with = " are " if len(role_members) > 1 else " is "
        text += actors_to_text(role_members) + conjoin_with + "'" + role_name + "'. ".

    return text


def get_permitted_object(permission):
    for field in permission["related_fields"]:
        if "permitted_object_content_type" in field["related_field_data"].keys():
            return field["related_field_old_id"]  # NOTE: may be wrong thing to grab here?


def get_conditioned_object(condition):
    for field in condition["related_fields"]:
        if "conditioned_object" in field["related_field_data"].keys():
            return field["related_field_old_id"]   # NOTE: may be wrong thing to grab here?


def conditions_to_text(conditions):
    from conditionals.client import PermissionConditionalClient
    text += ", "
    condition_strings = []
    for condition in conditions:
        condition_object = pcc.condition_lookup_helper(condition["fields"]["condition_type"])
        permission_data = json.loads(condition["fields"]["permission_data"])
        actors = roles_and_actors({ "roles": permission_data["permission_roles"], 
            "actors": permission_data["permission_actors"]})
        new_string = "on the condition that " + actors + " " condition_object.verb_name
        condition_strings.append(new_string)
    text += list_to_text(condition_strings)
    return text


def permission_to_text(template_set, set_target=None):
    """X has/have permission to Y of Z."""
    from actions.utils import get_state_change_object_given_name

    text = ""

    for permission in template_set["permissions"]:
        if set_target == None or set_target == get_permitted_object(permission):
            action = get_state_change_object_given_name(permission["change_type"]).description.lower()
            target = get_permitted_object(permission)
            text += roles_and_actors(permission) + " can " + action + " on " + target

            conditions_on_this_permission = []
            for condition in template_set["condition_templates"]:
                target = get_conditioned_object(condition)
                if target == permission:
                    conditions_on_this_permission.append(condition)
            
            if conditions_on_this_permission:
                text += conditions_to_text(conditions)
                
            text += ". "

            # Look for nested permissions recursively.
            text += permission_to_text(template_set, set_target=permission)
                
    return text


def owned_objects_basic_info(template_set):

    num_objects = len(template_set["owned_objects"])
    if num_objects == 0:
        return ""

    object_string = " objects. " if num_objects > 1 else " object. "

    text = "The community owns " + str(num_objects) + object_string

    obj_list = []
    for obj in template_set["owned_objects"]:
        obj_list.append(obj["model_type"].lower() + " " + obj["fields"]["name"])
    
    text += list_to_text(obj_list)

    return text


def owned_object_detailed_info(template_set, owned_object):
    object_name = owned_object["fields"]["name"]
    return permission_to_text(template_set, object_name)  # need id probably not object_name


def generate_text_from_template_set(template_set):

    text = OrderedDict()

    text.update({ "community_basic_info" : community_basic_info_to_text(template_set) }) 
    text.update({ "community_governance_info" : community_governance_info_to_text(template_set) }) 
    text.update({ "community_members_info" : community_members_to_text(template_set) }) 
    text.update({ "community_roles_info" : community_roles_to_text(template_set) })
    text.update({ "community_permissions_info" : permission_to_text(template_set) })
    text.update({ "owned_objects_basic_info" : owned_objects_basic_info(template_set) })

    for index, owned_object in enumerate(template_set["owned_objects"]):
        text.update({ "owned_object_" + str(index) : owned_object_detailed_info(template_set, owned_object) })

    return text


class HumanReadableTemplate(object):

    human_readable_text = ""

    def __init__(self, template_set):
        self.template_set = template_set
        self.human_readable_text = self.make_readable(template_set)

    def make_readable(self, template_set):
        """Creates a "plain english" paragraph/sentence with the content of the template."""
        return generate_text_from_template_set(template_set)

    def change_field(self, fieldname, newfielddata):
        """"""
        # change field in template
        # validate template, if not valid return error, otherwise change human_readable_text and return True
        pass

    def validate_template(self):
        return validate_template(self.template)


# TODO:

#   - fix set_target in permission/condition logic (not referring to exactly the same things)
#   - get names of things currently represented by IDs (possibly create dict for use by unique ID?)
#   - add unique id span when generating text

#   - figure out how to handle condition configuration info (currently not included)
#   - figure out how to handle permission configuration info (currently not included)

#   - implement change_field

#   - write tests


"""

The Community USWNT is owned by the individual 1 and governed by 1.    (((community template)))

Unless otherwise specified, the governor(s) can do whatever they like, but the owners must be 
granted specific permission to do anything.  Also, individual 1 must approve any changes they make.
(((community template, condition template)))

The community has members 1, 3 and 4.   (((community template)))

There is 1 custom role in the community, "forwards".  Individuals 3 and 4 are "forwards".
(((community template)))

Everyone with role "forwards" and the individual 10 may change the name of the community.
(((permission template)))

The community owns two objects.  It owns resource "WoSo Forum" and resource "Ticker Tape Parade Pictures".
(((resource template)))

Any member of the community may add an item to the resource "Ticker Tape Parade Pictures", on the condition
that they get approval from individual 4.  The individual 10 may remove the permission to add an item 
to the resource "Ticker Tape Parade Pictures".
(((resource template, permission template, condition template)))

*******

NOTE: How do we associate content with fields? The user will want to click an underlined section 
like ___forwards___, how do we make clear when they do this, which reference to "forwards" it should be?

When we hit a field, we generate a unique ID for it and insert it as a <span> into the text while also
keeping track of it internally.


"""