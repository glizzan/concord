"""Utils for conditionals package."""
from dataclasses import dataclass, asdict


from concord.utils.helpers import Changes
from concord.utils.text_utils import roles_and_actors
from concord.utils.lookups import get_all_conditions, get_filter_conditions, get_state_change_object
from concord.utils.dependent_fields import replacer
from concord.permission_resources.models import PermissionsItem


########################
### Management Utils ###
########################


def get_condition_model(condition_type):
    for condition_model in get_all_conditions():
        if condition_model.__name__.lower() == condition_type.lower():
            return condition_model


def validate_condition_data(model_instance, condition_data):

    if not condition_data: return True, None

    for field_name, field_value in condition_data.items():

        if type(field_value) == str and field_value[:2] == "{{":
            continue  # don't validate if it's a replaced field

        try:
            if hasattr(model_instance, "_meta") and hasattr(model_instance._meta, "get_field"):
                field_instance = model_instance._meta.get_field(field_name)
            else:
                field_instance = getattr(model_instance, field_name)
        except AttributeError:
            return False, f"There is no field {field_name} on condition {self.__class__}"

        try:
            if hasattr(field_instance, "clean"):
                field_instance.clean(field_value, model_instance)
        except ValidationError:
            return False, f"{field_value} is not valid value for {field_name}"

    return True, None


def validate_permission_data(model_instance, permission_data):

    if not permission_data: return True, None

    for permission in permission_data:

        state_change_object = get_state_change_object(permission["permission_type"])
        if model_instance.__class__ not in state_change_object.get_allowable_targets():
            return False, f"Permission type {permission['permission_type']} cannot be set on {condition_model}"

        if "permission_roles" not in permission and "permission_actors" not in permission:
            return False, f"Must supply either roles or actors to permission {permission['permission_type']}"

    return True, None


class ConditionData(object):
    condition_type: str = None
    element_id: int = None

    condition_data: dict = None
    permission_data: dict = None

    def __str__(self):
        return f"{self.condition_type} ({self.element_id})"

    def __repr__(self):
        return f"{self.condition_type} ({self.element_id}); " + \
            f"condition data: {self.condition_data}, permission data: {self.permission_data}"

    def __init__(self, condition_type, element_id, **kwargs):
        self.condition_type, self.element_id = condition_type, element_id
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.condition_data = self.condition_data if self.condition_data else {}
        self.clean_permission_data()

    @property
    def mode(self):
        return "filter" if "Filter" in self.condition_type else "acceptance"

    def serialize(self):
        new_dict = self.get_fields_as_dict()
        new_dict.update({"condition_type": self.condition_type, "element_id": self.element_id})
        return new_dict

    def get_fields_as_dict(self):
        fields_to_get = ["condition_data"] if self.mode == "filter" else ["condition_data", "permission_data"]
        return {field: getattr(self, field) for field in fields_to_get}

    def update_data(self, data):
        for key, value in data.items():
            setattr(self, key, value)

    def clean_permission_data(self):
        if self.permission_data:
            for perm in self.permission_data:
                if "permission_actors" in perm and perm["permission_actors"] is None:
                    del(perm["permission_actors"])
                if "permission_roles" in perm and perm["permission_roles"] is None:
                    del(perm["permission_roles"])

    def get_unsaved_condition_object(self):
        model = get_condition_model(self.condition_type)
        return model(**self.condition_data) if self.condition_data else model()

    def validate(self, change_object):

        model_instance = self.get_unsaved_condition_object()

        if self.mode == "acceptance":
            is_valid, message = validate_condition_data(model_instance, self.condition_data)
            if not is_valid:
                return is_valid, message
            is_valid, message = validate_permission_data(model_instance, self.permission_data)
            return is_valid, message

        if self.mode == "filter":
            return model_instance.validate(change_object)


def validate_condition(condition_type, condition_data, permission_data, change_object):
    return ConditionData(condition_type=condition_type, element_id=None, condition_data=condition_data,
        permission_data=permission_data).validate(change_object)


# Get utils

def get_acceptance_condition(*, element_id, manager, data, action):
    condition_model = get_condition_model(condition_type=data.condition_type)
    instances = condition_model.objects.filter(action=action.pk, source=manager.pk, element_id=element_id)
    return instances[0] if instances else None


def get_filter_condition(*, data, action):
    for condition in get_filter_conditions():
        if condition.__name__ == data.condition_type:
            return condition(**data.get_fields_as_dict()["condition_data"])
    raise ValueError(f"No matching filter condition found for {condition_data.condition_type}")


def get_condition_instances(*, manager, action):
    conditions = {}
    for data in manager.get_conditions_as_data():
        if data.mode == "acceptance":
            instance = get_acceptance_condition(element_id=data.element_id, manager=manager, action=action, data=data)
        if data.mode == "filter":
            instance = get_filter_condition(data=data, action=action)
        conditions.update({data.element_id: instance})
    return conditions


def get_condition_status(condition, action):
    if hasattr(condition, "pk"):   # acceptance condition
        return condition.condition_status()
    else:
        return condition.condition_status(action)


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


def get_condition_target_filter(manager):
    for data in manager.get_conditions_as_data():
        if data.mode == "filter":
            instance = get_filter_condition(data=data, action=None)
            if instance.__class__.__name__ == "TargetTypeFilter":
                return instance.target_type

# Create utils


def replace_condition_fields(*, data, action):
    if data.condition_data:
        context = {"context": {"action": action}}
        for field_name, field_value in data.condition_data.items():
            result = replacer(field_value, context)
            data.condition_data[field_name] = result if result != ... else field_value


def replace_permission_fields(*, data, action):
    if data.permission_data:
        for index, permission in enumerate(data.permission_data):
            change_object = get_state_change_object(permission["permission_type"])
            context = {"context": change_object.all_context_instances(action)}
            for field_name, field_value in permission.items():
                result = replacer(field_value, context)
                result = result if result != ... else field_value
                data.permission_data[index][field_name] = result


def create_acceptance_condition(manager, element_id, data, action):

    condition_model = get_condition_model(condition_type=data.condition_type)
    condition_data = data.condition_data if data.condition_data else {}
    condition_instance = condition_model(
        action=action.pk, source=manager.pk, element_id=element_id, **condition_data)

    condition_instance.owner = manager.get_owner()
    condition_instance.initialize_condition(action.target, data, manager.set_on)
    condition_instance.save()

    if data.permission_data:
        for permission in data.permission_data:
            permission_item = PermissionsItem()
            permission_item.set_fields(
                owner=condition_instance.owner, permitted_object=condition_instance,
                change_type=permission["permission_type"], actors=permission.get("permission_actors", []),
                roles=permission.get("permission_roles", []))
            permission_item.save()

    return condition_instance


def create_condition(*, manager, element_id, data, action):

    # filter conditions should always be created by get_condition_instances, so we can skip them here

    if data.mode == "acceptance":

        replace_condition_fields(data=data, action=action)
        replace_permission_fields(data=data, action=action)

        return create_acceptance_condition(manager, element_id, data, action)


def create_conditions(*, manager, action):
    """Gets already created instances, then loops through the conditions set in the manager. If any are not
    already created, creates and returns them."""

    created_instances = get_condition_instances(manager=manager, action=action)

    for data in manager.get_conditions_as_data():
        if not created_instances.get(data.element_id, None):
            instance = create_condition(manager=manager, element_id=data.element_id, data=data, action=action)
            created_instances.update({data.element_id: instance})

    return created_instances.values()


##################
### Text Utils ###
##################


def get_permission_value(permission_data, permission_type, assignee_type):
    """Given permission data in the form of a list of dicts, with keys 'permission_type',
    'permission_roles', 'permission_actors' gets the value being looked up."""

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
