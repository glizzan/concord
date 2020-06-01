from concord.actions.state_changes import Changes
from concord.permission_resources.client import PermissionResourceClient
from concord.conditionals.client import ConditionalClient


class MembershipHelper(object):

    def __init__(self, actor, community, previous_setting, new_setting, extra_data=None):

        self.mock_action_list = []

        self.actor = actor
        self.community = community
        self.permissionClient = PermissionResourceClient(actor=actor, target=community)
        self.permissionClient.mode = "mock"
        self.permission = self.get_add_member_permsision()
        self.conditionalClient = ConditionalClient(actor=actor)
        self.conditionalClient.mode = "mock"

        self.previous_setting = previous_setting
        self.new_setting = new_setting
        self.extra_data = extra_data

    def get_add_member_permsision(self):
        permissions = self.permissionClient.get_specific_permissions(change_type="concord.communities.state_changes.AddMembersStateChange")
        # Let us assume, for now, that there's only one AddMember permission possible.
        return None if len(permissions) == 0 else permissions[0]

    def get_permission_roles_and_actors(self):
        permission_roles = self.extra_data.get("permission_roles", None)
        permission_actors = self.extra_data.get("permission_actors", None)
        if not permission_roles and not permission_actors :
            raise ValueError("Must supply 'permission_actors' or 'permission_roles' when switching to invite only membership setting.")
        return permission_roles, permission_actors

    def remove_permission(self):
        action = self.permissionClient.remove_permission(item_pk=self.permission.pk)
        self.mock_action_list.append(action)
        self.permission = None

    def remove_condition_on_permission(self):
        self.conditionalClient.set_target(target=self.permission)
        condition = self.conditionalClient.get_conditions_given_targets(target_pks=[self.permission.pk])[0]
        action = self.conditionalClient.remove_condition(condition=condition)
        self.mock_action_list.append(action)

    def add_anyone_can_ask_condition(self, permission):
        self.conditionalClient.set_target(target=permission)
        condition_type = self.extra_data.get("condition_type")
        permission_data = self.extra_data.get("permission_data")
        condition_data = self.extra_data.get("condition_data", None)
        action = self.conditionalClient.add_condition(condition_type=condition_type, 
            condition_data=condition_data, permission_data=permission_data)
        self.mock_action_list.append(action)

    # Clears previous permission settings

    def remove_invite_only(self):
        self.remove_condition_on_permission()
        self.remove_permission()

    def remove_anyone_can_join(self):
        self.remove_permission()

    def remove_anyone_can_ask(self):
        self.remove_condition_on_permission()
        self.remove_permission()

    # Add new structure if membership setting type has changed
        
    def add_invite_only(self):

        # add permission
        roles, actors = self.get_permission_roles_and_actors()
        action = self.permissionClient.add_permission(permission_type=Changes.Communities.AddMembers,
            permission_roles=roles, permission_actors=actors)
        self.mock_action_list.append(action)

        # add condition to permission
        self.conditionalClient.set_target(target={"action_container_placeholder": action.unique_id })
        condition_type = self.extra_data.get("condition_type")
        permission_data = self.extra_data.get("permission_data")
        condition_data = self.extra_data.get("condition_data", dict())
        action_sourced_fields = { "condition": dict(), "permission": { 
            "approve_actors": { "replacement field": "change_parameter", "additional data" : "member_pk_list" },
            "reject_actors": { "replacement field": "change_parameter", "additional data" : "member_pk_list" } 
        } }
        action = self.conditionalClient.add_condition(condition_type="approvalcondition", condition_data=condition_data,
            action_sourced_fields=action_sourced_fields, 
            permission_data={ "approve_actors": ["action-sourced-field"], "reject_actors" : ["action-sourced-field"]})
        self.mock_action_list.append(action)

    def add_anyone_can_join(self):

        # add permission & set to anyone
        action = self.permissionClient.add_permission(permission_type=Changes.Communities.AddMembers,
            permission_configuration={"self_only": True}, anyone=True)
        self.mock_action_list.append(action)

    def add_anyone_can_ask(self):

        # add permission & set to anyone
        action = self.permissionClient.add_permission(permission_type=Changes.Communities.AddMembers,
            permission_configuration={"self_only": True}, anyone=True)
        self.mock_action_list.append(action)

        self.add_anyone_can_ask_condition(permission={"action_container_placeholder": action.unique_id })

    # Updates extra data if that's all that has changed (if the setting itself has changed, old extra data is cleared anyway)

    def update_invite_only(self):
        """Updates how 'invite only' is configured. The only customization is in the permission (what roles or actors can
        issue invites)."""
        
        roles, actors = self.get_permission_roles_and_actors()

        if self.permission.roles.get_roles() != roles:
            actions = self.permissionClient.update_roles_on_permission(role_data=roles, permission=self.permission,
                return_type="mock_action_list")
            self.mock_action_list += actions

        if self.permission.actors.pk_list != actors:
            actions = self.permissionClient.update_actors_on_permission(actor_data=actors, permission=self.permission,
                return_type="mock_action_list")
            self.mock_action_list += actions

    def update_anyone_can_ask(self):
        """Updates how 'anyone can ask' is configured. The only customization is in the condition set on the permission
        (how the ask is resolved)"""

        self.conditionalClient.set_target(target=self.permission)

        condition = self.conditionalClient.get_conditions_given_targets(target_pks=[self.permission.pk])[0]

        condition_type = self.extra_data.get("condition_type")
        if condition_type != condition.condition_data.condition_type:
            # currently, changing the condition type requires adding a new condition entirely, so we can just delete the old
            # one and add the new one with its new extra data
            self.remove_condition_on_permission()
            self.add_anyone_can_ask_condition(permission=self.permission)  # permission already exists, no need to fake it
        else:
            permission_data = self.extra_data.get("permission_data")
            condition_data = self.extra_data.get("condition_data", None)
            action = self.conditionalClient.change_condition(condition_pk=condition.pk,
                condition_data=condition_data, permission_data=permission_data)
            self.mock_action_list.append(action)

    # Called from client

    def generate_actions_to_switch_settings(self):

        if self.previous_setting != self.new_setting:

            # remove old data
            if self.previous_setting != "no new members can join":
                remove_method = getattr(self, "remove_" + self.previous_setting.replace(" ", "_"))
                remove_method()

            # add new data
            if self.new_setting != "no new members can join":
                add_method = getattr(self, "add_" + self.new_setting.replace(" ", "_"))
                add_method()

        else:

            # note - "no new members can join" and "anyone can join" do not require extra data so no need for updates
            if self.new_setting == "anyone can ask":
                self.update_anyone_can_ask()
            if self.new_setting == "invite only":
                self.update_invite_only()

        return self.mock_action_list


def get_membership_setting(actor, community):

    permissionClient = PermissionResourceClient(actor=actor, target=community)
    permissions = permissionClient.get_specific_permissions(change_type="concord.communities.state_changes.AddMembersStateChange")

    if len(permissions) == 0:
        return "no new members can join", None, None
    
    permission = permissions[0]
    # Check for condition
    conditionalClient = ConditionalClient(actor=actor)
    condition = conditionalClient.get_conditions_given_targets(target_pks=[permission.pk])
    
    if permission.anyone:

        if condition:
            return "anyone can ask", permission, condition[0]
        else:
            return "anyone can join", permission, None
    
    else:
        return "invite only", permission, condition[0]
