import datetime
import json
import decimal
from abc import abstractmethod
from collections import namedtuple

from django.db import models
from django.utils import timezone
from django.urls import reverse
from django.db.models.signals import post_save
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.dispatch import receiver

from concord.actions.models import PermissionedModel
from concord.actions.utils import Changes, Client, get_all_conditions
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

    action =  models.IntegerField()
    source_id = models.CharField(max_length=20)

    descriptive_name = "condition"
    has_timeout = False

    is_condition = True

    def get_name(self):
        return "%s (%d)" % (self.descriptive_name, self.pk)

    def get_model_name(self):
        return self.__class__.__name__.lower()

    def get_url(self):
        return reverse('conditionals:condition_detail', kwargs={'action_pk': self.action })

    def get_display_string(self):
        return self.descriptive_name

    def get_action(self):
        return Client().Action.get_action_given_pk(pk=self.action)

    def get_configurable_fields_with_data(self, permission_data=None):
        """Returns form_dict with condition data set as value."""

        form_dict = self.configurable_fields()
        
        for field_name, field_dict in form_dict.items():

            if field_dict["type"] in ["PermissionRoleField", "PermissionActorField"]:
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

    # Class methods with default implementation

    @classmethod
    def get_slug(cls):
        return cls.__name__.lower()

    @classmethod
    def get_configurable_fields(cls):
        """Returns field values as list instead of dict"""
        return [ value for key, value in cls.configurable_fields().items() ]

    @classmethod
    def get_configurable_field_names(cls):
        """Return field names as list."""
        return [ key for key, value in cls.configurable_fields().items() ]

    @classmethod
    def get_form_dict_for_field(cls, field):
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
        '''All conditions must supply their own version of the configurable_fields method, 
        which should return a dict with field names as keys and field objects as values.'''
        return {}

    @abstractmethod
    def description_for_passing_condition(self, fill_dict):
        """This method returns a verbose, human-readable description of what will fulfill this condition.  It optionally
        accepts permission data from the configured condition_template to be more precise about who can do what."""
        pass

    @abstractmethod
    def display_fields(self):
        """This method returns a list of fields and their values which can be shown to the user. Some overlap with
        get_configurable_fields_with_data since in many cases we're just showing the configured fields, but some
        data may be specific to the condition instance.  Note that we do not, for now, return permission data."""
        pass

    @abstractmethod
    def condition_status(self):
        """This method returns one of status 'approved', 'rejected', or 'waiting', after checking the condition
        for its unqiue status logic."""
        pass

    @abstractmethod
    def display_status(self):
        """This method returns a more verbose, human-readable description of the condition status, after checking
        the condition for its unique status logic."""
        pass


class ApprovalCondition(ConditionModel):

    descriptive_name = "Approval Condition"
    verb_name = "approve"

    approved = models.BooleanField(null=True, blank=True)  # Null by default
    self_approval_allowed = models.BooleanField(default=False)

    def approve(self):
        self.approved = True
    
    def reject(self):
        self.approved = False

    # Required methods

    @classmethod
    def configurable_fields(cls):
        return {          
            "self_approval_allowed": { "display": "Can individuals approve their own actions?",
                **cls.get_form_dict_for_field(cls._meta.get_field("self_approval_allowed"))},
            "approve_roles" : { "display": "Roles who can approve", "type": "PermissionRoleField", "required": False, 
                "value": None, "field_name": "approve_roles", "full_name": Changes().Conditionals.Approve },
            "approve_actors" : { "display": "People who can approve", "type": "PermissionActorField", "required": False, 
                "value": None, "field_name": "approve_actors", "full_name": Changes().Conditionals.Approve },
            "reject_roles" : { "display": "Roles who can reject", "type": "PermissionRoleField", "required": False, 
                "value": None, "field_name": "reject_roles", "full_name": Changes().Conditionals.Reject },
            "reject_actors": { "display": "People who can reject", "type": "PermissionActorField", "required": False, 
                "value": None, "field_name": "reject_actors", "full_name": Changes().Conditionals.Reject }
        }

    def display_fields(self):
        return [{ "field_name": "self_approval_allowed", "field_value": self.self_approval_allowed, "hidden": False }]

    def condition_status(self):
        if self.approved == True:
            return "approved"
        if self.approved == False:
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
        if self.has_voted(user):
            return False, "has voted"
        return True, "has not voted"

    def get_timeout(self):
        return self.voting_deadline()

    def current_results(self):
        results = { "yeas": self.yeas, "nays": self.nays }
        if self.allow_abstain:
            results.update({ "abstains": self.abstains })
        return results

    def has_voted(self, actor):
        voted = json.loads(self.voted)
        if actor.username in voted:
            return True
        return False

    def add_vote(self, vote):
        if vote == "yea":
            self.yeas += 1
        elif vote == "nay":
            self.nays += 1
        elif vote == "abstain":
            self.abstains += 1

    def add_vote_record(self, actor):
        voted = json.loads(self.voted)
        voted.append(actor.username)
        self.voted = json.dumps(voted)

    def voting_time_remaining(self):
        seconds_passed = (timezone.now() - self.voting_starts).total_seconds()
        hours_passed = seconds_passed / 360
        return self.voting_period - hours_passed

    def voting_deadline(self):
        return self.voting_starts + datetime.timedelta(hours=self.voting_period)

    def yeas_have_majority(self):
        if self.yeas > (self.nays + self.abstains):
            return True
        return False

    def yeas_have_plurality(self):
        if self.yeas > self.nays and self.yeas > self.abstains:
            return True
        return False

    def current_standing(self):
        if self.require_majority or not self.allow_abstain:
            if self.yeas_have_majority():
                return "approved"
            return "rejected"
        else:
            if self.yeas_have_plurality():
                return "approved"
            return "rejected"

    def get_voting_period_in_units(self):
        weeks = int(self.voting_period / 168)
        time_remaining = self.voting_period - (weeks*168)
        days = int(time_remaining / 24)
        hours = time_remaining - (days*24)
        return weeks, days, hours

    def describe_voting_period(self):
        weeks, days, hours = self.get_voting_period_in_units()
        time_pieces = []
        if weeks > 0:
            time_pieces.append("%d weeks" % weeks if weeks > 1 else "1 week")
        if days > 0:
            time_pieces.append("%d days" % days if days > 1 else "1 day")
        if hours > 0:
            time_pieces.append("%d hours" % hours if hours > 1 else "1 hour")
        return ", ".join(time_pieces)

    # Required methods

    @classmethod
    def configurable_fields(cls):
        return {
            "allow_abstain": { "display": "Let people abstain from voting?",
                **cls.get_form_dict_for_field(cls._meta.get_field("allow_abstain")) },
            "require_majority": { "display": "Require a majority rather than a plurality to pass?",
                **cls.get_form_dict_for_field(cls._meta.get_field("require_majority")) },
            "publicize_votes": { "display": "Publicize peoples' votes?",
                **cls.get_form_dict_for_field(cls._meta.get_field("publicize_votes")) },
            "voting_period":  { "display": "How long should the vote go on, in hours?",
                **cls.get_form_dict_for_field(cls._meta.get_field("voting_period")) },
            "vote_roles" : { "display": "Roles who can vote", "type": "PermissionRoleField", 
                "required": False, "value": None, "field_name": "vote_roles", "full_name": Changes().Conditionals.AddVote },
            "vote_actors": { "display": "People who can vote", "type": "PermissionActorField", 
                "required": False, "value": None, "field_name": "vote_actors", "full_name": Changes().Conditionals.AddVote },
        }

    def display_fields(self):
        individual_votes = self.voted if self.publicize_votes else []
        return [
            # configuration data
            { "field_name": "allow_abstain", "field_value": self.allow_abstain, "hidden": False },
            { "field_name": "require_majority", "field_value": self.require_majority, "hidden": False },
            { "field_name": "publicize_votes", "field_value": self.publicize_votes, "hidden": False },
            { "field_name": "voting_period", "field_value": self.voting_period, "hidden": False},
            # instance-specific data
            { "field_name": "current_yeas", "field_value": self.yeas, "hidden": False },
            { "field_name": "current_nays", "field_value": self.nays, "hidden": False },
            { "field_name": "current_abstains", "field_value": self.abstains, "hidden": False },
            { "field_name": "individual_votes", "field_value": individual_votes, "hidden": not self.publicize_votes },
            { "field_name": "voting_deadline", "field_value": self.voting_deadline(), "hidden": False }
        ]

    def condition_status(self):
        if self.voting_time_remaining() <= 0:
            return self.current_standing()
        return "waiting"

    def display_status(self):
        base_str = f"{self.yeas} yea votes vs {self.nays} nay votes"
        base_str += f" with {self.abstains} abstentions" if self.allow_abstain else ""
        if self.condition_status() == "waiting":
            base_str += f" and {self.voting_time_remaining()} time remaining. If the vote ended right now, " + \
                           f"the result would be: {self.current_standing()}."
        else:
            base_str += f". The vote ended with result {self.condition_status()}."
        return base_str

    def description_for_passing_condition(self, fill_dict=None):
        return utils.description_for_passing_voting_condition(condition=self, fill_dict=None)


# Set up signals so that when a condition is updated, the action it's linked to is retried.
        
@receiver(retry_action_signal)
def retry_action(sender, instance, created, **kwargs):
    if not created:
        client = Client()
        action = client.Action.get_action_given_pk(pk=instance.action)
        if action.container is not None:
            container = client.Action.get_container_given_pk(pk=action.container)
            container.commit_actions()  # retry processing all actions in container
        else:
            client.Action.take_action(action=action)


for conditionModel in [ApprovalCondition, VoteCondition]:
    post_save.connect(retry_action, sender=conditionModel)
