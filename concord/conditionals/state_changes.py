from typing import Dict
import json

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError

from concord.actions.state_changes import BaseStateChange


###################################
### All Condition State Changes ###
###################################


class SetConditionOnActionStateChange(BaseStateChange):
    """
    State change which actually creates a condition item associated with a specific action. I'm not actually 100%
    sure this should be a state change, since as far as I can tell this will always be triggered by the system
    internally, but we're doing it this way for now.  Also not sure if this should be split up into permission
    condition and leadership condition.  ¯\_(ツ)_/¯
    """
    description = "Set condition on action"

    def __init__(self, *, condition_type, condition_data=None, permission_pk=None, community_pk=None, 
        leadership_type=None):
        self.condition_type = condition_type  
        self.condition_data = condition_data if condition_data else {}
        self.permission_pk = permission_pk 
        self.community_pk = community_pk 
        self.leadership_type = leadership_type 

    def get_condition_class(self):
        from concord.conditionals.client import ConditionalClient
        return ConditionalClient(system=True).get_condition_class(condition_type=self.condition_type)

    def get_condition_verb(self):
        return self.get_condition_class().verb_name
    
    def get_owner(self):
        """The owner of the condition should be the community in which it is created.  For now, this means
        looking up permission and getting owner, or using community if community is set."""

        if self.permission_pk:
            from concord.permission_resources.client import PermissionResourceClient
            permClient = PermissionResourceClient(system=True)
            permission = permClient.get_permission(pk=self.permission_pk)
            return permission.get_owner()

        if self.community_pk:
            community_models = self.get_community_models()
            for model in community_models:
                found_communities = model.objects.filter(pk=self.community_pk)
                if len(found_communities) > 0:
                    return found_communities[0]     
            # NOTE: this is a bit of a hack, we need a better way to agnostically set the community_model
            # type here, and then we can just call get_community()  

    def generate_source_id(self):
        source_pk = self.permission_pk if self.permission_pk else self.community_pk
        source_type = "perm" if self.permission_pk else self.leadership_type
        return source_type + "_" + str(source_pk)

    def validate(self, actor, target):

        # FIXME: since this is internal, do we want to actually raise the errors here?

        if not self.permission_pk and not self.community_pk:
            self.set_validation_error(message="Must supply either permission_pk or community_pk when setting condition")
            return False

        if self.community_pk and not self.leadership_type:
            self.set_validation_error(message="Must supply leadership type ('own' or 'gov') if setting condition on community")
            return False

        if target.__class__.__name__ not in ["Action"]:  # allow "MockAction"?
            self.set_validation_error(message="Target must be an action")
            return False

        try:
            condition_class = self.get_condition_class()
            source_id = self.generate_source_id()
            condition_instance = condition_class(action=target.pk, source_id=source_id, owner=self.get_owner(),
                **self.condition_data)
            return True
        except ValidationError as error:
            self.set_validation_error(message=error.message)
            return False

    def implement(self, actor, target, save=True):

        condition_class = self.get_condition_class()
        source_id = self.generate_source_id()

        if save:
            condition_instance = condition_class.objects.create(action=target.pk, source_id=source_id, owner=self.get_owner(),
                **self.condition_data)
        else:
            condition_instance = condition_class(action=target.pk, source_id=source_id, owner=self.get_owner(),
                **self.condition_data)
        
        return condition_instance


####################################
### Vote Condition State Changes ###
####################################


class AddVoteStateChange(BaseStateChange):
    description = "Add vote"
    verb_name = "vote"
    action_helps_pass_condition = True

    def __init__(self, vote):
        self.vote = vote

    @classmethod
    def get_settable_classes(cls):
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

    def implement(self, actor, target, save=True):

        target.add_vote(self.vote)
        target.add_vote_record(actor)
        
        if save:
            target.save()
        
        return True


#######################################
### Approve Condition State Changes ###
#######################################


class ApproveStateChange(BaseStateChange):
    description = "Approve"
    preposition = ""
    verb_name = "approve"
    action_helps_pass_condition = True

    @classmethod
    def get_settable_classes(cls):
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
            self.set_validation_error("Self approval is not allowed.")
            return False

        return True

    def implement(self, actor, target, save=True):

        target.approve()
        
        if save:
            target.save()
        
        return True


class RejectStateChange(BaseStateChange):
    description = "Reject"
    preposition = ""
    verb_name = "reject"
    action_helps_pass_condition = False

    @classmethod
    def get_settable_classes(cls):
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
            self.set_validation_error("Actor cannot approve or reject their own action.")
            return False

        return True

    def implement(self, actor, target, save=True):

        target.reject()
        
        if save:
            target.save()
        
        return True