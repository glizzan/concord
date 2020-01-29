import json, random
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


def roles_to_text(role_info):
    """Given a list of role pairs, returns in readable format."""

    if role_info is None:
        return ""

    role_string = "roles " if len(role_info) > 1 else "role "

    role_list = [rolepair.role_name for rolepair in role_info]

    return "everyone with " + role_string + list_to_text(role_list)


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


def add_span_id(model_template, field_name, inner_content):
    """Adds span id to a field.  Not currently being used."""
    span_id = get_old_id(model_template) + "-" + field_name
    return "<span id='" + span_id + "'>" + inner_content + "</span>"


def community_basic_info_to_text_with_span_ids(template_set):
    """Gets basic community info such as name, owners, governors. Not currently being used."""

    name_field = add_span_id(model_template=template_set["community"], field_name="name", 
        inner_content=template_set["community"]["fields"]["name"])
    owners_field = add_span_id(model_template=template_set["community"], field_name="owners", 
        inner_content=roles_and_actors(template_set["community"]["fields"]["roles"]["owners"]))
    governors_field = add_span_id(model_template=template_set["community"], field_name="governors",
        inner_content=roles_and_actors(template_set["community"]["fields"]["roles"]["governors"]))

    return "Community %s is owned by %s and governed by %s. " % (name_field, owners_field, governors_field)


def community_basic_info_to_text(template_set):
    """Gets basic community info such as name, owners, governors."""

    name_field = template_set["community"]["fields"]["name"]
    owners_field = roles_and_actors(template_set["community"]["fields"]["roles"]["owners"])
    governors_field = roles_and_actors(template_set["community"]["fields"]["roles"]["governors"])

    return "Community %s is owned by %s and governed by %s. " % (name_field, owners_field, governors_field)



def community_governance_info_to_text(template_set):
    """Give details of how owners/governors operate on this community."""

    owner_condition, governor_condition = None, None

    for condition in template_set["condition_templates"]:

        old_id_of_target = get_conditioned_object(condition).lower()
        old_id_of_community = get_old_id(template_set["community"]).lower()

        if old_id_of_target == old_id_of_community:
            if condition["fields"]["conditioning_choices"] == "community_owner":
                owner_condition = condition
            elif condition["fields"]["conditioning_choices"] == "community_governor":
                governor_condition = condition
    
    text = ""

    if template_set["community"]["fields"]["foundational_permission_enabled"]:
        text += "By default, the owners of the community must approve all actions"
    else:
        text += "By default, the owners do not need to approve actions in the community"

    if owner_condition:
        text += ", " + conditions_to_text([owner_condition]) + ". "
    else:
        text += ". "

    if template_set["community"]["fields"]["governing_permission_enabled"]:
        text += "Unless otherwise specified, the governors of the community can take any action"
    else:
        text += "The governors of the community can take actions only when specified"

    if governor_condition:
        text += ", " + conditions_to_text([governor_condition]) + ". "
    else:
        text += ". "

    return text


def community_members_to_text(template_set):
    community_fields = template_set["community"]["fields"]
    return "The members of this community are " + list_to_text(community_fields["roles"]["members"]) + ". "


def community_roles_to_text(template_set):
    
    community_fields = template_set["community"]["fields"]
    
    if len(community_fields["roles"]["custom_roles"]) == 0:
        return None
    elif len(community_fields["roles"]["custom_roles"]) == 1:
        text = "There is 1 custom role in the community, "
    else:
        text = "There are %s custom roles in the community: " % str(len(community_fields["roles"]["custom_roles"]))

    custom_role_names = list(community_fields["roles"]["custom_roles"].keys())
    text += list_to_text(custom_role_names) + ". "

    for role_name, role_members in community_fields["roles"]["custom_roles"].items():
        conjoin_with = " are " if len(role_members) > 1 else " is "
        new_text = actors_to_text(role_members) + conjoin_with + "'" + role_name + "'. "
        text += capitalize_first_letter(new_text)

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
    """Takes a list of conditions and turns them into text."""
    
    from conditionals.client import PermissionConditionalClient
    pcc = PermissionConditionalClient(actor="system")

    condition_strings = []
    for condition in conditions:
        condition_object = pcc.condition_lookup_helper(lookup_string=condition["fields"]["condition_type"])
        permission_data = json.loads(condition["fields"]["permission_data"])
        actors = roles_and_actors({ "roles": permission_data["permission_roles"], 
            "actors": permission_data["permission_actors"]})
        new_string = "on the condition that " + actors + " " + condition_object.verb_name
        condition_strings.append(new_string)
    return list_to_text(condition_strings)


def permission_to_text(template_set, set_target=None):
    """X has/have permission to Y of Z."""
    from actions.utils import get_state_change_object_given_name

    text = ""

    for permission in template_set["permissions"]:

        if set_target == None or set_target == get_permitted_object(permission):

            action = get_state_change_object_given_name(permission["fields"]["change_type"]).description.lower()
            target = get_permitted_object(permission)
            new_text = roles_and_actors(permission["fields"]) + " can " + action + " for " + target
            text += capitalize_first_letter(new_text)

            conditions_on_this_permission = []
            for condition in template_set["condition_templates"]:
                if get_conditioned_object(condition).lower() == get_old_id(permission).lower():
                    conditions_on_this_permission.append(condition)
            
            if conditions_on_this_permission:
                text += ", " + conditions_to_text(conditions_on_this_permission)
                
            text += ". "

            # Look for nested permissions recursively.
            text += permission_to_text(template_set, set_target=get_old_id(permission))
                
    return text


def owned_objects_basic_info(template_set):

    num_objects = len(template_set["owned_objects"])
    if num_objects == 0:
        return ""

    object_string = " objects, " if num_objects > 1 else " object, "

    text = "The community owns " + str(num_objects) + object_string

    obj_list = []
    for obj in template_set["owned_objects"]:
        obj_list.append(obj["model_type"].lower() + " " + obj["fields"]["name"])
    
    text += list_to_text(obj_list) + ". "

    return text


def generate_text_from_template_set(template_set):

    text = OrderedDict()

    old_community_id = get_old_id(template_set["community"])

    text.update({ "community_basic_info" : community_basic_info_to_text(template_set) }) 
    text.update({ "community_governance_info" : community_governance_info_to_text(template_set) }) 
    text.update({ "community_members_info" : community_members_to_text(template_set) }) 
    text.update({ "community_roles_info" : community_roles_to_text(template_set) })
    text.update({ "community_permissions_info" : permission_to_text(template_set, set_target=old_community_id) })
    text.update({ "owned_objects_basic_info" : owned_objects_basic_info(template_set) })

    for index, owned_object in enumerate(template_set["owned_objects"]):
        text.update({ "owned_object_" + str(index) : permission_to_text(template_set, get_old_id(owned_object)) })

    return text


def change_field_in_template(template_set, model_type, old_pk, fieldname, newfielddata):
    """This is super limited, because we're making tons of assumptions about the data being passed in.

    - a template set, likely generated from a pk corresponding to where the original template is stored 
        as a Django model in the DB
    - the type of the model the changed field is on (community, owned_objects, permissions, or 
        conditiontemplates), so we can find it in the template set 
    - the pk of the model the changed field is on, so we can find it in the template set
    - the name of the field being changed, possibly as a span_id that needs to be reconstructed, which
        we assume for now is NOT a related field
    - the new field data, which will def need to be validated for format, which we're not doing here

    We'll need to refactor this soon, but it probably makes sense to do so after we've created a 
    template model in the DB.

    """

    if model_type == "community":
        template_set["community"]["fields"][fieldname] = newfielddata
    else:
        for item in template_set[model_type]:
            if item["original_pk"] == old_pk:
                item[fieldname] = newfielddata


"""
NOTE: for documentation somewhere


# Upon reflection, I think it's reasonable to ask people editing templates to deal more directly
# with the data structure - this is a power user tool anyway.  We can create a user interface to do 
# edit the Englishified templates later.

# This means we do not need to insert span IDs into the template texts.  For the record, this is the
# logic of the span_ids, implemented above in a couple of unused functions:
#                                                modeltypeOfModel_pkOfModel-[fieldname]
"""