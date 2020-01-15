import json
from collections import namedtuple

from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType

from concord.permission_resources.client import PermissionResourceClient


# This structure doesn't work for related fields because keys must be unique, but you might have
# two fields pointing at the same object (usually community).

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


# FIXME: there's a lot of ways to improve this, full_clean doesn't do very much and so we aren't 
# checking all fields and we're definitely not checking that values are valid options and
# not just valid formats, but I think what we have is good enough for now

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
            ownerConditionTemplate = commConditionalClient.get_condition_info_for_owner()
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

    # TODO: create owned objects and add to template map

    # we need to use a loop to handle permissions & conditionals as dependency order between
    # the two is unpredictable
    objects_to_create = template_set["permissions"] + template_set["condition_templates"] 
    while len(objects_to_create) > 0:

        current_template = objects_to_create.pop(0)
        model = get_model_given_name(current_template["model_type"])

        # print("Attempting to create ", current_template["model_type"], current_template["original_pk"])

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

    
