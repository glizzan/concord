"""
This module implements the logic of the permission system.

The `has_permission` function is called by external callers, while the rest of the functions are used by
has_permission.
"""
import json

from concord.utils.helpers import Client


############################
### Permissions Pipeline ###
############################


def determine_status(action, has_authority, has_condition, manager):
    """Quick helper method to determine a pipeline's final status."""
    if not has_authority: return "rejected"
    if not has_condition: return "approved"
    return Client().Conditional.check_condition_status(manager=manager, action=action)


def check_configuration(action, permission):
    """Given a permission, check whether the action matches the configuration."""

    # Does permission.configuration contain keys?  If not, action passes by default.
    if not json.loads(permission.configuration):
        return True, None

    # Call check_configuration on the state_change, passing in the permission configuration data, and return result.
    return action.change.check_configuration(action, permission)


def foundational_permission_pipeline(action, client, community):
    """Handles logic for foundational actions."""

    has_authority, matched_role = client.Community.has_foundational_authority(actor=action.actor)
    has_condition = community.has_condition("owner")
    manager = client.Conditional.get_condition_manager(community, "owner") if has_authority and has_condition else None
    status = determine_status(action, has_authority, has_condition, manager)

    return {
        "pipeline": "foundational", "has_authority": has_authority, "matched_role": matched_role,
        "has_condition": has_condition, "condition_manager": manager, "status": status
    }


def governing_permission_pipeline(action, client, community):
    """Checks whether the actor behind the action has governing permission."""

    has_authority, matched_role = client.Community.has_governing_authority(actor=action.actor)
    has_condition = community.has_condition("governor")
    manager = client.Conditional.get_condition_manager(community, "governor") if has_authority and has_condition else None
    status = determine_status(action, has_authority, has_condition, manager)

    return {
        "pipeline": "governing", "has_authority": has_authority, "matched_role": matched_role,
        "has_condition": has_condition, "condition_manager": manager, "status": status
    }


def check_specific_permission(action, client, permission):
    """Checks whether user has a specific permission."""

    passes_configuration, rejection_message = check_configuration(action, permission)

    if permission.is_active and passes_configuration:

        has_authority, matched_role = client.PermissionResource.actor_satisfies_permission(
            actor=action.actor, permission=permission)
        has_condition = permission.has_condition()
        manager = client.Conditional.get_condition_manager(permission) if has_authority and has_condition else None
        status = determine_status(action, has_authority, has_condition, manager)

    else:

        has_authority, matched_role, has_condition, manager, status = False, None, None, None, None

    return {
        "pipeline": "specific", "has_authority": has_authority, "matched_role": matched_role,
        "has_condition": has_condition, "condition_manager": manager, "status": status, "rejection": rejection_message
    }


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
        if permission_dict["status"] == "approved": return permission_dict
        matches.append(permission_dict)

    # If we're still here, that means nothing matched without a condition, so now we look for nested permissions
    for nested_object in action.target.get_nested_objects():
        client.PermissionResource.set_target(target=nested_object)
        for permission in client.PermissionResource.get_specific_permissions(change_type=action.change.get_change_type()):
            permission_dict = check_specific_permission(action, client, permission)
            if permission_dict["status"] == "approved": return permission_dict
            matches.append(permission_dict)

    # If after all of this, we've only got waiting options, return them
    status = "waiting" if "waiting" in [match["status"] for match in matches] else "rejected"
    return {"pipeline": "specific", "status": status, "matches": matches}


def is_foundational(action):
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

    if is_foundational(action): return [foundational_permission_pipeline(action, client, community)]

    if action.target.governing_permission_enabled:
        governing_dict = governing_permission_pipeline(action, client, community)
        if governing_dict["status"] == "approved": return [governing_dict]

    return [governing_dict, specific_permission_pipeline(action, client)]


#######################
### Action Pipeline ###
#######################


def save_logs(info, action):

    approved_through, matched_role, rejection_reason = None, None, None

    for item in info:

        if item["status"] == "approved":
            approved_through = item["pipeline"]
            matched_role = item["matched_role"]

        if item.get("rejection", None): rejection_reason = item["rejection"]

        item["condition_manager"] = item["condition_manager"].pk if item.get("condition_manager", None) else None
        for match in item.get("matches", []):
            if match.get("rejection", None): rejection_reason = match["rejection"]
            match["condition_manager"] = match["condition_manager"].pk if match.get("condition_manager", None) else None

    action.add_log(log={"approved_through": approved_through, "matched_role": matched_role,
                        "rejection_reason": rejection_reason, "info": info})


def determine_action_status(info):

    status_list = [item["status"] for item in info]

    if "approved" in status_list: return "approved"  # only needs to be approved by one pipeline
    if "waiting" in status_list: return "waiting"  # if any pipeline is waiting, status is waiting
    if "rejected" in status_list: return "rejected"  # if none ar approved or waiting, they should all be rejected

    raise Exception(f"Unexpected contents for status list: {status_list}")


def create_conditions(action, info):

    managers = []
    for info_dict in info:
        if info_dict["pipeline"] in ["foundational", "governing"] and info_dict["status"] in ["not created", "waiting"]:
            managers.append(info_dict["condition_manager"])
        if info_dict["pipeline"] == "specific" and info_dict["status"] in ["not created", "waiting"]:
            for item in info_dict["matches"]:
                if item["pipeline"] == "specific" and item["status"] in ["not created", "waiting"]:
                    managers.append(item["condition_manager"])

    Client().Conditional.create_conditions_for_action(action=action, condition_managers=managers)


def action_pipeline(action, do_create_conditions=True):

    if action.status in ["taken", "waiting"]:

        info = has_permission(action)
        if do_create_conditions:
            create_conditions(action, info)
        action.status = determine_action_status(info)
        save_logs(info, action)

    if action.status == "approved":
        result = action.change.implement(actor=action.actor, target=action.target, action=action)
        action.status = "implemented"

    action.save()

    return result if 'result' in locals() else None


def mock_action_pipeline(mock_action, exclude_conditional=False):

    mock_action.status = "taken"
    info = has_permission(mock_action)
    status = determine_action_status(info)

    if status == "approved": return True
    if status == "waiting" and not exclude_conditional: return True

    return False
