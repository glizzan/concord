"""Utils for conditionals package."""

from concord.actions.utils import Client
from concord.actions.text_utils import roles_and_actors
from concord.permission_resources.models import PermissionsItem


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
