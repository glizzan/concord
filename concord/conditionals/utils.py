"""Utils for conditionals package."""

from concord.actions.utils import Changes
from concord.actions.text_utils import roles_and_actors


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


def parse_duration_into_units(duration):
    """Given a period of time in hours, parses into months, weeks, days, hours, minutes.
    #FIXME: use // instead of int() for clarity"""

    duration = int(duration)

    weeks = int(duration / 168)
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
