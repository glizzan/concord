"""Utils for conditionals package."""

from concord.utils.helpers import Changes
from concord.utils.text_utils import roles_and_actors
from concord.utils.lookups import get_all_conditions, get_filter_conditions, get_state_change_object
from concord.utils.dependent_fields import replacer
from concord.permission_resources.models import PermissionsItem


########################
### Management Utils ###
########################

# Get utils

def get_condition_model(*, condition_type):
    for condition_model in get_all_conditions():
        if condition_model.__name__.lower() == condition_type.lower():
            return condition_model


def get_acceptance_condition(*, element_id, manager, condition_dataclass, action):
    condition_model = get_condition_model(condition_type=condition_dataclass.data["condition_type"])
    instances = condition_model.objects.filter(action=action.pk, source=manager.pk, element_id=element_id)
    return instances[0] if instances else None


def get_filter_condition(*, condition_data):
    for condition in get_filter_conditions():
        if condition.__name__ == condition_data.data["condition_type"]:
            return condition(**condition_data.data["condition_data"])
    raise ValueError(f"No matching filter condition found for {condition_data.data['condition_type']}")


def get_condition_instances(*, manager, action):
    conditions = {}
    for element_id, condition_dataclass in manager.get_condition_dataclasses().items():
        if condition_dataclass.mode == "acceptance":
            condition_instance = get_acceptance_condition(element_id=element_id, manager=manager, action=action,
                                                          condition_dataclass=condition_dataclass)
        else:
            condition_instance = get_filter_condition(condition_data=condition_dataclass)
        conditions.update({element_id: condition_instance})
    return conditions


def get_condition_status(condition, action):
    if hasattr(condition, "pk"):   # acceptance condition
        return condition.condition_status()
    else:
        result = condition.condition_status(action)
        return "approved" if result else "rejected"


def get_condition_statuses(*, manager, action):
    return [get_condition_status(condition_instance, action) if condition_instance else "not created"
            for condition_instance in get_condition_instances(manager=manager, action=action).values()]


def condition_status(*, manager, action):
    condition_statuses = get_condition_statuses(manager=manager, action=action)
    if "rejected" in condition_statuses: return "rejected"
    if "waiting" in condition_statuses or "not created" in condition_statuses: return "waiting"
    return "approved"


def uncreated_condition_names(*, manager, action):
    items = [manager.get_name_given_element_id(element_id) for element_id, condition_instance
             in get_condition_instances(manager=manager, action=action) if not condition_instance]
    return ", ".join(items)


def waiting_conditions(*, manager, action):
    return [condition_instance for element_id, condition_instance
            in get_condition_instances(manager=manager, action=action)
            if condition_instance and condition_instance.condition_status() == "waiting"]


def waiting_condition_names(*, manager, action):
    return ", ".join([condition.descriptive_name for condition
                      in waiting_conditions(manager=manager, action=action)])


# Create utils


def replace_condition_fields(*, condition_dataclass, action):
    context = {"context": {"action": action}}
    for field_name, field_value in condition_dataclass.data["condition_data"].items():
        result = replacer(field_value, context)
        condition_dataclass.data["condition_data"][field_name] = result if result != ... else field_value


def replace_permission_fields(*, condition_dataclass, action):
    for index, permission in enumerate(condition_dataclass.data["permission_data"]):
        change_object = get_state_change_object(permission["permission_type"])
        context = {"context": change_object.all_context_instances(action)}
        for field_name, field_value in permission.items():
            result = replacer(field_value, context)
            result = result if result != ... else field_value
            condition_dataclass.data["permission_data"][index][field_name] = result



# def create_condition(*, manager, element_id, condition_dataclass, action):

#     # Create condition
#     cond = get_condition_model(condition_type=condition_dataclass.data["condition_type"])()
#     cond.action, cond.source, cond.element_id, cond.owner = action.pk, manager.pk, element_id, manager.get_owner()
#     context = {"context": {"action": action}}
#     for key, value in condition_dataclass.data["condition_data"]:
#         new_value = replacer(field_value, context)
#         cond.transform_and_set_value(key, new_value if new_value else value)
#     cond.initialize_condition(action.target, condition_dataclass, manager.set_on)
#     cond.save()

#     # Create & link permissions
#     for permission in condition_dataclass.data["permission_data"]:
#         perm = PermissionsItem()
#         perm.owner, perm.permitted_object, perm.change_type = cond.owner, cond, permission["permission_type"]
#         change_object = get_state_change_object(permission["permission_type"])
#         context = {"context": change_object.all_context_instances(action)}
#         for name, default in {"permission_actors": [], "permission_roles": [], "permission_configuration": {}}.items():
#             field_value = permission.get(name, default)
#             new_value = replacer(field_value, context)
#             perm.transform_and_set_value(name, new_value if new_value else field_value)
#         perm.save()

#     return cond



def create_condition(*, manager, element_id, condition_dataclass, action):

    replace_condition_fields(condition_dataclass=condition_dataclass, action=action)
    replace_permission_fields(condition_dataclass=condition_dataclass, action=action)

    if condition_dataclass.mode == "acceptance":

        condition_model = get_condition_model(condition_type=condition_dataclass.data["condition_type"])
        condition_instance = condition_model(action=action.pk, source=manager.pk, element_id=element_id,
                                                **condition_dataclass.data["condition_data"])

        condition_instance.owner = manager.get_owner()
        condition_instance.initialize_condition(action.target, condition_dataclass, manager.set_on)
        condition_instance.save()

        for permission in condition_dataclass.data["permission_data"]:
            permission_item = PermissionsItem()
            permission_item.set_fields(
                owner=condition_instance.owner, permitted_object=condition_instance,
                change_type=permission["permission_type"], actors=permission.get("permission_actors", []),
                roles=permission.get("permission_roles", []),
                configuration=permission.get("permission_configuration", {}))
            permission_item.save()

        return condition_instance


def create_conditions(*, manager, action):
    created_instances = []
    for element_id, condition_dataclass in manager.get_condition_dataclasses().items():
        condition_instance = get_acceptance_condition(element_id=element_id, manager=manager,
                                                      condition_dataclass=condition_dataclass, action=action)
        if not condition_instance:
            instance = create_condition(manager=manager, element_id=element_id,
                                        condition_dataclass=condition_dataclass, action=action)
            created_instances.append(instance)
    return created_instances



##################
### Text Utils ###
##################


def get_permission_value(permission_data, permission_type, assignee_type):
    """Given permission data in the form of a list of dicts, with keys 'permission_type',
    'permission_roles', 'permission_actors' and 'permission_configuration, gets the
    value being looked up."""

    if not permission_data:
        return []

    permission = [p for p in permission_data if p["permission_type"] == permission_type]
    if not permission:
        return []

    if "permission_" + assignee_type in permission[0]:
        value = permission[0]["permission_" + assignee_type]
        return value if value else []

    return []


def description_for_passing_approval_condition(permission_data=None):
    """Generate a 'plain English' description for passing the approval condtion."""

    approve_actors = get_permission_value(permission_data, Changes().Conditionals.Approve, "actors")
    approve_roles = get_permission_value(permission_data, Changes().Conditionals.Approve, "roles")
    reject_actors = get_permission_value(permission_data, Changes().Conditionals.Reject, "actors")
    reject_roles = get_permission_value(permission_data, Changes().Conditionals.Reject, "roles")

    if not approve_roles and not approve_actors:
        return "one person needs to approve this action"

    approve_str = roles_and_actors({"roles": approve_roles, "actors": approve_actors})
    if reject_actors or reject_roles:
        reject_str = f", without {roles_and_actors({'roles': reject_roles, 'actors': reject_actors})} rejecting."
    else:
        reject_str = ""

    return f"{approve_str} needs to approve this action{reject_str}"


def description_for_passing_voting_condition(condition, permission_data=None):
    """Generate a 'plain English' description for passing the approval condtion."""

    vote_actors = get_permission_value(permission_data, Changes().Conditionals.AddVote, "actors")
    vote_roles = get_permission_value(permission_data, Changes().Conditionals.AddVote, "roles")

    vote_type = "majority" if condition.require_majority else "plurality"

    if vote_roles or vote_actors:
        people_str = roles_and_actors({'roles': vote_roles, 'actors': vote_actors})
    else:
        people_str = "people"

    return f"a {vote_type} of {people_str} vote for it within {condition.describe_voting_period()}"


def description_for_passing_consensus_condition(condition, permission_data=None):
    """Generate a 'plain English' description for passing the consensus condtion."""

    participate_actors = get_permission_value(permission_data, Changes().Conditionals.RespondConsensus, "actors")
    participate_roles = get_permission_value(permission_data, Changes().Conditionals.RespondConsensus, "roles")

    if not participate_roles and not participate_actors:
        consensus_type = "strict" if condition.is_strict else "loose"
        return f"a group of people must agree to it through {consensus_type} consensus"

    participate_str = roles_and_actors({"roles": participate_roles, "actors": participate_actors})

    if condition.is_strict:
        return f"{participate_str} must agree to it with everyone participating and no one blocking"
    else:
        return f"{participate_str} must agree to it with no one blocking"


def convert_measured_in(duration, measured_in):
    """Takes a numeric duration and a measurement type (measured_in) and returns duration in seconds."""
    if measured_in == "seconds":
        return duration
    if measured_in == "minutes":
        return duration * 60
    if measured_in == "hours":
        return duration * 60 * 60
    if measured_in == "days":
        return duration * 60 * 60 * 24
    if measured_in == "weeks":
        return duration * 60 * 60 * 24 * 7
    raise ValueError(f"measured_in must be seconds, minutes, hours, days or weeks, not {measured_in}")


def parse_duration_into_units(duration, measured_in="hours"):
    """Given a period of time, parses into months, weeks, days, hours, minutes, seconds."""

    duration = convert_measured_in(duration, measured_in)

    weeks = duration // (60 * 60 * 24 * 7)
    time_remaining = duration % (60 * 60 * 24 * 7)

    days = time_remaining // (60 * 60 * 24)
    time_remaining = duration % (60 * 60 * 24)

    hours = time_remaining // (60 * 60)
    time_remaining = duration % (60 * 60)

    minutes = time_remaining // 60
    seconds = duration % 60

    return {"weeks": weeks, "days": days, "hours": hours, "minutes": minutes, "seconds": seconds}


def display_duration_units(weeks=0, days=0, hours=0, minutes=0, seconds=0):
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
    if seconds > 0:
        time_pieces.append(f"{seconds} seconds" if seconds > 1 else "1 second")

    if len(time_pieces) == 1:
        return time_pieces[0]

    if len(time_pieces) > 1:
        last_time_piece = time_pieces.pop()
        description = ", ".join(time_pieces)
        description += " and " + last_time_piece
        return description

    return ""
