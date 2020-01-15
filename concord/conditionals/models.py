import datetime
import json
import decimal
from abc import abstractmethod

from django.db import models
from django.utils import timezone
from django.urls import reverse
from django.db.models.signals import post_save

from concord.actions.models import PermissionedModel
from concord.actions.client import ActionClient
from concord.permission_resources.client import PermissionResourceClient


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
        which should return a dict with field names as keys and field objects (ie BooleanField) 
        as values.'''
        return {}
    
    @classmethod
    def get_slug(cls):
        return cls.__name__.lower()
    # TODO: Add method for getting permission a given condition is set on.

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


class ApprovalCondition(ConditionModel):

    descriptive_name = "Approval Condition"

    approved = models.BooleanField(null=True)  # Null by default
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
        return {"self_approval_allowed": BooleanField}

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
    voting_starts = models.DateTimeField(auto_now_add=True)
    voting_period = models.FloatField(default=168)

    @classmethod
    def get_configurable_fields(cls):
        return {
            "allow_abstain": BooleanField,
            "require_majority": BooleanField,
            "publicize_votes": BooleanField,
            "voting_period": FloatField
        }

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
        microseconds_passed = (timezone.now() - self.voting_starts).microseconds
        hours_passed = microseconds_passed / 360000000
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

    def description_for_passing_condition(self):
        string = "a group of people must vote by %s" % self.voting_deadline().strftime("%Y-%m-%d at %H:%M:%S")
        if self.require_majority:
            string += "(a majority of voters is required)"
        return string

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
    conditioned_object - pk of the thing the condition is set on
    conditioning_choices - currently only 'permission' or (less likely) 'community_governor', 
                    'community_owner'
    """

    condition_type = models.CharField(max_length=400)  # Replace with choices field???
    condition_data = models.CharField(max_length=400, blank=True, null=True)
    permission_data = models.CharField(max_length=400, blank=True, null=True)
    conditioned_object = models.IntegerField()  
    conditioning_choices = models.CharField(max_length=18, default="permission")

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
                "permission_data": permission_data
        })




