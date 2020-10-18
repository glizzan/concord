"""This module contains system-created templates available to users."""
import json
from abc import ABCMeta, abstractmethod

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist

from concord.actions.customfields import Template
from concord.actions.utils import Changes, Client
from concord.actions.models import TemplateModel


class TemplateLibraryObject(metaclass=ABCMeta):
    """Abstract parent class used to create templates."""
    is_template_object = True
    default_action_target = "{{context.action.target}}"
    name: str
    description: str
    scopes: list
    supplied_fields: dict = dict()

    @abstractmethod
    def get_action_list(self):
        """Returns a list of actions, must be implemented by subclass."""

    def get_and_process_action_list(self):
        """If any actions lack a target, replaces them with default_action_target."""
        actions = self.get_action_list()
        for action in actions:
            if not action.target:
                if self.default_action_target:
                    action.target = self.default_action_target
                else:
                    raise ValueError(
                        "Must provide targets for all of template's mock actions, or set default_action_target.")
        return actions

    def return_if_exists(self):
        """Returns template model instance if one with this object's name already exists."""
        template = TemplateModel.objects.filter(name=self.name)
        return template[0] if template else None

    def get_description(self):
        """Strips newlines from description so user can create provide description via multiline string."""
        if not self.description:
            raise NotImplementedError("Must provide a description in description attribute or get_description method")
        return " ".join([line.rstrip().lstrip() for line in self.description.splitlines()])

    def get_superuser(self):
        """Gets or create a superuser in the database."""
        try:
            user = User.objects.get(username="superuser")
            return user
        except ObjectDoesNotExist:
            user = User.objects.create(username="superuser")
            return user

    def get_client(self):
        """Get client."""
        client = Client(actor=self.get_superuser())
        client.set_mode_for_all("mock")
        return client

    def create_template_model(self):
        """Creates the model in DB given above."""
        if self.name is None:
            raise NotImplementedError(f"Must specify name of template library class {self.__class__.__name__}.")
        if self.description is None:
            raise NotImplementedError(f"Must specify description for template library class {self.name}.")
        if self.scopes is None:
            raise NotImplementedError(f"Must specify scopes for template library class {self.name}.")
        if len(self.get_action_list()) < 1:
            raise NotImplementedError(f"get_action_list() must return at least one action for template {self.name}.")

        template_data = Template(action_list=self.get_and_process_action_list())
        scopes = json.dumps(self.scopes)
        supplied_fields = json.dumps(self.supplied_fields if self.supplied_fields else {})
        return TemplateModel.objects.create(
            template_data=template_data, user_description=self.get_description(), scopes=scopes,
            name=self.name, supplied_fields=supplied_fields, owner=self.get_superuser())


class SimpleListLimitedMemberTemplate(TemplateLibraryObject):
    """Creates permissions on a simplelist where members can add rows to the list without condition but can only
    edit or delete rows, or edit the list itself, if the creator approves. Only the creator can delete the list."""
    name = "Limited Member Permissions"
    scopes = ["simplelist"]
    description = """This template allows members to add rows to the list without needing approval. To edit or
                        delete rows, or to edit the list itself, the creator must approve. Only the creator may
                        delete the list."""

    def get_action_list(self):

        client = self.get_client()

        # Step 1: give members permission to add row
        action_1 = client.PermissionResource.add_permission(
            permission_roles=['members'], permission_type=Changes().Resources.AddRow)

        # Step 2: give members permission to edit list
        action_2 = client.PermissionResource.add_permission(
            permission_roles=['members'], permission_type=Changes().Resources.EditList)

        # Step 3: set approval condition on permission
        permission_data = [{"permission_type": Changes().Conditionals.Approve,
                            "permission_actors": "{{nested:context.simplelist.creator||to_pk_in_list}}"},
                           {"permission_type": Changes().Conditionals.Reject,
                            "permission_actors": "{{nested:context.simplelist.creator||to_pk_in_list}}"}]
        action_3 = client.Conditional.add_condition(
            condition_type="approvalcondition", permission_data=permission_data
        )
        action_3.target = "{{previous.1.result}}"

        # Step 4: give members permission to edit row
        action_4 = client.PermissionResource.add_permission(
            permission_roles=['members'], permission_type=Changes().Resources.EditRow)

        # Step 5: set approval condition on permission
        action_5 = client.Conditional.add_condition(
            condition_type="approvalcondition", permission_data=permission_data)
        action_5.target = "{{previous.3.result}}"

        # Step 6: give members permission to edit row
        action_6 = client.PermissionResource.add_permission(
            permission_roles=['members'], permission_type=Changes().Resources.DeleteRow)

        # Step 7: set approval condition on permission
        action_7 = client.Conditional.add_condition(
            condition_type="approvalcondition", permission_data=permission_data)
        action_7.target = "{{previous.5.result}}"

        return [action_1, action_2, action_3, action_4, action_5, action_6, action_7]


class CommunityMembersAndBoardTemplate(TemplateLibraryObject):
    """Creates a template where all members are owners, with a board acting as governors. Owners must vote to make
    any changes, so governors are added and removed by a vote of all members."""
    name = "Members and Board"
    scopes = ["community"]
    supplied_fields = {
        "initial_board_members":
            ["ActorListField", {"label": "Who should the initial board members be?", "required": False}],
        "initial_membership_admins":
            ["ActorListField", {"label": "Who should the initial membership admins be?", "required": False}],
    }
    description = """This template gives all members ownership powers, which they exercise through voting. It also
                     creates a 'board' role as governors. Anyone can request to join, but they must be approved by
                     a member of the board or a new role called 'membership admin'."""

    def get_action_list(self):

        client = self.get_client()

        # Step 1: create role which will be governing role
        action_1 = client.Community.add_role(role_name="board")

        # Step 2: add initial people to board
        action_2 = client.Community.add_people_to_role(
            role_name="board", people_to_add="{{supplied_fields.initial_board_members}}")

        # Step 3: make 'board' role a governorship role
        action_3 = client.Community.add_governor_role(governor_role="board")

        # Step 4: make members an ownership role
        action_4 = client.Community.add_owner_role(owner_role="members")

        # Step 5: add vote condition to ownership role
        permission_data = [{"permission_type": Changes().Conditionals.AddVote, "permission_roles": ["owners"]}]
        action_5 = client.Conditional.add_condition(
            condition_type="votecondition", leadership_type="owner", permission_data=permission_data)

        # Step 6: create role 'membership admins'
        action_6 = client.Community.add_role(role_name="membership admins")

        # Step 7: add initial people to 'membership admins'
        action_7 = client.Community.add_people_to_role(
            role_name="membership admins", people_to_add="{{supplied_fields.initial_membership_admins}}")

        # Step 8: add addMember permission with anyone set to True and self_only set to True
        action_8 = client.PermissionResource.add_permission(
            permission_type=Changes().Communities.AddMembers, anyone=True, permission_configuration={"self_only": True}
        )

        # Step 9: add condition to that permission
        permission_data = [{
            "permission_type": Changes().Conditionals.Approve,
            "permission_roles": ["membership admins"]
        }]
        action_9 = client.Conditional.add_condition(
            condition_type="approvalcondition", permission_data=permission_data)
        action_9.target = "{{previous.7.result}}"

        return [action_1, action_2, action_3, action_4, action_5, action_6, action_7, action_8, action_9]


class CommunityCoreTeamTemplate(TemplateLibraryObject):
    """Creates a template with core team as owners with an approval condition for foundational actions.
    Core team members are also set as governor. Also incldues 'anyone can join' permission."""
    name = "Core Team"
    scopes = ["community"]
    supplied_fields = {
        "initial_core_team_members":
            ["ActorListField", {"label": "Who should the initial members of the core team be?", "required": True}]
    }
    description = """This template is a good fit for small teams with high trust. It creates a 'core team' role
                     which is given both owner and governor powers. In order for core team members to use their
                     ownership authority one other core team member must approve. The template also allows anyone
                     to join the community."""

    def get_action_list(self):

        client = self.get_client()

        # Step 1: add 'core team'
        action_1 = client.Community.add_role(role_name="core team")

        # Step 2: make initial people into 'core team'
        action_2 = client.Community.add_people_to_role(
            role_name="core team", people_to_add="{{supplied_fields.initial_core_team_members}}")

        # Step 3: make 'core team' role an ownership role
        action_3 = client.Community.add_owner_role(owner_role="core team")

        # Step 4: make 'core team' role an governorship role
        action_4 = client.Community.add_governor_role(governor_role="core team")

        # Step 5: add approval condition to ownership role
        permission_data = [{"permission_type": Changes().Conditionals.Approve, "permission_roles": ["core team"]},
                           {"permission_type": Changes().Conditionals.Reject, "permission_roles": ["core team"]}]
        action_5 = client.Conditional.add_condition(
            condition_type="approvalcondition", leadership_type="owner", permission_data=permission_data)

        # Step 6: add anyone can join permission
        action_6 = client.PermissionResource.add_permission(
            permission_type=Changes().Communities.AddMembers, anyone=True, permission_configuration={"self_only": True})

        return [action_1, action_2, action_3, action_4, action_5, action_6]


class CommunityVotingMembersTemplate(TemplateLibraryObject):
    """Creates a template with voting members as owners with a vote condition and the creator as
    governor. Also includes 'anyone can join' permission."""
    name = "Voting members"
    scopes = ["community"]
    supplied_fields = {
        "initial_voting_members":
            ["ActorListField", {"label": "Who should the initial voting members be?", "required": True}],
        "allow_abstain":
            ["BooleanField", {"label": "Should voting members be allowed to cast 'abstain' votes?"}],
        "require_majority":
            ["BooleanField",
             {"label": "Should the owners' vote require a majority to pass? If no, it will require a plurality."}],
        "publicize_votes":
            ["BooleanField", {"label": "Should voting members' votes be public?"}],
        "voting_period":
            ["IntegerField", {"label": "How long, in hours, should the voting period be? (Default is one week.)"}]
    }
    description = """Creates a 'voting members' role and makes them owners of the community. To take any action,
                      these voting members must vote. Governors are left as-is. Anyone can join the community."""

    def get_action_list(self):

        client = self.get_client()

        # Step 1: add 'voting member'
        action_1 = client.Community.add_role(role_name="voting members")
        action_1.target = "{{context.action.target}}"

        # Step 2: make initial people into 'voting members'
        action_2 = client.Community.add_people_to_role(
            role_name="voting members", people_to_add="{{supplied_fields.initial_voting_members}}")
        action_2.target = "{{context.action.target}}"

        # Step 3: make 'voting member' role an ownership role
        action_3 = client.Community.add_owner_role(owner_role="voting members")
        action_3.target = "{{context.action.target}}"

        # Step 4: add vote condition to ownership role
        permission_data = [{"permission_type": Changes().Conditionals.AddVote,
                            "permission_roles": ["voting members"]}]
        condition_data = {"allow_abstain": "{{supplied_fields.allow_abstain}}",
                          "require_majority": "{{supplied_fields.require_majority}}",
                          "publicize_votes": "{{supplied_fields.publicize_votes}}",
                          "voting_period": "{{supplied_fields.voting_period}}"}
        action_4 = client.Conditional.add_condition(
            condition_type="votecondition", leadership_type="owner", condition_data=condition_data,
            permission_data=permission_data)
        action_4.target = "{{context.action.target}}"

        # Step 5: add anyone can join permission
        action_5 = client.PermissionResource.add_permission(
            permission_type=Changes().Communities.AddMembers, anyone=True, permission_configuration={"self_only": True})
        action_5.target = "{{context.action.target}}"

        return [action_1, action_2, action_3, action_4, action_5]


class InviteOnlyMembershipTemplate(TemplateLibraryObject):
    """Creates a template in the membership scope where membership is invite only."""
    name = "Invite Only"
    description = """Only the specified roles and/or users can invite members. Invited members must approve before
                     they're added."""
    scopes = ["membership"]
    supplied_fields = {
        "addmembers_permission_roles": ["RoleListField", {"label": "What roles can invite new members?"}],
        "addmembers_permission_actors": ["ActorListField", {"label": "What actors can invite new members?"}]
    }

    def get_action_list(self):

        client = self.get_client()

        # Step 1: add permission to addMember change
        action_1 = client.PermissionResource.add_permission(
            permission_type=Changes().Communities.AddMembers,
            permission_actors="{{supplied_fields.addmembers_permission_actors}}",
            permission_roles="{{supplied_fields.addmembers_permission_roles}}"
        )
        action_1.target = "{{context.action.target}}"

        # Step 2: add condition to permission
        permission_data = [{"permission_type": Changes().Conditionals.Approve,
                            "permission_actors": "{{nested:context.action.change.member_pk_list}}"},
                           {"permission_type": Changes().Conditionals.Reject,
                            "permission_actors": "{{nested:context.action.change.member_pk_list}}"}]
        action_2 = client.Conditional.add_condition(
            condition_type="approvalcondition", permission_data=permission_data)
        action_2.target = "{{previous.0.result}}"

        return [action_1, action_2]


class AnyoneCanRequestMembershipTemplate(TemplateLibraryObject):
    """Creates an template in the membership scope where anyone can request to join."""
    name = "Anyone Can Request to Join"
    description = "Anyone can request to join, but only specified roles and actors can approve requests."
    scopes = ["membership"]
    supplied_fields = {
        "approve_permission_roles": ["RoleListField", {"label": "What roles can approve requests to join?"}],
        "approve_permission_actors": ["ActorListField", {"label": "What actors can approve requests to join?"}]
    }

    def get_action_list(self):

        client = self.get_client()

        # Step 1: add addMember permission with anyone set to True and self_only set to True
        action_1 = client.PermissionResource.add_permission(
            permission_type=Changes().Communities.AddMembers, anyone=True, permission_configuration={"self_only": True}
        )
        action_1.target = "{{context.action.target}}"

        # Step 2: add condition to permission
        permission_data = [{
            "permission_type": Changes().Conditionals.Approve,
            "permission_actors": "{{supplied_fields.approve_permission_actors}}",
            "permission_roles": "{{supplied_fields.approve_permission_roles}}"
        }]
        action_2 = client.Conditional.add_condition(
            condition_type="approvalcondition", permission_data=permission_data
        )
        action_2.target = "{{previous.0.result}}"

        return [action_1, action_2]


class AnyoneCanJoinMembershipTemplate(TemplateLibraryObject):
    """Creates a template in the membership scope where anyone can ask to join."""
    name = "Anyone Can Join"
    description = "Anyone can join. No approval from anyone inside the group is needed."
    scopes = ["membership"]

    def get_action_list(self):

        client = self.get_client()

        # Step 1: add addMember permission with anyone set to True and self_only set to True
        action_1 = client.PermissionResource.add_permission(
            permission_type=Changes().Communities.AddMembers, anyone=True, permission_configuration={"self_only": True}
        )
        action_1.target = "{{context.action.target}}"

        return [action_1]


class CommenterRoleTemplate(TemplateLibraryObject):
    """Creates a role with the ability to add comments throughout the community, as well as edit and delete
    their own comments."""
    name = "Commenters"
    description = """Creates a 'commenter' role with ability to add comments, as well as to edit and delete their
                     own comments."""
    scopes = ["role"]
    default_action_target = "{{context.group}}"

    def get_action_list(self):

        client = self.get_client()

        # Step 1: create commenter role
        action_1 = client.Community.add_role(role_name="commenters")

        # Step 2: set permissions
        action_2 = client.PermissionResource.add_permission(
            permission_type=Changes().Resources.AddComment, permission_roles=["commenters"])
        action_3 = client.PermissionResource.add_permission(
            permission_type=Changes().Resources.EditComment, permission_roles=["commenters"],
            permission_configuration={"commenter_only": True})
        action_4 = client.PermissionResource.add_permission(
            permission_type=Changes().Resources.DeleteComment, permission_roles=["commenters"],
            permission_configuration={"commenter_only": True})

        return [action_1, action_2, action_3, action_4]
