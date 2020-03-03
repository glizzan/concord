from typing import Dict
import json

from django.contrib.contenttypes.models import ContentType

from concord.actions.state_changes import BaseStateChange
from concord.conditionals.models import ConditionTemplate


###################################
### All Condition State Changes ###
###################################

class AddConditionStateChange(BaseStateChange):
    description = "Add condition"

    def __init__(self, *, condition_type: str, permission_data: Dict, condition_data: Dict, 
        target_type=None):
        self.condition_type = condition_type
        self.condition_data = condition_data if condition_data else "{}"
        self.permission_data = permission_data
        self.target_type = target_type

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community
        from concord.permission_resources.models import PermissionsItem
        return [Community, PermissionsItem]    

    def description_present_tense(self):
        return "add condition %s to %s" % (self.condition_type, self.target_type)  

    def description_past_tense(self):
        return "added condition %s to %s" % (self.condition_type, self.target_type)

    def validate(self, actor, target):
        return True

    def implement(self, actor, target):
        return ConditionTemplate.objects.create(
            owner = target.get_owner(), 
            condition_type=self.condition_type,
            condition_data=self.condition_data,
            permission_data=self.permission_data,
            conditioned_object_content_type = ContentType.objects.get_for_model(target),
            conditioned_object_id=target.pk,
            target_type=self.target_type)


class RemoveConditionStateChange(BaseStateChange):
    description = "Remove condition"

    def __init__(self, condition_pk):
        self.condition_pk = condition_pk

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community
        from concord.permission_resources.models import PermissionsItem
        return [Community, PermissionsItem]    

    def description_present_tense(self):
        return "remove condition %s" % (self.condition_pk)  

    def description_past_tense(self):
        return "removed condition %s" % (self.condition_pk)  

    def validate(self, actor, target):
        # If we add ability to remove by giving target, check that target == conditioned object
        return True

    def implement(self, actor, target):
        template = ConditionTemplate.objects.get(pk=self.condition_pk)
        template.delete()
        return True


class ChangeConditionStateChange(BaseStateChange):
    description = "Change condition"

    def __init__(self, condition_pk, permission_data: Dict, condition_data: Dict):
        # Note that only permission data and condition data are changeable, if you want to switch
        # the condition type, owner, etc, you'll have to remove and add another.
        self.condition_pk = condition_pk
        self.condition_data = condition_data if condition_data else "{}"
        self.permission_data = permission_data

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community
        from concord.permission_resources.models import PermissionsItem
        return [Community, PermissionsItem]    

    def description_present_tense(self):
        return "change condition %s" % (self.condition_pk)  

    def description_past_tense(self):
        return "changed condition %s" % (self.condition_pk)  

    def validate(self, actor, target):
        return True

    def implement(self, actor, target):
        template = ConditionTemplate.objects.get(pk=self.condition_pk)
        template.condition_data = self.condition_data
        template.permission_data = self.permission_data
        template.save()
        return template


####################################
### Vote Condition State Changes ###
####################################


class AddVoteStateChange(BaseStateChange):
    description = "Add vote"

    def __init__(self, vote):
        self.vote = vote

    @classmethod
    def get_allowable_targets(cls):
        from concord.conditionals.models import VoteCondition
        return [VoteCondition]    

    def description_present_tense(self):
        return "add vote %s" % (self.vote)  

    def description_past_tense(self):
        return "added vote %s" % (self.vote)

    def validate(self, actor, target):
        """
        To validate the vote, we need to check that:
        a) the voter hasn't voted before
        b) if the vote is abstain, abstentions are allowed
        """
        if self.vote not in ["yea", "nay", "abstain"]:
            self.set_validation_error("Vote type must be 'yea', 'nay' or 'abstain', not %s" % self.vote)
            return False
        if target.has_voted(actor):
            self.set_validation_error("Actor may only vote once")
            return False
        if not target.allow_abstain and self.vote == "abstain":
            self.set_validation_error("Actor abstained but this vote does not allow abstentions.")
            return False
        return True

    def implement(self, actor, target):
        target.add_vote(self.vote)
        target.add_vote_record(actor)
        target.save()
        return True


#######################################
### Approve Condition State Changes ###
#######################################


class ApproveStateChange(BaseStateChange):
    description = "Approve"

    @classmethod
    def get_allowable_targets(cls):
        from concord.conditionals.models import ApprovalCondition
        return [ApprovalCondition]    

    def description_present_tense(self):
        return "approve"

    def description_past_tense(self):
        return "approved"

    def validate(self, actor, target):

        # If approval condition allows self approval, we can simply return True here.
        if target.self_approval_allowed:
            return True
            
        from concord.actions.models import Action
        action = Action.objects.get(pk=target.action)
        if action.actor == actor:
            return False

        return True

    def implement(self, actor, target):
        target.approve()
        target.save()
        return True


class RejectStateChange(BaseStateChange):
    description = "Reject"

    @classmethod
    def get_allowable_targets(cls):
        from concord.conditionals.models import ApprovalCondition
        return [ApprovalCondition]    

    def description_present_tense(self):
        return "reject"

    def description_past_tense(self):
        return "rejected"

    def validate(self, actor, target):
        """Checks if actor is the same user who sent the action that triggered the condition
        and, unless self approval is allowed, rejects them as invalid."""

        # If approval condition allows self approval, we can simply return True here.
        if target.self_approval_allowed:
            return True
            
        from concord.actions.models import Action
        action = Action.objects.get(pk=target.action)
        if action.actor == actor:
            return False

        return True

    def implement(self, actor, target):
        target.reject()
        target.save()
        return True