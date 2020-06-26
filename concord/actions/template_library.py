"""
This module contains system-created templates available to users.
"""
import json

from django.contrib.auth.models import User

from concord.actions.customfields import Template
from concord.actions.state_changes import Changes
from concord.conditionals.client import ConditionalClient
from concord.permission_resources.client import PermissionResourceClient
from concord.actions.models import TemplateModel

# FIXME: is there a way to easily (or at least, not horribly painfully) save info about what inputs of user
# supplied fields would be valid?  just the name of the field type is prob not enough, but what else is needed?


def get_or_create_superuser():
    try:
        user = User.objects.get(username="superuser")
        return user
    except:
        user = User.objects.create(username="superuser")
        return user


def create_invite_only_template():

    user = get_or_create_superuser()
    perm_client = PermissionResourceClient(actor=user)    # NOTE: This feels bad for reasons I can't explain
    perm_client.mode = "mock"

    # Step 1: add permission to addMember change
    action_1 = perm_client.add_permission(permission_type=Changes.Communities.AddMembers,
        permission_actors="{{supplied_fields.addmembers_permission_actors}}",
        permission_roles="{{supplied_fields.addmembers_permission_roles}}")
    action_1.target="{{trigger_action.target}}"

    # Step 2: add condition to permission
    permission_data = [{ "permission_type": Changes.Conditionals.Approve, 
        "permission_actors": "{{trigger_action.change.member_pk_list}}"}]   
    # NOTE: the template replacer only goes down one level, so permission_data['permission_actors] = {{ }} will
    # be unpacked in the condition template, not this top level one
    action_2 = perm_client.add_condition_to_permission(permission_pk="{{previous.0.result.pk}}", 
        condition_type="approvalcondition", permission_data=permission_data)
    action_2.target = "{{previous.0.result}}"

    # Step 3: create Template Model
    user_description = "Only the specified roles and/or users can invite members. Those members will only be " + \
        "added when the invited user approves (that is, accepts) the invite."
    template_data = Template(action_list=[action_1, action_2])
    supplied_fields = json.dumps({"addmembers_permission_roles": "PermissionRoleField", 
        "addmembers_permission_actors": "PermissionActorFeild"})
    template_model = TemplateModel.objects.create(template_data=template_data, user_description=user_description,
        scopes="membership", name="Invite Only", supplied_fields=supplied_fields, owner=user)

    return template_model