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
from django.core.exceptions import ValidationError

from concord.actions.models import PermissionedModel
from concord.actions.client import ActionClient
from concord.permission_resources.client import PermissionResourceClient
from concord.actions.state_changes import Changes


##################################
### Conditional Resource/Items ###
##################################


class ConditionModel(PermissionedModel):

    class Meta:
        abstract = True

    action =  models.IntegerField()
    descriptive_name = "condition"

    @classmethod
    @abstractmethod
    def get_configurable_fields(cls):
        '''All conditions must supply their own version of the get_configurable_fields method, 
        which should return a dict with field names as keys and field objects as values.'''
        return {}
    
    @classmethod
    def get_slug(cls):
        return cls.__name__.lower()

    def get_name(self):
        return "%s (%d)" % (self.descriptive_name, self.pk)

    def get_url(self):
        return reverse('conditionals:condition_detail', kwargs={'action_pk': self.action })

    def get_display_string(self):
        return self.descriptive_name

    def get_action(self):
        ac = ActionClient(system=True)
        return ac.get_action_given_pk(pk=self.action)

    def description_permissions(self):
        prc = PermissionResourceClient(system=True)  # FIXME: should be actor, no?
        permissions = prc.get_permissions_on_object(object=self)
        display_permissions = []
        for permission in permissions:
            display_permissions.append(permission.display_string())
        return display_permissions

    @classmethod
    def get_form_dict_for_field(cls, field):
        return { 'name': field.field.name, 'type': field.field.__class__.__name__, 
            'required': "required" if field.field.blank else "", 'value': field.field.default }


class ApprovalCondition(ConditionModel):

    descriptive_name = "Approval Condition"
    verb_name = "approve"

    approved = models.BooleanField(null=True, blank=True)  # Null by default
    self_approval_allowed = models.BooleanField(default=False)

    def condition_status(self):
        if self.approved == True:
            return "approved"
        if self.approved == False:
            return "rejected"
        return "waiting"

    def approve(self):
        self.approved = True
    
    def reject(self):
        self.approved = False

    @classmethod
    def get_configurable_fields(cls):
        return {          
            "self_approval_allowed": { "display": "Can individuals approve their own actions?",
                **cls.get_form_dict_for_field(getattr(cls, "self_approval_allowed"))},
            "approve_roles" : { "display": "Roles who can approve", "type": "PermissionRoleField", "required": False, 
                "value": None, "field_name": "approve_roles" },
            "approve_actors" : { "display": "People who can approve", "type": "PermissionActorField", "required": False, 
                "value": None, "field_name": "approve_actors" },
            "reject_roles" : { "display": "Roles who can reject", "type": "PermissionRoleField", "required": False, 
                "value": None, "field_name": "reject_roles" },
            "reject_actors": { "display": "People who can reject", "type": "PermissionActorField", "required": False, 
                "value": None, "field_name": "reject_actors" }
        }

    def get_data_from_permission_field(self, field_name):
        perm_dict = {
            "approve_roles": Changes.Conditionals.Approve,
            "approve_actors": Changes.Conditionals.Approve,
            "reject_roles": Changes.Conditionals.Reject,
            "reject_actors": Changes.Conditionals.Reject
        }
        return perm_dict[field_name], field_name.split("_")[1]

    def description_for_passing_condition(self):
        return "one person needs to approve this action"

    def description_status(self):
        status = self.condition_status()
        if status == "waiting":
            return "waiting for approval"
        elif status == "rejected":
            return "not approved"
        else:
            return "approved"


class VoteCondition(ConditionModel):

    descriptive_name = "Vote Condition"
    verb_name = "vote"

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

    @classmethod
    def get_configurable_fields(cls):
        return {
            "allow_abstain": { "display": "Let people abstain from voting?",
                **cls.get_form_dict_for_field(getattr(cls, "allow_abstain")) },
            "require_majority": { "display": "Require a majority rather than a plurality to pass?",
                **cls.get_form_dict_for_field(getattr(cls, "require_majority")) },
            "publicize_votes": { "display": "Publicize peoples' votes?",
                **cls.get_form_dict_for_field(getattr(cls, "publicize_votes")) },
            "voting_period":  { "display": "How long should the vote go on, in hours?",
                ** cls.get_form_dict_for_field(getattr(cls, "voting_period")) },
            "vote_roles" : { "display": "Roles who can vote", "type": "PermissionRoleField", 
                "required": False, "value": None, "field_name": "vote_roles" },
            "vote_actors": { "display": "People who can vote", "type": "PermissionActorField", 
                "required": False, "value": None, "field_name": "vote_actors" },
        }

    def get_data_from_permission_field(self, field_name):
        perm_dict = {
            "vote_roles": Changes.Conditionals.AddVote,
            "vote_actors": Changes.Conditionals.AddVote
        }
        return perm_dict[field_name], field_name.split("_")[1]

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

    def condition_status(self):
        if self.voting_time_remaining() <= 0:
            return self.current_standing()
        return "waiting"

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

    def description_for_passing_condition(self):
        # string = "a group of people must vote by %s" % self.voting_deadline().strftime("%Y-%m-%d at %H:%M:%S")
        if self.require_majority:
            return "a majority of people vote for it within %s" % self.describe_voting_period()
        return "a plurality of people vote for it within %s" % self.describe_voting_period()

    def description_status(self):

        base_string = "%d yea votes vs %d nay votes" % (self.yeas, self.nays)
        if self.allow_abstain:
            base_string += " with %s abstentions" % self.abstains
        
        standing = self.current_standing()

        if self.condition_status() == "waiting":
            base_string += " and %s time remaining" % self.voting_time_remaining()
            base_string += ". If the vote ended right now, the result would be: %s" % status
        else:
            base_string += ". The vote ended with result %s." % self.condition_status()

        return base_string


# Set up signals so that when a condition is updated, the action it's linked to is retried.
        
def retry_action(sender, instance, created, **kwargs):
    if not created:
        actionClient = ActionClient(system=True)
        action = actionClient.get_action_given_pk(pk=instance.action)
        action.take_action()  # FIXME: make this a client call as well.

for conditionModel in [ApprovalCondition, VoteCondition]:  # FIXME: should be auto-detected
    post_save.connect(retry_action, sender=conditionModel)


##########################
### ConditionTemplates ###
##########################

class ConditionTemplate(PermissionedModel):
    """
    condition_type - one of the concrete ConditionModel types specified in this file
    condition_data - configures a condition that isn't simply using defaults, for instance
                     making the voting period longer or setting self-approval to True
    permission_data - this data is used to create a permissions resource for the condition,
                     otherwise the default permission is used  

    conditioned_object is either permission or community, generic relations have been added to those
    models for ease of reference.
    """

    condition_type = models.CharField(max_length=400)  # Replace with choices field???
    condition_data = models.CharField(max_length=400, blank=True, null=True)
    permission_data = models.CharField(max_length=400, blank=True, null=True)

    conditioned_object_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    conditioned_object_id = models.PositiveIntegerField()
    conditioned_object = GenericForeignKey('conditioned_object_content_type', 'conditioned_object_id')

    COMMUNITY_CHOICES = (
        ('gov', 'Governor'),
        ('own', 'Owner'),
    )
    target_type = models.CharField(max_length=3, blank=True, null=True, choices=COMMUNITY_CHOICES)

    def __str__(self):
        return "%s Condition on %s (configuration: %s, permission: %s) " % (self.condition_type, 
            str(self.conditioned_object), str(self.condition_data), str(self.permission_data))

    def get_name(self):
        return self.__str__()

    def get_data_as_json(self):
        # FIXME: this is a hack until we refactor these fields to be customfields and
        # jsonfields, not sad permissive charfields 
        try:
            condition_data = json.loads(self.condition_data)
        except:
            condition_data = self.condition_data
        try:
            permission_data = json.loads(self.permission_data)
        except:
            permission_data = self.permission_data

        return json.dumps({
                "condition_type": self.condition_type,
                "condition_data": condition_data,
                "permission_data": permission_data,
                "target_type": self.target_type
        })

    def get_condition_type_class(self, lookup_string=None):
        # lookup_string is used when doing an uninstantiated lookup
        condition_dict = {
            "approvalcondition": ApprovalCondition,
            "votecondition": VoteCondition
        }
        condition = lookup_string if lookup_string else self.condition_type
        return condition_dict[condition]

    def get_condition_description(self):
        condition_model = self.get_condition_type_class()
        condition_instance = condition_model(json.loads(self.condition_data))
        return condition_instance.description_for_passing_condition()

    def get_permission_data_options(self):
        return self.get_condition_type_class().get_condition_permissions()

    def get_permission_data(self):
        return json.loads(self.permission_data)

    def set_permission_data(self, permission_data):
        self.permission_data = json.dumps(permission_data)
        pass

    def validate_permission_data_formatting(self, data_dict):
        if not (hasattr(data_dict, "roles") or hasattr(data_dict, "actors")):
            return False
        if hasattr(data_dict, "roles"):
            if type(data_dict["roles"]) != list:
                return False
        if hasattr(data_dict, "actors"):
            if type(data_dict["roles"]) != list:
                return False
        return True

    def has_actor_or_role(self, data_dict):
        if self.validate_permission_data_formatting(data_dict):
            if hasattr(data_dict, "roles") and len(data_dict["roles"]) > 0:
                return True
            if hasattr(data_dict, "actors") and len(data_dict["actors"]) > 0:
                return True
        return False

    def validate_permission_data(self, permission_data):
        """Permission data should be a dict with the following format:
        { "ApprovalStateChange": { "roles": [], "actors": [] }, "RejectStateChange: { "roles": [], "actors": [] } } """

        for change_type, change_info in self.get_permission_data_options.items():
            if change_info['required']:
                if change_type not in permission_data:
                    raise ValidationError("Permission " + change_type + " is required but was not supplied.")
                if not self.has_actor_or_role(permission_data[change_type]):
                    raise ValidationError("Permission " + change_type + " is required, so at least one actor or role must be specified.")
            else:
                if not self.validate_permission_data_formatting(permission_data[change_type]):
                    raise ValidationError("Permission " + change_type + " is incorrectly formatted.")

    def get_configurable_fields_with_data(self):

        condition_data = json.loads(self.condition_data)
        permission_data = json.loads(self.permission_data) if self.permission_data else {}

        field_list = []        
        
        condition = self.get_condition_type_class()
        fields = condition.get_configurable_fields()

        for field_name, field in fields.items():
            if field["type"] in ["PermissionRoleField", "PermissionActorField"]:
                if field["field_name"] in permission_data:
                    field["value"] = permission_data[field["field_name"]]
            else:
                if field_name in condition_data:
                    field["value"] = condition_data[field_name]
            field_list.append(field)

        return field_list