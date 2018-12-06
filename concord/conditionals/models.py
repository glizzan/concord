"""
When we set a condition on a permission, we need to store two types of info.  First, 
we need to know what type of condition the permission requires.  Second, we need to store
the status of each instantiation of a condition on a per action basis.

The flow goes like this:

Check_condition from action/permissions.py or from communities/models.py asks "hey is
there a condition set on this permission?"  If no, it moves on.  If yes, it asks,
"okay well do we already have a conditional action for this specific action?"  If yes,
it gets the existing conditional action and checks the status.  If no, it creates the
conditional_action, and checks the status.

Breaking down the steps:

- Checking for a condition set on the permission requires looking for a corresponding 
ConditionTemplate model.
- Checking for a conditional action instantiated for a given action requires looking
for a corresponding ConditionalAction model.
- Creating a conditional action requires generating a conditional action from the
conditional template and giving it its own separate permission to restrict who can 
change the conditional.

Most of the conditional logic itself is in the conditional action models like 
ApproveCondition and  VoteCondition, which have corresponding state changes like 
ApproveStateChange, etc.
"""

import datetime
import json
import decimal

from django.db import models
from django.utils import timezone

from actions.models import PermissionedModel


##################################
### Conditional Resource/Items ###
##################################


class ConditionModel(PermissionedModel):

    class Meta:
        abstract = True

    action =  models.IntegerField()

    # Add a method that makes it easy to get the permission that the condition
    # is set on.  Maybe an emtpy condition_status or is_condition_met method with 
    # the decorator on it that means you'll get an error if it's not implemented.


class ApprovalCondition(ConditionModel):

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


class VoteCondition(ConditionModel):

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

    def current_results(self):
        results = { "yeas": self.yeas, "nays": self.nays }
        if self.allow_abstain:
            results.update({ "abstains": self.abstains })
        return results

    def has_voted(self, actor):
        voted = json.loads(self.voted)
        if actor in voted:
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
        voted.append(actor)
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

    def condition_status(self):
        if self.voting_time_remaining() <= 0:
            if self.require_majority or not self.allow_abstain:
                if self.yeas_have_majority():
                    return "approved"
                return "rejected"
            else:
                if self.yeas_have_plurality():
                    return "approved"
                return "rejected"
        return "waiting"


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
