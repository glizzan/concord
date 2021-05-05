"""
This module implements the logic of the permission system.

The `has_permission` function is called by external callers, while the rest of the functions are used by
has_permission.
"""
import json

from concord.utils.helpers import Client


class Match:
    """Match is a helper class to manage info from each match. The Specific pipeline makes use of nested matches (for
    specific permissions that matched)."""

    def __init__(self, *args, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __str__(self):
        return json.dumps(self.serialize())

    def __repr__(self):
        return self.__str__()

    @property
    def unresolved(self):
        return self.status in ["not created", "waiting"]

    def rejection_message(self):
        if hasattr(self, "matches"):
            rejections = [match.rejection for match in self.matches if match.rejection]
            return rejections[0] if rejections else None
        return self.rejection if hasattr(self, "rejection") else f"does not have {self.pipeline} permission"

    def get_condition_manager(self, unresolved_only=True):
        if hasattr(self, "condition_manager") and (self.unresolved or not unresolved_only):
            return self.condition_manager

    def get_condition_managers(self, unresolved_only=True):
        if hasattr(self, "matches"):
            responses = [match.get_condition_manager(unresolved_only) for match in self.matches]
            return list(filter(None, responses))
        return [self.get_condition_manager(unresolved_only)]

    def serialize(self):
        data = {}
        for key, value in self.__dict__.items():
            data.update({key: value})
            if key == "matches":
                data[key] = [match.serialize() for match in value]
            if key == "condition_manager" and value is not None and not isinstance(value, int):
                data[key] = value.pk
        return data


############################
### Permissions Pipeline ###
############################


def determine_status(action, has_authority, has_condition, manager):
    """Quick helper method to determine a pipeline's final status."""
    if not has_authority: return "rejected"
    if not has_condition: return "approved"
    return Client().Conditional.check_condition_status(manager=manager, action=action)


def foundational_permission_pipeline(action, client, community):
    """Handles logic for foundational actions."""

    has_authority, matched_role = client.Community.has_foundational_authority(actor=action.actor)
    has_condition = community.has_condition("owner")
    manager = client.Conditional.get_condition_manager(community, "owner") if has_authority and has_condition else None
    status = determine_status(action, has_authority, has_condition, manager)

    return Match(pipeline="foundational", has_authority=has_authority, matched_role=matched_role,
                 has_condition=has_condition, condition_manager=manager, status=status)


def governing_permission_pipeline(action, client, community):
    """Checks whether the actor behind the action has governing permission."""

    has_authority, matched_role = client.Community.has_governing_authority(actor=action.actor)
    has_condition = community.has_condition("governor")
    if has_authority and has_condition:
        manager = client.Conditional.get_condition_manager(community, "governor")
    else:
        manager = None
    status = determine_status(action, has_authority, has_condition, manager)

    return Match(pipeline="governing", has_authority=has_authority, matched_role=matched_role,
                 has_condition=has_condition, condition_manager=manager, status=status)


def check_specific_permission(action, client, permission):
    """Checks whether user has a specific permission."""

    if permission.is_active:

        has_authority, matched_role = client.PermissionResource.actor_satisfies_permission(
            actor=action.actor, permission=permission)
        has_condition = permission.has_condition()
        manager = client.Conditional.get_condition_manager(permission) if has_authority and has_condition else None
        status = determine_status(action, has_authority, has_condition, manager)

    else:

        has_authority, matched_role, has_condition, manager, status = False, None, None, None, None

    return Match(pipeline="specific", has_authority=has_authority, matched_role=matched_role,
                 has_condition=has_condition, condition_manager=manager, status=status, rejection=None)


def specific_permission_pipeline(action, client):
    """Looks for specific permissions matching the change type and configuration of the action. If found, evaluates
    if actor has the permission.

    We look at permissions set on the target, then permissions set on objects the target is nested within. If at any
    point we find an approved permission, we exit and return info for it. If we reach the end without approval, we
    return any unresolved conditions we found along the way."""

    client.PermissionResource.set_target(target=action.target)
    matches = []

    # Get and check target level permissions
    for permission in client.PermissionResource.get_specific_permissions(change_type=action.change.get_change_type()):
        permission_dict = check_specific_permission(action, client, permission)
        if permission_dict.status == "approved": return permission_dict
        matches.append(permission_dict)

    # If we're still here, that means nothing matched without a condition, so now we look for nested permissions
    for nested_object in action.target.get_nested_objects():
        client.PermissionResource.set_target(target=nested_object)
        for permission in client.PermissionResource.get_specific_permissions(
                change_type=action.change.get_change_type()):
            permission_dict = check_specific_permission(action, client, permission)
            if permission_dict.status == "approved": return permission_dict
            matches.append(permission_dict)

    # If after all of this, we've only got waiting options, return them
    status = "waiting" if "waiting" in [match.status for match in matches] else "rejected"
    return Match(pipeline="specific", status=status, matches=matches)


def is_foundational(action):
    if action.__class__.__name__ == "MockAction":
        return False
    return action.change.is_foundational or action.target.foundational_permission_enabled or \
        action.change.is_conditionally_foundational(action)


def has_permission(action):
    """has_permission directs the flow of logic in the permissions pipeline.  It returns information about
    whether the action has permsision to take the action and if there are any conditions that need to be
    triggered.  It does not change the database or alter the action; instead, all information is passed back
    via a list of dictionaries (one for each pipeline).

    We preferentially enter the foundational pipeline if applicable. Otherwise we try the governing pipeline.
    If not approved by governing pipeline, we try the specific pipeline."""

    client = Client()
    community = client.Community.get_owner(owned_object=action.target)
    client.update_target_on_all(target=community)

    if is_foundational(action):
        return [foundational_permission_pipeline(action, client, community)]

    if action.target.governing_permission_enabled:
        governing_dict = governing_permission_pipeline(action, client, community)
        if governing_dict.status == "approved":
            return [governing_dict]
        else:
            return [governing_dict, specific_permission_pipeline(action, client)]

    return [specific_permission_pipeline(action, client)]


#######################
### Action Pipeline ###
#######################


def save_logs(matches, action):

    approved_through, matched_role, rejection_reason, serialized_info = None, None, None, []

    for match in matches:

        if match.status == "approved":
            approved_through, matched_role = match.pipeline, match.matched_role

        if match.status == "rejected":
            rejection_reason = match.rejection_message()

        serialized_info.append(match.serialize())

    action.add_log(log={"approved_through": approved_through, "matched_role": matched_role,
                        "rejection_reason": rejection_reason, "info": serialized_info})


def determine_action_status(matches):

    status_list = [match.status for match in matches]

    if "approved" in status_list: return "approved"  # only needs to be approved by one pipeline
    if "waiting" in status_list: return "waiting"  # if any pipeline is waiting, status is waiting
    if "rejected" in status_list: return "rejected"  # if none ar approved or waiting, they should all be rejected

    raise Exception(f"Unexpected contents for status list: {status_list}")


def create_conditions(action, matches):

    managers = []
    for match in matches:
        if match.unresolved:
            managers += match.get_condition_managers()

    Client().Conditional.create_conditions_for_action(action=action, condition_managers=managers)


def action_pipeline(action, do_create_conditions=True):

    if action.status in ["taken", "waiting"]:

        matches = has_permission(action)
        if do_create_conditions:
            create_conditions(action, matches)
        action.status = determine_action_status(matches)
        save_logs(matches, action)

    if action.status == "approved":
        result = action.change.implement_action(actor=action.actor, target=action.target, action=action)
        action.status = "implemented"

    action.save()

    return result if 'result' in locals() else None


def mock_action_pipeline(mock_action, exclude_conditional=False):

    mock_action.status = "taken"
    matches = has_permission(mock_action)
    status = determine_action_status(matches)

    if status == "approved":
        return True
    if status == "waiting" and exclude_conditional:
        return True

    return False
