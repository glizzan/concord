from typing import Dict

import json

from concord.actions.state_changes import BaseStateChange

from concord.conditionals.models import ConditionTemplate


###################################
### All Condition State Changes ###
###################################

class AddConditionStateChange(BaseStateChange):
    description = "Add condition"

    def __init__(self, *, condition_type: str, permission_data: Dict, condition_data: Dict, 
        conditioning_choices: str):
        self.condition_type = condition_type
        self.condition_data = condition_data if condition_data else "{}"
        self.permission_data = permission_data
        self.conditioning_choices = conditioning_choices

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community, SubCommunity, SuperCommunity
        from concord.permission_resources.models import PermissionsItem
        return [Community, SubCommunity, SuperCommunity, PermissionsItem]    

    def description_present_tense(self):
        return "add condition %s to %s" % (self.condition_type, self.conditioning_choices)  

    def description_past_tense(self):
        return "added condition %s to %s" % (self.condition_type, self.conditioning_choices)

    def validate(self, actor, target):
        return True

    def implement(self, actor, target):
        self.owner = actor if target.owner_type == "ind" else target.get_owner()
        return ConditionTemplate.objects.create(
            owner = self.owner, 
            owner_type = target.owner_type,
            condition_type=self.condition_type,
            condition_data=self.condition_data,
            permission_data=self.permission_data,
            conditioned_object=target.pk,
            conditioning_choices=self.conditioning_choices
        )

class RemoveConditionStateChange(BaseStateChange):
    description = "Remove condition"

    def __init__(self, condition_pk):
        self.condition_pk = condition_pk
        # TODO: maybe add ability to remove condition by giving the target's ID & type?
        # self.conditioned_object = conditioned_object
        # self.conditioning_choices = conditioning_choices

    @classmethod
    def get_allowable_targets(cls):
        from concord.communities.models import Community, SubCommunity, SuperCommunity
        from concord.permission_resources.models import PermissionsItem
        return [Community, SubCommunity, SuperCommunity, PermissionsItem]    

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
        # TODO: I feel like we could provide more helpful responses here so they
        # know why it's invalid.
        if self.vote not in ["yea", "nay", "abstain"]:
            return False
        if target.has_voted(actor):
            return False
        if not target.allow_abstain and self.vote == "abstain":
            return False
        return True

    def implement(self, actor, target):
        # TODO: Maybe we should always re-validate before implementing in a state
        # change?
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