"""
This module contains functions which take in various Concord objects and return human-readable English descriptions.
"""

import copy


########################
### Helper functions ###
########################

# Called mostly inside this file


def is_plural(new_list):
    return True if len(new_list) > 1 else False


def capitalize_first_letter(text):
    """Helper method which capitalizes first letter in a string."""
    return text[0].upper() + text[1:]


def list_to_text(list_to_convert):
    """Given a list with items that can be turned into strings, return them as text in format
    'apple, banana and carrot'."""
    
    list_to_convert = copy.deepcopy(list_to_convert)   # since we're mutating the list, need to deep copy it

    if len(list_to_convert) == 0:
        return ""
    if len(list_to_convert) == 1:
        return str(list_to_convert[0])
    
    last_item = list_to_convert.pop(-1)   # pop is a mutation
    text = ", ".join([str(item) for item in list_to_convert])
    text += " and " + str(last_item)
    return text


def roles_to_text(roles):
    """Given a list of roles, returns them in format 'everyone with role 'banana''."""

    if roles is None:
        return ""

    role_string = "roles " if len(roles) > 1 else "role "

    return "those with " + role_string + list_to_text(roles)


def actors_to_text(actor_info):
    """Given a list of actors, returns in a readable format."""

    if actor_info is None:
        return ""
    
    actor_string = "individuals " if len(actor_info) > 1 else "individual "

    return actor_string + list_to_text(actor_info)


def replaceable_field_check(value):
    """Checks for replaceable fields and parses & returns their content if found.

    Note that is is pretty brittle (the remove change has member_pk_list as a param too,
    what if we're removing people with this action?), and should be replaced by some kind 
    of text_utils function."""

    if type(value) == str and value[0:2] == "{{" and value[-2:] == "}}":
        command = value.replace("{{", "").replace("}}", "").strip()
        tokens = command.split(".")
    
        if tokens[0] == "trigger_action" and tokens[1] == "change" and tokens[2] == "member_pk_list":
            return True, "users added by the action"   

    return False, value


def roles_and_actors(role_and_actor_dict):

    text = ""

    if len(role_and_actor_dict["roles"]) > 0:
        replaced, response = replaceable_field_check(role_and_actor_dict["roles"])
        if replaced:
            text += response
        else:
            text += roles_to_text(role_and_actor_dict["roles"])
    
    if len(role_and_actor_dict["roles"]) > 0 and len(role_and_actor_dict["actors"]) > 0:
        text += " and "

    if len(role_and_actor_dict["actors"]) > 0:
        replaced, response = replaceable_field_check(role_and_actor_dict["actors"])
        if replaced:
            text += response
        else:
            text += actors_to_text(role_and_actor_dict["actors"])

    if len(role_and_actor_dict["roles"]) == 0 and len(role_and_actor_dict["actors"]) == 0:
        return "no one"

    return text


######################
### Main functions ###
######################

# Called mostly outside this file

def condition_template_to_text(condition_action, permissions_actions):
    """This function assumes the first parameter is a condition to be set on an action and the second parameter
    a list of permissions on that condition. Written to be understood by people setting conditions on permissions, 
    so typically we're adding the second part of a sentence that begins 'X has permission to Y...'"""

    # For now, we ignore the configuration in condition_action, and build our text from the permissions_actions
    from concord.actions.utils import get_state_change_object
    
    phrases = []
    for perm_action in permissions_actions:

        roles_and_actors_string = roles_and_actors({"roles": perm_action.change.permission_roles,
                                                    "actors": perm_action.change.permission_actors})

        change_type = get_state_change_object(perm_action.change.permission_type)

        if change_type.action_helps_pass_condition:
            phrases.append(roles_and_actors_string + " " + change_type.verb_name)
        else:
            phrases.append(roles_and_actors_string + " does not " + change_type.verb_name)

    text = "on the condition that "

    if len(phrases) == 0:
        # This means that the default permissions will be used, but this function has no way of knowing what
        # the default permission is, so we must be vague.  Condition action should always be 
        # SetConditionOnActionStateChange so get_condition_verb should always be valid.
        return text + "the governors and/or owners " + condition_action.change.get_condition_verb()

    if len(phrases) == 1:
        return text + phrases[0]
    
    if len(phrases) == 2:
        return text + phrases[0] + " and " + phrases[1]

    if len(phrases) > 2:
        return text + ", ".join(phrases[:-1]) + " and " + phrases[-1]


def community_basic_info_to_text(community):
    owners = roles_and_actors(community.roles.get_owners())
    governors = roles_and_actors(community.roles.get_governors())
    return f"Community {community.name} is owned by {owners}. It is governed by {governors}. "


def community_governance_info_to_text(community):
    """Give details of how owners/governors operate on this community."""

    text = ""

    if community.foundational_permission_enabled:
        text += "By default, the owners of the community must approve all actions"
    else:
        text += "By default, the owners do not need to approve actions in the community"

    if community.has_owner_condition():
        text += ", " + community.owner_condition.description + ". "
    else:
        text += ". "

    if community.governing_permission_enabled:
        text += "Unless otherwise specified, the governors of the community can take any action"
    else:
        text += "The governors of the community can take actions only when specified"

    if community.has_governor_condition():
        text += ", " + community.governor_condition.description + ". " 
    else:
        text += ". "

    return text


def action_status_to_text(resolution):
    """Gives details of the status of an action."""
    if resolution.is_approved:
        return f"approved through {resolution.approved_through} with role {resolution.approved_role} " + \
               f"and condition {resolution.approved_condition}"
    if resolution.generate_status() == "waiting":
        if resolution.foundational_status == "waiting":
            return "waiting on condition set on foundational permission"
        pipelines = filter(lambda x: x is not None, ["governing" if resolution.governing_status else None,
                            "specific" if resolution.specific_status else None])
        return "waiting on condition(s) for " + list_to_text(list(pipelines))
    if resolution.generate_status() == "created":
        return "action has not been put through pipeline yet"
    if resolution.foundational_status == "rejected":
        return "actor does not have foundational authority"
    return "action did not meet any permission criteria"


def action_to_text(action, with_target=True):

    target_string = f" {action.change.get_preposition()} {action.target.get_name()}" if with_target else ""

    if action.status == "implemented":
        return f"{action.actor.username} {action.change.description_past_tense()}" + target_string
    else:
        return f"{action.actor.username} asked to {action.change.description_present_tense()}" + target_string


def permission_change_to_text(permission):

    state_change_object = permission.get_state_change_object()
    if hasattr(state_change_object, "get_uninstantiated_description"):
        return state_change_object.get_uninstantiated_description(**permission.get_configuration())
    return state_change_object.description.lower()


def permission_to_text(permission):

    action_str = permission.get_state_change_object().description.lower()

    if permission.anyone:
        return f"anyone has permission to {action_str}"

    actors = [user.username for user in permission.get_actors(as_instances=True)]
    people_str = roles_and_actors({"roles": permission.get_roles(), "actors": actors})

    return f"{people_str} have permission to {action_str}"


def get_verb_given_permission_type(permission_type):
    from concord.actions.utils import get_state_change_object
    state_change_object = get_state_change_object(permission_type)
    return state_change_object.description.lower()
