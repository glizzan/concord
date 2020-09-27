"""Utils for conditionals package."""

from concord.actions.utils import Client
from concord.actions.text_utils import roles_and_actors
from concord.permission_resources.models import PermissionsItem


def get_basic_condition_info(condition_object):
    """Given a condition object, returns basic info about the object in dict form."""
    return {
        "type": condition_object.__class__.__name__,
        "display_name": condition_object.descriptive_name,
        "how_to_pass": condition_object.description_for_passing_condition()
    }


def generate_condition_fields_for_form(condition_object, permissions_objects):
    """Given a condition objects and permission objects set on that condition, returns field
    data in dict form."""

    permission_data = {}
    for short_name, field_dict in condition_object.configurable_fields().items():
        for permission in permissions_objects:

            if "full_name" in field_dict and permission.change_type == field_dict["full_name"]:

                if field_dict["type"] in ["RoleField", "RoleListField"]:
                    try:
                        permission_data.update({field_dict["field_name"]: permission.roles.role_list})
                    except AttributeError:
                        permission_data.update({field_dict["field_name"]: permission.roles})
                elif field_dict["type"] in ["ActorField", "ActorListField"]:
                    try:
                        permission_data.update({field_dict["field_name"]: permission.actors.pk_list})
                    except AttributeError:
                        permission_data.update({field_dict["field_name"]: permission.actors})

    return condition_object.get_configurable_fields_with_data(permission_data)


def generate_condition_form(condition_object, permissions_objects):
    """Given a condition objects and permission objects set on that condition, returns a full
    dict of basic info & fields."""

    basic_info = get_basic_condition_info(condition_object)
    basic_info.update({
        "fields": generate_condition_fields_for_form(condition_object, permissions_objects)
    })
    return basic_info


def parse_action_list_into_condition_and_permission_objects(action_list):
    """Given a list of actions which will create a condition object and any permission objects that need to be set
    on the condition, creates them."""

    # get condition object
    condition_model = Client().Conditional.get_condition_class(condition_type=action_list[0].change.condition_type)
    data = action_list[0].change.condition_data if action_list[0].change.condition_data else {}
    condition_object = condition_model(**data)

    # get permissions objects
    permission_objects = []
    for action in action_list[1:]:
        permission = PermissionsItem()
        permission.set_fields(
            change_type=action.change.change_type,
            actors=action.change.actors,
            roles=action.change.roles,
            inverse=action.change.inverse,
            anyone=action.change.anyone,
            configuration=action.change.configuration
        )
        permission_objects.append(permission)

    return condition_object, permission_objects


def generate_condition_form_from_action_list(action_list, info):
    """Given a list of actions, create the condition and permission they'll make and then generate forms from them."""

    condition, permissions = parse_action_list_into_condition_and_permission_objects(action_list)

    if info == "all":
        return generate_condition_form(condition, permissions)
    if info == "fields":
        return generate_condition_fields_for_form(condition, permissions)
    if info == "basic":
        return get_basic_condition_info(condition)

    return generate_condition_form(condition, permissions)


def description_for_passing_approval_condition(fill_dict=None):
    """Generate a 'plain English' description for passing the approval condtion."""

    approve_actors = fill_dict.get("approve_actors", []) if fill_dict else None
    approve_roles = fill_dict.get("approve_roles", []) if fill_dict else None
    reject_actors = fill_dict.get("reject_actors", []) if fill_dict else None
    reject_roles = fill_dict.get("reject_roles", []) if fill_dict else None

    if not fill_dict or (not approve_roles and not approve_actors):
        return "one person needs to approve this action"

    approve_str = roles_and_actors({"roles": approve_roles, "actors": approve_actors})
    if reject_actors or reject_roles:
        reject_str = f", without {roles_and_actors({'roles': reject_roles, 'actors': reject_actors})} rejecting."
    else:
        reject_str = ""

    return f"one person {approve_str} needs to approve{reject_str}"


def description_for_passing_voting_condition(condition, fill_dict=None):
    """Generate a 'plain English' description for passing the approval condtion."""

    vote_actors = fill_dict.get("vote_actors", []) if fill_dict else None
    vote_roles = fill_dict.get("vote_roles", []) if fill_dict else None

    vote_type = "majority" if condition.require_majority else "plurality"

    if fill_dict and (vote_roles or vote_actors):
        people_str = roles_and_actors({'roles': vote_roles, 'actors': vote_actors})
    else:
        people_str = ""

    return f"a {vote_type} of people{people_str} vote for it within {condition.describe_voting_period()}"


def description_for_passing_consensus_condition(condition, fill_dict=None):
    """Generate a 'plain English' description for passing the consensus condtion."""

    participate_actors = fill_dict.get("participate_actors", []) if fill_dict else None
    participate_roles = fill_dict.get("participate_roles", []) if fill_dict else None

    if not fill_dict or (not participate_roles and not participate_actors):
        consensus_type = "strict" if condition.is_strict else "loose"
        return f"a group of people must agree to it through {consensus_type} consensus"

    participate_str = roles_and_actors({"roles": participate_roles, "actors": participate_actors})

    if condition.is_strict:
        return f"{participate_str} must agree to it with everyone participating and no one blocking"
    else:
        return f"{participate_str} must agree to it with no one blocking"


def parse_duration_into_units(duration):
    """Given a period of time in hours, parses into months, weeks, days, hours, minutes."""

    weeks = int(int(duration) / 168)
    time_remaining = duration % 168
    days = int(int(time_remaining) / 24)
    time_remaining = int(time_remaining) % 24
    hours = int(time_remaining)
    minutes = int((duration - int(duration)) * 60)

    return {"weeks": weeks, "days": days, "hours": hours, "minutes": minutes}


def display_duration_units(weeks=0, days=0, hours=0, minutes=0):
    """Creates human readable description of duration period."""

    time_pieces = []

    if weeks > 0:
        time_pieces.append(f"{weeks} weeks" if weeks > 1 else "1 week")
    if days > 0:
        time_pieces.append(f"{days} days" if days > 1 else "1 day")
    if hours > 0:
        time_pieces.append(f"{hours} hours" if hours > 1 else "1 hour")
    if minutes > 0:
        time_pieces.append(f"{minutes} minutes" if minutes > 1 else "1 minute")

    if len(time_pieces) == 1:
        return time_pieces[0]

    if len(time_pieces) > 1:
        last_time_piece = time_pieces.pop()
        description = ", ".join(time_pieces)
        description += " and " + last_time_piece
        return description

    return ""
