"""Condition models."""

import datetime
import json
from abc import abstractmethod

from django.db import models
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver

from concord.actions.models import PermissionedModel
from concord.actions.utils import Changes, Client
from concord.conditionals import utils
from concord.conditionals.management.commands.check_condition_status import retry_action_signal


##################################
### Conditional Resource/Items ###
##################################


class ConditionModel(PermissionedModel):
    """
    Attributes:

    action: integer representing the pk of the action that triggered the creation of this condition
    source_id : consists of a type and a pk, separated by a _, for example "perm_" + str(permission_pk) or
                    "owner_" + str(community_pk)
    """

    class Meta:
        abstract = True

    action = models.IntegerField()
    source_id = models.CharField(max_length=20)

    descriptive_name = "condition"
    has_timeout = False

    is_condition = True

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
        return Client().Action.get_action_given_pk(pk=self.action)

    def get_configurable_fields_with_data(self, permission_data=None):
        """Returns form_dict with condition data set as value."""

        form_dict = self.configurable_fields()

        for field_name, field_dict in form_dict.items():

            if field_dict["type"] in ["RoleField", "RoleListField", "ActorField", "ActorListField"]:
                permission_field_value = permission_data.get(field_dict["field_name"], None)
                field_dict["value"] = permission_field_value if permission_field_value else field_dict["value"]
            else:
                field_dict["value"] = getattr(self, field_name)

        return form_dict

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
        return [value for key, value in cls.configurable_fields().items()]

    @classmethod
    def get_configurable_field_names(cls):
        """Return field names as list."""
        return [key for key, value in cls.configurable_fields().items()]

    @classmethod
    def get_form_dict_for_field(cls, field):
        """Get dictionary with form data for supplied field."""
        return {
            'field_name': field.name,
            'type': field.__class__.__name__,
            'required': "required" if field.blank else "",
            'value': field.default
        }

    # Methods models must implement themselves

    @classmethod
    @abstractmethod
    def configurable_fields(cls):
        """All conditions must supply their own version of the configurable_fields method,
        which should return a dict with field names as keys and field objects as values."""
        return {}

    @abstractmethod
    def description_for_passing_condition(self, fill_dict):
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
            "self_approval_allowed": {
                "display": "Can individuals approve their own actions?", "can_depend": False,
                **cls.get_form_dict_for_field(cls._meta.get_field("self_approval_allowed"))
            },
            "approve_roles": {
                "display": "Roles who can approve", "type": "RoleListField", "required": False,
                "can_depend": True, "value": None, "field_name": "approve_roles",
                "full_name": Changes().Conditionals.Approve
            },
            "approve_actors": {
                "display": "People who can approve", "type": "ActorListField", "required": False,
                "can_depend": True, "value": None, "field_name": "approve_actors",
                "full_name": Changes().Conditionals.Approve
            },
            "reject_roles": {
                "display": "Roles who can reject", "type": "RoleListField", "required": False,
                "can_depend": True, "value": None, "field_name": "reject_roles",
                "full_name": Changes().Conditionals.Reject
            },
            "reject_actors": {
                "display": "People who can reject", "type": "ActorListField", "required": False,
                "can_depend": True, "value": None, "field_name": "reject_actors",
                "full_name": Changes().Conditionals.Reject
            }
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

    def description_for_passing_condition(self, fill_dict=None):
        return utils.description_for_passing_approval_condition(fill_dict=fill_dict)


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
            "allow_abstain": {
                "display": "Let people abstain from voting?", "can_depend": False,
                **cls.get_form_dict_for_field(cls._meta.get_field("allow_abstain"))
            },
            "require_majority": {
                "display": "Require a majority rather than a plurality to pass?", "can_depend": False,
                **cls.get_form_dict_for_field(cls._meta.get_field("require_majority"))
            },
            "publicize_votes": {
                "display": "Publicize peoples' votes?", "can_depend": False,
                **cls.get_form_dict_for_field(cls._meta.get_field("publicize_votes"))
            },
            "voting_period": {
                "display": "How long should the vote go on, in hours?", "can_depend": False,
                **cls.get_form_dict_for_field(cls._meta.get_field("voting_period"))
            },
            "vote_roles": {
                "display": "Roles who can vote", "type": "RoleListField", "can_depend": True,
                "required": False, "value": None, "field_name": "vote_roles",
                "full_name": Changes().Conditionals.AddVote
            },
            "vote_actors": {
                "display": "People who can vote", "type": "ActorListField", "can_depend": True,
                "required": False, "value": None, "field_name": "vote_actors",
                "full_name": Changes().Conditionals.AddVote
            },
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

    def description_for_passing_condition(self, fill_dict=None):
        """Gets plain English description of what must be done to pass the condition."""
        return utils.description_for_passing_voting_condition(condition=self, fill_dict=None)


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

    def initialize_condition(self, target, condition_data, permission_data, leadership_type):
        """Called when creating the condition, and passed condition_data and permission data."""

        client = Client(target=target.target.get_owner())
        participants = set([])

        for permission in permission_data:
            if permission["permission_type"] == Changes().Conditionals.RespondConsensus:
                if permission.get("permission_roles"):
                    for role in permission["permission_roles"]:
                        for user in client.Community.get_users_given_role(role_name=role):
                            participants.add(user)
                if permission.get("permission_actors"):
                    for actor in permission["permission_actors"]:
                        participants.add(int(actor))

        if leadership_type == "owner":
            for action in client.get_users_with_ownership_privileges():
                participants.add(int(actor))

        if leadership_type == "governor":
            for action in client.get_users_with_governorship_privileges():
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

    def description_for_passing_condition(self, fill_dict=None):
        """Gets plain English description of what must be done to pass the condition."""
        return utils.description_for_passing_consensus_condition(self, fill_dict)

    @classmethod
    def configurable_fields(cls):
        """Gets fields on condition which may be configured by user."""
        return {
            "is_strict": {
                "display": "Use strict consensus mode? (Defaults to loose.)", "can_depend": False,
                **cls.get_form_dict_for_field(cls._meta.get_field("is_strict"))
            },
            "minimum_duration": {
                "display": "What is the minimum amount of time for discussion?", "can_depend": False,
                **cls.get_form_dict_for_field(cls._meta.get_field("minimum_duration"))
            },
            "participant_roles": {
                "display": "Roles who can participate in the discussion", "type": "RoleListField",
                "can_depend": True, "required": False, "value": None, "field_name": "participant_roles",
                "full_name": Changes().Conditionals.RespondConsensus
            },
            "participant_actors": {
                "display": "People who can participate in the discussion", "type": "ActorListField",
                "can_depend": True, "required": False, "value": None, "field_name": "participant_actors",
                "full_name": Changes().Conditionals.RespondConsensus
            },
            "resolver_roles": {
                "display": "Roles who can end discussion", "type": "RoleListField",
                "can_depend": True, "required": False, "value": None, "field_name": "resolver_roles",
                "full_name": Changes().Conditionals.ResolveConsensus
            },
            "resolver_actors": {
                "display": "People who can end discussion", "type": "ActorListField", "can_depend": True,
                "required": False, "value": None, "field_name": "resolver_actors",
                "full_name": Changes().Conditionals.ResolveConsensus
            }
        }


# Set up signals so that when a condition is updated, the action it's linked to is retried.

@receiver(retry_action_signal)
def retry_action(sender, instance, created, **kwargs):
    """Signal handler which retries the corresponding action or action container when condition has been updated."""
    if not created:
        client = Client()
        action = client.Action.get_action_given_pk(pk=instance.action)
        client.Action.retake_action(action=action)


for conditionModel in [ApprovalCondition, VoteCondition, ConsensusCondition]:
    post_save.connect(retry_action, sender=conditionModel)
