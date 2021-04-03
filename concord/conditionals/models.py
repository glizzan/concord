"""Condition models."""

import datetime, json, random
from abc import abstractmethod
from dataclasses import dataclass, asdict

from django.db import models
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver

from concord.actions.models import PermissionedModel
from concord.conditionals import utils, forms
from concord.utils import helpers
from concord.conditionals.management.commands.check_condition_status import retry_action_signal


##################################
### Conditional Resource/Items ###
##################################


@dataclass
class ConditionData:
    data: dict
    mode: str = "acceptance"


class ConditionManager(PermissionedModel):  # NOTE: can maybe just be a model here?
    """The compound manager is associated with a single permission or leadership type on a community and coordinates
    any conditions set.

    Conditions field should have structure: {unique_id: ConditionData(), unique_id: ConditionData()}
    condition_data is the data needed to instantiate or otherwise manage the specific condition, with the following
    options:

        acceptance: {condition_type: X, condition_data: {}, permission_data: {}}

    For clarity's sake, any ConditionModel is refered to as an "instance" and the dictionaries/dataclass obj's
    corresponding to them are referred to as a "dataclass".
    """
    community = models.IntegerField()
    conditions = models.TextField()
    SET_ON_CHOICES = (
        ('permission', 'Permission'),
        ('owner', 'Owner'),
        ('governor', 'Governor'),
    )
    set_on = models.CharField(max_length=10, choices=SET_ON_CHOICES)

    # get methods

    def get_condition_dataclasses(self):
        if self.conditions:
            condition_dataclasses = json.loads(self.conditions)
            return {element_id: ConditionData(**data) for element_id, data in condition_dataclasses.items()}
        return {}

    def get_condition_dataclass(self, element_id):
        condition_dataclasses = self.get_condition_dataclasses()
        return condition_dataclasses[element_id]

    def get_element_ids(self):
        condition_dataclasses = self.get_condition_dataclasses()
        return [element_id for element_id, dataclass in condition_dataclasses.items()]

    def get_condition_names(self):
        names = []
        for unique_id, condition_dataclass in self.get_condition_dataclasses().items():
            names.append(condition_dataclass.data["condition_type"])
        return ", ".join(names)

    def get_name_given_element_id(self, element_id):
        condition_dataclass = self.get_condition_dataclasses()
        return condition_dataclass[element_id].data["condition_type"]

    def get_condition_form_data(self):
        return forms.condition_manager_form(self)

    # edit methods

    def set_conditions(self, condition_dataclasses):
        conditions = {element_id: asdict(data) for element_id, data in condition_dataclasses.items()}
        self.conditions = json.dumps(conditions)

    def clean_permission_data(self, permission_data):
        for perm in permission_data:
            if "permission_actors" in perm and perm["permission_actors"] is None:
                del(perm["permission_actors"])
            if "permission_roles" in perm and perm["permission_roles"] is None:
                del(perm["permission_roles"])
        return permission_data

    def prep_condition(self, condition, mode):
        if mode == "acceptance":
            condition["permission_data"] = self.clean_permission_data(condition["permission_data"])
            return ConditionData(data=condition)

    def add_condition(self, condition, mode="acceptance"):
        condition_dataclasses = self.get_condition_dataclasses()
        condition_dataclasses.update({random.getrandbits(20): self.prep_condition(condition, mode)})
        self.set_conditions(condition_dataclasses)

    def edit_condition(self, element_id, condition_data):
        condition_dataclasses = self.get_condition_dataclasses()
        if condition_dataclasses[element_id].mode == "acceptance":
            condition_data["permission_data"] = self.clean_permission_data(condition_data["permission_data"])
        condition_dataclasses[element_id].data = condition_data
        self.set_conditions(condition_dataclasses)

    def edit_condition_by_key(self, element_id, key, value):
        condition_dataclasses = self.get_condition_dataclasses()
        if key == "permission_data":
            value = self.clean_permission_data(value)
        condition_dataclasses[element_id].data[key] = value
        self.set_conditions(condition_dataclasses)

    def remove_condition(self, element_id):
        condition_dataclasses = self.get_condition_dataclasses()
        condition_dataclasses.pop(element_id)
        self.set_conditions(condition_dataclasses)


class ConditionModel(PermissionedModel):
    """
    Attributes:

    action: integer representing the pk of the action that triggered the creation of this condition
    source: integer representing the pk of the condition manager that created the condition
    element_id: integer representing the element_id generated by the condition manager
    """

    class Meta:
        abstract = True

    action = models.IntegerField()
    source = models.CharField(max_length=20)
    element_id = models.CharField(max_length=10)

    descriptive_name = "condition"
    has_timeout = False

    is_condition = True

    @property
    def name(self):
        self.get_name()

    def get_name(self):
        """Get name of condition."""
        return f"{self.descriptive_name}, {self.pk}"

    def get_model_name(self):
        """Get name of condition model."""
        return self.__class__.__name__.lower()

    def get_display_string(self):
        """Get display text describing condition.."""
        return self.descriptive_name

    def get_action(self):
        """Get action associated with condition instance."""
        return helpers.Client().Action.get_action_given_pk(pk=self.action)

    def get_configurable_fields_with_data(self, permission_data=None):
        """Returns form_dict with condition data set as value."""
        return forms.form_dict_for_fields_with_data(self, permission_data)

    def user_condition_status(self, user):
        """User condition status is a shortcut which helps us determine if a user can take an action on a condition
        without actually creating an action. This is useful in determining what to show the user on the front-end.
        We assume that by the time user_condition_status is called the user has passed the permissions system, and so
        this status is to check instance-specific issues, like preventing a person who has already voted from voting
        again."""
        return True, ""

    def initialize_condition(self, *args, **kwargs):
        """Called when creating the condition, and passed condition_data and permission data."""
        return

    # Class methods with default implementation

    @classmethod
    def get_configurable_fields(cls):
        """Returns field values as list instead of dict"""
        return [value for key, value in forms.form_dict_for_fields_with_data(cls).items()]

    # Methods models must implement themselves

    @classmethod
    @abstractmethod
    def configurable_fields(cls):
        """All conditions must supply their own version of the configurable_fields method,
        which should return a dict with field names as keys and field objects as values."""
        return {}

    @abstractmethod
    def description_for_passing_condition(self, permission_data=None):
        """This method returns a verbose, human-readable description of what will fulfill this condition.  It optionally
        accepts permission data from the configured condition_template to be more precise about who can do what."""

    @abstractmethod
    def display_fields(self):
        """This method returns a list of fields and their values which can be shown to the user. Some overlap with
        get_configurable_fields_with_data since in many cases we're just showing the configured fields, but some
        data may be specific to the condition instance.  Note that we do not, for now, return permission data."""

    @abstractmethod
    def condition_status(self):
        """This method returns one of status 'approved', 'rejected', or 'waiting', after checking the condition
        for its unqiue status logic."""

    @abstractmethod
    def display_status(self):
        """This method returns a more verbose, human-readable description of the condition status, after checking
        the condition for its unique status logic."""


class ApprovalCondition(ConditionModel):
    """Approval Condition class."""

    descriptive_name = "Approval Condition"
    verb_name = "approve"

    approved = models.BooleanField(null=True, blank=True)  # Null by default
    self_approval_allowed = models.BooleanField(default=False)

    def approve(self):
        """Approve a condition."""
        self.approved = True

    def reject(self):
        """Reject a condition."""
        self.approved = False

    # Required methods

    @classmethod
    def configurable_fields(cls):
        return {
            "self_approval_allowed": {"display": "Can individuals approve their own actions?"},
            "approve_roles":
                {"display": "Roles who can approve", "type": "RoleListField",
                 "full_name": helpers.Changes().Conditionals.Approve},
            "approve_actors":
                {"display": "People who can approve", "type": "ActorListField",
                 "full_name": helpers.Changes().Conditionals.Approve},
            "reject_roles":
                {"display": "Roles who can reject", "type": "RoleListField",
                 "full_name": helpers.Changes().Conditionals.Reject},
            "reject_actors":
                {"display": "People who can reject", "type": "ActorListField",
                 "full_name": helpers.Changes().Conditionals.Reject}
        }

    def display_fields(self):
        return [{"field_name": "self_approval_allowed", "field_value": self.self_approval_allowed, "hidden": False}]

    def condition_status(self):
        if self.approved is True:
            return "approved"
        if self.approved is False:
            return "rejected"
        return "waiting"

    def display_status(self):
        status = self.condition_status()
        if status == "waiting":
            return "waiting for approval"
        elif status == "rejected":
            return "not approved"
        else:
            return "approved"

    def description_for_passing_condition(self, permission_data=None):
        return utils.description_for_passing_approval_condition(permission_data=permission_data)


class VoteCondition(ConditionModel):
    """Vote Condition class."""

    descriptive_name = "Vote Condition"
    verb_name = "vote"
    has_timeout = True

    yeas = models.IntegerField(default=0)
    nays = models.IntegerField(default=0)

    # If abstentions allowed, do we require majority to pass or merely plurality?
    allow_abstain = models.BooleanField(default=True)
    abstains = models.IntegerField(default=0)
    require_majority = models.BooleanField(default=False)

    # 'voted' should eventually be a list field or json field or something
    publicize_votes = models.BooleanField(default=False)
    voted = models.CharField(max_length=500, default="[]")

    # voting period in hours, default is 168 hours aka one week
    voting_starts = models.DateTimeField(default=timezone.now)
    voting_period = models.IntegerField(default=168)

    def user_condition_status(self, user):
        """Checks whether a user has voted already."""
        if self.has_voted(user):
            return False, "has voted"
        return True, "has not voted"

    def get_timeout(self):
        """Get when condition closes, aka the voting deadline."""
        return self.voting_deadline()

    def current_results(self):
        """Get the current results of the vote."""
        results = {"yeas": self.yeas, "nays": self.nays}
        if self.allow_abstain:
            results.update({"abstains": self.abstains})
        return results

    def has_voted(self, actor):
        """Returns True if actor has voted, otherwise False."""
        voted = json.loads(self.voted)
        if actor.username in voted:
            return True
        return False

    def add_vote(self, vote):
        """Increments vote depending on vote type."""
        if vote == "yea":
            self.yeas += 1
        elif vote == "nay":
            self.nays += 1
        elif vote == "abstain":
            self.abstains += 1

    def add_vote_record(self, actor):
        """Adds vote to record."""
        voted = json.loads(self.voted)
        voted.append(actor.username)
        self.voted = json.dumps(voted)

    def yeas_have_majority(self):
        """Helper method, returns True if yeas currently have majority."""
        if self.yeas > (self.nays + self.abstains):
            return True
        return False

    def yeas_have_plurality(self):
        """Helper method, returns True if yeas currently have plurality."""
        if self.yeas > self.nays and self.yeas > self.abstains:
            return True
        return False

    def current_standing(self):
        """If voting ended right now, returns what the status would be."""
        if self.require_majority or not self.allow_abstain:
            if self.yeas_have_majority():
                return "approved"
            return "rejected"
        else:
            if self.yeas_have_plurality():
                return "approved"
            return "rejected"

    def voting_time_remaining(self):
        """Gets time remaining to vote."""
        seconds_passed = (timezone.now() - self.voting_starts).total_seconds()
        hours_passed = seconds_passed / 360
        return self.voting_period - hours_passed

    def voting_deadline(self):
        """Gets deadline of vote given starting point and length of vote."""
        return self.voting_starts + datetime.timedelta(hours=self.voting_period)

    def describe_voting_period(self):
        """Gets human readable description of voting period."""
        units = utils.parse_duration_into_units(self.voting_period)
        return utils.display_duration_units(**units)

    # Required methods

    @classmethod
    def configurable_fields(cls):
        """Gets fields on condition which may be configured by user."""
        return {
            "allow_abstain": {"display": "Let people abstain from voting?"},
            "require_majority": {"display": "Require a majority rather than a plurality to pass?"},
            "publicize_votes": {"display": "Publicize peoples' votes?"},
            "voting_period": {"display": "How long should the vote go on, in hours?"},
            "vote_roles":
                {"display": "Roles who can vote", "type": "RoleListField",
                 "full_name": helpers.Changes().Conditionals.AddVote},
            "vote_actors":
                {"display": "People who can vote", "type": "ActorListField",
                 "full_name": helpers.Changes().Conditionals.AddVote}
        }

    def display_fields(self):
        """Gets condition fields in form dict format."""
        individual_votes = self.voted if self.publicize_votes else []
        return [
            # configuration data
            {"field_name": "allow_abstain", "field_value": self.allow_abstain, "hidden": False},
            {"field_name": "require_majority", "field_value": self.require_majority, "hidden": False},
            {"field_name": "publicize_votes", "field_value": self.publicize_votes, "hidden": False},
            {"field_name": "voting_period", "field_value": self.voting_period, "hidden": False},
            # instance-specific data
            {"field_name": "current_yeas", "field_value": self.yeas, "hidden": False},
            {"field_name": "current_nays", "field_value": self.nays, "hidden": False},
            {"field_name": "current_abstains", "field_value": self.abstains, "hidden": False},
            {"field_name": "individual_votes", "field_value": individual_votes, "hidden": not self.publicize_votes},
            {"field_name": "voting_deadline", "field_value": self.voting_deadline(), "hidden": False}
        ]

    def condition_status(self):
        """Gets status of condition."""
        if self.voting_time_remaining() <= 0:
            return self.current_standing()
        return "waiting"

    def display_status(self):
        """Gets 'plain English' display of status."""
        base_str = f"{self.yeas} yea votes vs {self.nays} nay votes"
        base_str += f" with {self.abstains} abstentions" if self.allow_abstain else ""
        if self.condition_status() == "waiting":
            base_str += f" and {self.voting_time_remaining()} time remaining. If the vote ended right now, " + \
                        f"the result would be: {self.current_standing()}."
        else:
            base_str += f". The vote ended with result {self.condition_status()}."
        return base_str

    def description_for_passing_condition(self, permission_data=None):
        """Gets plain English description of what must be done to pass the condition."""
        return utils.description_for_passing_voting_condition(condition=self, permission_data=permission_data)


class ConsensusCondition(ConditionModel):
    """Consensus Condition class."""
    descriptive_name = "Consensus Condition"
    verb_name = "consense"
    has_timeout = True

    resolved = models.BooleanField(default=False)

    is_strict = models.BooleanField(default=False)
    responses = models.CharField(max_length=500, default="{}")

    minimum_duration = models.IntegerField(default=48)
    discussion_starts = models.DateTimeField(default=timezone.now)

    response_choices = ["support", "support with reservations", "stand aside", "block", "no response"]

    def initialize_condition(self, target, condition_dataclass, set_on):
        """Called when creating the condition, and passed condition_data and permission data."""

        client = helpers.Client(target=target.get_owner())
        participants = set([])

        for permission in condition_dataclass.data.get("permission_data"):
            if permission["permission_type"] == helpers.Changes().Conditionals.RespondConsensus:
                if permission.get("permission_roles"):
                    for role in permission["permission_roles"]:
                        for user in client.Community.get_users_given_role(role_name=role):
                            participants.add(user)
                if permission.get("permission_actors"):
                    for actor in permission["permission_actors"]:
                        participants.add(int(actor))

        if set_on == "owner":
            for actor in client.Community.get_users_with_ownership_privileges():
                participants.add(int(actor))

        if set_on == "governor":
            for actor in client.Community.get_users_with_governorship_privileges():
                participants.add(int(actor))

        self.create_response_dictionary(participant_pk_list=list(participants))

    def condition_status(self):
        if not self.resolved:
            return "waiting"
        return self.current_result()

    def current_result(self):
        if self.is_strict:
            if self.full_participation():
                if self.has_blocks() or not self.has_support():
                    return "rejected"
                return "approved"
            return "rejected"
        else:
            if self.has_blocks() or not self.has_support():
                return "rejected"
            return "approved"

    def create_response_dictionary(self, participant_pk_list):
        response_dict = {pk: "no response" for pk in participant_pk_list}
        self.responses = json.dumps(response_dict)

    def get_responses(self):
        return json.loads(self.responses)

    def has_support(self):
        for user, response in self.get_responses().items():
            if response in ["support", "support with reservations"]:
                return True
        return False

    def full_participation(self):
        for user, response in self.get_responses().items():
            if response == "no response":
                return False
        return True

    def has_blocks(self):
        for user, response in self.get_responses().items():
            if response == "block":
                return True
        return False

    def time_until_duration_passed(self):
        seconds_passed = (timezone.now() - self.discussion_starts).total_seconds()
        hours_passed = seconds_passed / 360
        return self.minimum_duration - hours_passed

    def time_remaining_display(self):
        time_remaining = self.time_until_duration_passed()
        units = utils.parse_duration_into_units(time_remaining)
        return utils.display_duration_units(**units)

    def duration_display(self):
        units = utils.parse_duration_into_units(self.minimum_duration)
        return utils.display_duration_units(**units)

    def ready_to_resolve(self):
        if self.time_until_duration_passed() <= 0:
            return True
        return False

    def is_participant(self, actor):
        for user, response in self.get_responses().items():
            if int(user) == int(actor.pk):
                return True
        return False

    def add_response(self, actor, new_response):
        responses = self.get_responses()
        for user, response in responses.items():
            if int(user) == int(actor.pk):
                responses[user] = new_response
        self.responses = json.dumps(responses)

    def display_fields(self):
        """Gets condition fields in form dict format, for displaying in the condition component."""
        return [
            # configuration data
            {"field_name": "minimum_duration", "field_value": self.duration_display(), "hidden": False},
            {"field_name": "time_remaining", "field_value": self.time_remaining_display(), "hidden": False},
            {"field_name": "responses", "field_value": self.get_responses(), "hidden": False},
            {"field_name": "response_options", "field_value": self.response_choices, "hidden": False},
            {"field_name": "can_be_resolved", "field_value": self.ready_to_resolve(), "hidden": False},
            {"field_name": "current_result", "field_value": self.current_result(), "hidden": False}
        ]

    def display_status(self):
        """Gets 'plain English' display of status."""
        consensus_type = "strict" if self.is_strict else "loose"
        if self.resolved:
            return f"The discussion has ended with result {self.condition_status} under {consensus_type} consensus"
        return f"The discussion is ongoing with {self.time_remaining_display()}. If the discussion ended now, " + \
               f"the result would be: {self.current_result()}"

    def description_for_passing_condition(self, permission_data=None):
        """Gets plain English description of what must be done to pass the condition."""
        return utils.description_for_passing_consensus_condition(self, permission_data)

    @classmethod
    def configurable_fields(cls):
        """Gets fields on condition which may be configured by user."""
        return {
            "is_strict": {"display": "Use strict consensus mode? (Defaults to loose.)"},
            "minimum_duration": {"display": "What is the minimum amount of time for discussion?"},
            "participant_roles":
                {"display": "Roles who can participate in the discussion", "type": "RoleListField",
                 "full_name": helpers.Changes().Conditionals.RespondConsensus},
            "participant_actors":
                {"display": "People who can participate in the discussion", "type": "ActorListField",
                 "full_name": helpers.Changes().Conditionals.RespondConsensus},
            "resolver_roles":
                {"display": "Roles who can end discussion", "type": "RoleListField",
                 "full_name": helpers.Changes().Conditionals.ResolveConsensus},
            "resolver_actors":
                {"display": "People who can end discussion", "type": "ActorListField",
                 "full_name": helpers.Changes().Conditionals.ResolveConsensus}
        }


# Set up signals so that when a condition is updated, the action it's linked to is retried.

@receiver(retry_action_signal)
def retry_action(sender, instance, created, **kwargs):
    """Signal handler which retries the corresponding action or action container when condition has been updated."""
    if not created:
        client = helpers.Client()
        action = client.Action.get_action_given_pk(pk=instance.action)
        client.Action.retake_action(action=action)


for conditionModel in [ApprovalCondition, VoteCondition, ConsensusCondition]:
    post_save.connect(retry_action, sender=conditionModel)
