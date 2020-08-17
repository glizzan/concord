"""This module contains system-created templates available to users."""
import json

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist

from concord.actions.customfields import Template
from concord.actions.utils import Changes, Client
from concord.actions.models import TemplateModel


def get_or_create_superuser():
    """Gets or create a superuser in the database."""
    try:
        user = User.objects.get(username="superuser")
        return user
    except ObjectDoesNotExist:
        user = User.objects.create(username="superuser")
        return user


def create_invite_only_template():
    """Creates a template in the membership scope where membership is invite only."""

    user = get_or_create_superuser()
    client = Client(actor=user)
    client.PermissionResource.mode = "mock"

    # Step 1: add permission to addMember change
    action_1 = client.PermissionResource.add_permission(
        permission_type=Changes().Communities.AddMembers,
        permission_actors="{{supplied_fields.addmembers_permission_actors}}",
        permission_roles="{{supplied_fields.addmembers_permission_roles}}"
    )
    action_1.target = "{{trigger_action.target}}"

    # Step 2: prepare supplied fields (see TemplateModel's get_supplied_form_fields method for syntax guidance)
    supplied_fields = json.dumps({
        "addmembers_permission_roles": ["RoleListField", {"label": "What roles can invite new members?"}],
        "addmembers_permission_actors": ["ActorListField", {"label": "What actors can invite new members?"}]
    })

    # Step 3: create Template Model
    user_description = "Only the specified roles and/or users can invite members."
    template_data = Template(action_list=[action_1])  # Template(action_list=[action_1, action_2])

    template_model = TemplateModel.objects.create(
        template_data=template_data, user_description=user_description, scopes=json.dumps(["membership"]),
        name="Invite Only", supplied_fields=supplied_fields, owner=user
    )

    return template_model


def create_anyone_can_request_template():
    """Creates an template in the membership scope where anyone can request to join."""

    user = get_or_create_superuser()
    client = Client(actor=user)
    client.PermissionResource.mode = "mock"

    # Step 1: add addMember permission with anyone set to True and self_only set to True
    action_1 = client.PermissionResource.add_permission(
        permission_type=Changes().Communities.AddMembers, anyone=True, permission_configuration={"self_only": True}
    )
    action_1.target = "{{trigger_action.target}}"

    # Step 2: add condition to permission
    permission_data = [{
        "permission_type": Changes().Conditionals.Approve,
        "permission_actors": "{{supplied_fields.approve_permission_actors}}",
        "permission_roles": "{{supplied_fields.approve_permission_roles}}"
    }]
    action_2 = client.PermissionResource.add_condition_to_permission(
        permission_pk="{{previous.0.result.pk}}", condition_type="approvalcondition", permission_data=permission_data
    )
    action_2.target = "{{previous.0.result}}"

    # Step 3: prepare supplied fields (see TemplateModel's get_supplied_form_fields method for syntax guidance)
    supplied_fields = json.dumps({
        "approve_permission_roles": ["RoleListField", {"label": "What roles can approve requests to join?"}],
        "approve_permission_actors": ["ActorListField", {"label": "What actors can approve requests to join?"}]
    })

    # Step 4: create Template Model
    user_description = "Anyone can request to join, but only specified roles and actors can approve requests."
    template_data = Template(action_list=[action_1, action_2])

    template_model = TemplateModel.objects.create(
        template_data=template_data, user_description=user_description, scopes=json.dumps(["membership"]),
        name="Anyone Can Request to Join", supplied_fields=supplied_fields, owner=user
    )

    return template_model


def create_anyone_can_join_template():
    """Creates a template in the membership scope where anyone can ask to join."""

    user = get_or_create_superuser()
    client = Client(actor=user)
    client.PermissionResource.mode = "mock"

    # Step 1: add addMember permission with anyone set to True and self_only set to True
    action_1 = client.PermissionResource.add_permission(
        permission_type=Changes().Communities.AddMembers, anyone=True, permission_configuration={"self_only": True}
    )
    action_1.target = "{{trigger_action.target}}"

    # Step 4: create Template Model
    user_description = "Anyone can join. No approval from anyone inside the group is needed."
    template_data = Template(action_list=[action_1])

    template_model = TemplateModel.objects.create(
        template_data=template_data, user_description=user_description, scopes=json.dumps(["membership"]),
        name="Anyone Can Join", supplied_fields=json.dumps({}), owner=user
    )

    return template_model


def create_all_templates():
    """Creates all templates at once."""

    create_invite_only_template()
    create_anyone_can_request_template()
    create_anyone_can_join_template()
