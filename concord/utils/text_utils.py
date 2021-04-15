"""This module contains functions which take in various Concord objects and return human-readable English
descriptions."""

import copy, logging

from concord.utils.lookups import get_state_change_object


logger = logging.getLogger(__name__)


########################
### Helper functions ###
########################

# Called mostly inside this file


def is_plural(new_list):
    """Returns true if list past in contains more than one item, otherwise False."""
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
    """Given a list of roles, returns them in format 'those with role 'banana''."""

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
    """Checks for replaceable fields and parses & returns their content if found."""

    if isinstance(value, str) and value[0:2] == "{{" and value[-2:] == "}}":
        command = value.replace("{{", "").replace("}}", "").strip()
        command = command[7:] if command[0:7] == "nested:" else command
        command = command.split("||")[0]
        tokens = command.split(".")

        if tokens[0] == "context":

            if tokens[1] == "action":

                if len(tokens) == 2:

                    replace_str = "the action"

                if len(tokens) == 3:

                    replace_str = "the action's " + tokens[2]

                if len(tokens) == 4:

                    replace_str = tokens[3] + " specified by the action"

            else:

                if len(tokens) == 2:

                    replace_str = "the " + tokens[1]

                if len(tokens) == 3:

                    replace_str = "the " + tokens[1] + "'s " + tokens[2]

            return True, replace_str

        if tokens[0] == "previous":

            if tokens[2] == "action":

                return True, f"action number {int(tokens[1])+1} in this template"

            else:

                return True, f"the result of action number {int(tokens[1])+1} in this template"

        # TODO: handle supplied_fields

    return False, value


def roles_and_actors(role_and_actor_dict):
    """Given a dict specifying roles and/or actions, returns a string of the format:
    'those with role 'banana', 'orange' and 'pineapple' and individuals '1', '2' and '3'. If dicts are empty,
    returns 'no one'."""

    text = ""

    if len(role_and_actor_dict["roles"]) > 0:
        replaced, response = replaceable_field_check(role_and_actor_dict["roles"])
        if replaced:
            logger.debug(f"Replaced {role_and_actor_dict['actors']} with {response}")
            text += response
        else:
            text += roles_to_text(role_and_actor_dict["roles"])

    if len(role_and_actor_dict["roles"]) > 0 and len(role_and_actor_dict["actors"]) > 0:
        text += " and "

    if len(role_and_actor_dict["actors"]) > 0:
        replaced, response = replaceable_field_check(role_and_actor_dict["actors"])
        if replaced:
            logger.debug(f"Replaced {role_and_actor_dict['actors']} with {response}")
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

def condition_to_text(condition_change_object):
    """Written to be understood by people setting conditions on permissions, so typically we're adding the second
    part of a sentence that begins 'X has permission to Y...'"""

    # For now, we ignore the configuration in condition_action, and build our text from the permissions_actions

    phrases = []
    permissions = condition_change_object.condition_data.get("permission_data", [])
    for permission in permissions:

        roles_and_actors_string = roles_and_actors({"roles": permission.get("permission_roles", []),
                                                    "actors": permission.get("permission_actors", [])})

        change_type = get_state_change_object(permission["permission_type"])

        if hasattr(change_type, "rejects_condition") and change_type.rejects_condition:
            phrases.append(roles_and_actors_string + " does not " + change_type._description().verb)
        else:
            phrases.append(roles_and_actors_string + " " + change_type._description().verb)

    text = "on the condition that "

    if len(phrases) == 0:
        # This means that the default permissions will be used, but this function has no way of knowing what
        # the default permission is, so we must be vague.  Condition action should always be
        # SetConditionOnActionStateChange so get_condition_verb should always be valid.
        return text + "the governors and/or owners " + condition_change_object.get_condition_verb()

    if len(phrases) == 1:
        return text + phrases[0]

    if len(phrases) == 2:
        return text + phrases[0] + " and " + phrases[1]

    if len(phrases) > 2:
        return text + ", ".join(phrases[:-1]) + " and " + phrases[-1]


def community_basic_info_to_text(community):
    """Gets the basic info about a community, including its name, owners, and governors."""
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

    if community.has_condition("owner"):
        text += ", " + community.owner_condition.get_condition_form_data()["how_to_pass_overall"] + ". "
    else:
        text += ". "

    if community.governing_permission_enabled:
        text += "Unless otherwise specified, the governors of the community can take any action"
    else:
        text += "The governors of the community can take actions only when specified"

    if community.has_condition("governor"):
        text += ", " + community.governor_condition.get_condition_form_data()["how_to_pass_overall"] + ". "
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
    if resolution.generate_status() == "proposed":
        return "action is still in proposal state"
    if resolution.foundational_status == "rejected":
        return "actor does not have foundational authority"
    return "action did not meet any permission criteria"


def action_to_text(action, with_actor=True, with_target=True):
    """Gets a text description of an action."""

    if not with_target:
        target_string = ""
    elif not action.target:
        target_string = f" {action.change.get_preposition()} deleted target"
    else:
        target_string = f" {action.change.get_preposition()} {action.target.get_name()}"

    actor_string = action.actor.username if with_actor else ""

    if action.status == "implemented":
        return f"{actor_string} {action.change.description_past_tense()}" + target_string
    else:
        return f"{actor_string} asked to {action.change.description_present_tense()}" + target_string


def supplied_fields_to_text(supplied_field_data, supplied_field_options):
    """Creates an English description of supplied fields."""

    fields = []
    for key, value in supplied_field_options.items():
        prompt = supplied_field_options[key][1]["label"]
        answer = supplied_field_data[key] if supplied_field_data else ""
        fields.append(f"{prompt} {answer}")

    return {"has_data": bool(supplied_field_data), "fields": fields}


def foundational_actions_to_text(actions):
    """Creates a string list of foundational actions"""
    foundational_actions = [action for action in actions if action.change.is_foundational]
    if foundational_actions:
        action_string = "Please note that the following actions are foundational, and require owner approval " + \
                        f"to pass: {', '.join([action.change.change_description() for action in foundational_actions])}"
    else:
        action_string = "None of the actions are foundational, so they do not necessarily require owner " + \
                        "approval to pass."
    return action_string


def mock_action_to_text(action, trigger_action=None):
    """Creates a text description of a mock action, used primarily by template models to describe what they
    do.  Also handles trigger_action and supplied_fields being passed in, to fully describe an apply_template
    action being considered during a condition or reviewed afterwards."""

    if isinstance(action.target, str):
        if action.target == "{{context.action.target}}":
            if trigger_action:
                target_name = trigger_action.target.get_name()
            else:
                target_name = "the target of the action that triggered the template"
        else:
            changed, new_name = replaceable_field_check(action.target)
            target_name = new_name if changed else action.target
    else:
        target_name = action.target.get_name()

    try:
        description = action.change.description_present_tense()
    except Exception as error:  # noqa: E722
        print(error)
        description = action.change.change_description()

    return f"{description} {action.change.get_preposition()} {target_name}"


def permission_change_to_text(permission):
    """Gets the text description of the change object on a permission."""
    state_change_object = permission.get_state_change_object()
    return state_change_object.get_uninstantiated_description()


def permission_to_text(permission):
    """Gets the text description of a permission item."""

    change_obj = permission.get_state_change_object()

    action_str = change_obj.change_description(capitalize=False)

    if permission.anyone:
        return f"anyone has permission to {action_str}"

    actors = [user.username for user in permission.get_actors(as_instances=True)]
    people_str = roles_and_actors({"roles": permission.get_roles(), "actors": actors})

    return f"{people_str} have permission to {action_str}"


def get_verb_given_permission_type(permission_type):
    """Given a permission type, get the verb specified by the corresponding change object."""
    state_change_object = get_state_change_object(permission_type)
    return state_change_object.change_description(capitalize=False)
