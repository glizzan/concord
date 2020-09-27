"""State Changes for conditional models"""
from django.core.exceptions import ValidationError

from concord.actions.state_changes import BaseStateChange, InputField
from concord.actions.utils import Client
from concord.conditionals.models import VoteCondition, ApprovalCondition, ConsensusCondition
from concord.actions.models import Action


###################################
### All Condition State Changes ###
###################################


class SetConditionOnActionStateChange(BaseStateChange):
    """State change which actually creates a condition item associated with a specific action. I'm not actually 100%
    sure this should be a state change, since as far as I can tell this will always be triggered by the system
    internally, but we're doing it this way for now.  Also not sure if this should be split up into permission
    condition and leadership condition."""
    description = "Set condition on action"
    input_fields = [InputField(name="condition_type", type="CharField", required=True, validate=False),
                    InputField(name="condition_data", type="DictField", required=False, validate=False),
                    InputField(name="permission_data", type="DictField", required=False, validate=False),
                    InputField(name="permission_pk", type="ObjectIDField", required=False, validate=False),
                    InputField(name="community_pk", type="ObjectIDField", required=False, validate=False),
                    InputField(name="leadership_type", type="CharField", required=False, validate=False)]

    def __init__(self, *, condition_type, condition_data=None, permission_data=None, permission_pk=None,
                 community_pk=None, leadership_type=None):
        self.condition_type = condition_type
        self.condition_data = condition_data if condition_data else {}
        self.permission_data = permission_data if permission_data else {}
        self.permission_pk = permission_pk
        self.community_pk = community_pk
        self.leadership_type = leadership_type

    @classmethod
    def get_allowable_targets(cls):
        """Returns the classes that an action of this type may target."""
        from concord.actions.models import Action
        return [Action]

    def get_condition_class(self):
        """Gets the condition class object given the condition type."""
        return Client().Conditional.get_condition_class(condition_type=self.condition_type)

    def get_condition_verb(self):
        """Get the verb of the associated condition."""
        return self.get_condition_class().verb_name

    def get_owner(self):
        """The owner of the condition should be the community in which it is created.  For now, this means
        looking up permission and getting owner, or using community if community is set.

        Note that if multiple community models are being used, and the community pk passed in is not the
        primary/default model, this will break."""

        if self.permission_pk:
            permission = Client().PermissionResource.get_permission(pk=self.permission_pk)
            return permission.get_owner()

        if self.community_pk:
            return Client().Community.get_community(community_pk=self.community_pk)

    def generate_source_id(self):
        """Generates a source_id to use when creating condition item."""
        source_pk = self.permission_pk if self.permission_pk else self.community_pk
        source_type = "perm" if self.permission_pk else self.leadership_type
        return source_type + "_" + str(source_pk)

    def validate(self, actor, target):
        if not super().validate(actor=actor, target=target):
            return False

        if not self.permission_pk and not self.community_pk:
            self.set_validation_error(message="Must supply either permission_pk or community_pk when setting condition")
            return False

        if self.community_pk and not self.leadership_type:
            self.set_validation_error(message="Must supply leadership type ('own' or 'gov') if conditioning community")
            return False

        if target.__class__.__name__ not in ["Action"]:  # allow "MockAction"?
            self.set_validation_error(message="Target must be an action")
            return False

        if not self.condition_type:
            self.set_validation_error(message="You must set a condition type")
            return False

        if not Client().Conditional.is_valid_condition_type(self.condition_type):
            self.set_validation_error(message=f"condition_type must be a valid type not {self.condition_type}")
            return False

        try:
            condition_class = self.get_condition_class()
            source_id = self.generate_source_id()
            condition_class(action=target.pk, source_id=source_id, owner=self.get_owner(), **self.condition_data)
            return True
        except ValidationError as error:
            self.set_validation_error(message=error.message)
            return False

    def implement(self, actor, target):

        condition_class = self.get_condition_class()
        source_id = self.generate_source_id()

        condition_data = self.condition_data if self.condition_data else {}  # replaces none so ** doesn't give an error
        condition_instance = condition_class.objects.create(
            action=target.pk, source_id=source_id, owner=self.get_owner(), **condition_data)

        condition_instance.initialize_condition(target, condition_data, self.permission_data,
                                                self.leadership_type)
        condition_instance.save()

        return condition_instance


####################################
### Vote Condition State Changes ###
####################################


class AddVoteStateChange(BaseStateChange):
    """State change for adding a vote."""
    description = "Add vote"
    verb_name = "vote"
    section = "Vote"
    input_fields = [InputField(name="vote", type="CharField", required=True, validate=False)]

    def __init__(self, vote):
        self.vote = vote

    @classmethod
    def get_allowable_targets(cls):
        return [VoteCondition]

    def description_present_tense(self):
        return f"add vote {self.vote}"

    def description_past_tense(self):
        return f"added vote {self.vote}"

    def validate(self, actor, target):
        """
        To validate the vote, we need to check that:
        a) the voter hasn't voted before
        b) if the vote is abstain, abstentions are allowed
        """

        if not super().validate(actor=actor, target=target):
            return False

        if self.vote not in ["yea", "nay", "abstain"]:
            self.set_validation_error(f"Vote type must be 'yea', 'nay' or 'abstain', not {self.vote}")
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
    """State change for approving a condition."""
    description = "Approve"
    preposition = ""
    section = "Approval"
    verb_name = "approve"

    @classmethod
    def get_allowable_targets(cls):
        return [ApprovalCondition]

    def description_present_tense(self):
        return "approve"

    def description_past_tense(self):
        return "approved"

    def validate(self, actor, target):
        if not super().validate(actor=actor, target=target):
            return False

        # If approval condition allows self approval, we can simply return True here.
        if target.self_approval_allowed:
            return True

        action = Action.objects.get(pk=target.action)
        if action.actor == actor:
            self.set_validation_error("Self approval is not allowed.")
            return False

        return True

    def implement(self, actor, target):
        target.approve()
        target.save()
        return True


class RejectStateChange(BaseStateChange):
    """State change for rejecting a condition.."""
    description = "Reject"
    preposition = ""
    section = "Approval"
    verb_name = "reject"
    rejects_condition = True

    @classmethod
    def get_allowable_targets(cls):
        return [ApprovalCondition]

    def description_present_tense(self):
        return "reject"

    def description_past_tense(self):
        return "rejected"

    def validate(self, actor, target):
        """Checks if actor is the same user who sent the action that triggered the condition
        and, unless self approval is allowed, rejects them as invalid."""
        if not super().validate(actor=actor, target=target):
            return False

        # If approval condition allows self approval, we can simply return True here.
        if target.self_approval_allowed:
            return True

        action = Action.objects.get(pk=target.action)
        if action.actor == actor:
            self.set_validation_error("Actor cannot approve or reject their own action.")
            return False

        return True

    def implement(self, actor, target):
        target.reject()
        target.save()
        return True


#########################################
### Consensus Condition State Changes ###
#########################################

class RespondConsensusStateChange(BaseStateChange):
    """State change for responding to a consensus condition"""
    description = "Respond"
    preposition = ""
    section = "Consensus"
    verb_name = "respond"
    input_fields = [InputField(name="response", type="CharField", required=True, validate=False)]

    def __init__(self, response):
        self.response = response

    @classmethod
    def get_allowable_targets(cls):
        return [ConsensusCondition]

    def description_present_tense(self):
        return f"respond with {self.response}"

    def description_past_tense(self):
        return f"responded with {self.response}"

    def validate(self, actor, target):
        """Checks that the actor is a participant."""
        if not super().validate(actor=actor, target=target):
            return False

        if self.response not in target.response_choices:
            self.set_validation_error(
                f"Response must be one of {', '.join(target.response_choices)}, not {self.response}")
            return False

        return True

    def implement(self, actor, target):
        target.add_response(actor, self.response)
        target.save()
        return self.response


class ResolveConsensusStateChange(BaseStateChange):
    """State change for resolving a consensus condition."""
    description = "Resolve"
    preposition = ""
    section = "Consensus"
    verb_name = "resolve"

    @classmethod
    def get_allowable_targets(cls):
        return [ConsensusCondition]

    def description_present_tense(self):
        return "resolve"

    def description_past_tense(self):
        return "resolved"

    def validate(self, actor, target):
        """Checks that the actor is a participant."""
        if not super().validate(actor=actor, target=target):
            return False

        if not target.ready_to_resolve():
            self.set_validation_error("The minimum duration of discussion has not yet passed.")
            return False

        return True

    def implement(self, actor, target):
        target.resolved = True
        target.save()
        return target
