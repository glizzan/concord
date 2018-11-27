import json

from actions.state_changes import BaseStateChange

from conditionals.models import ConditionTemplate


###################################
### All Condition State Changes ###
###################################

class AddConditionStateChange(BaseStateChange):
    name = "conditional_addcondition"

    def __init__(self, condition_type, condition_data, permission_data, conditioned_object_type):
        self.condition_type = condition_type
        self.condition_data = condition_data if condition_data else "{}"
        self.permission_data = permission_data
        self.conditioned_object_type = conditioned_object_type

    def validate(self, actor, target):
        return True

    def implement(self, actor, target):
        return ConditionTemplate.objects.create(
            owner = actor, 
            condition_type=self.condition_type,
            condition_data=self.condition_data,
            permission_data=self.permission_data,
            conditioned_object=target.pk,
            conditioned_object_type=self.conditioned_object_type
        )

class RemoveConditionStateChange(BaseStateChange):
    name = "conditional_removecondition"

    def __init__(self, condition_pk):
        self.condition_pk = condition_pk
        # TODO: maybe add ability to remove condition by giving the target's ID & type?
        # self.conditioned_object = conditioned_object
        # self.conditioned_object_type = conditioned_object_type

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
    name = "conditionalvote_addvote"

    def __init__(self, vote):
        self.vote = vote

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
    name = "conditional_approvecondition"

    def validate(self, actor, target):
        return True

    def implement(self, actor, target):
        target.approve()
        target.save()
        return True