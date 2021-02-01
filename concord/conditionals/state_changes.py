"""State Changes for conditional models"""
from django.core.exceptions import ValidationError

from concord.actions.state_changes import BaseStateChange
from concord.utils.helpers import Client
from concord.utils.lookups import get_state_change_object
from concord.conditionals.models import VoteCondition, ApprovalCondition, ConsensusCondition
from concord.actions.models import Action
from concord.permission_resources.models import PermissionsItem
from concord.utils import field_utils


##########################################
### Add/Remove Condition State Changes ###
##########################################


class AddConditionStateChange(BaseStateChange):
    """State change to add condition to permission or leadership role."""

    descriptive_text = {
        "verb": "add",
        "default_string": "condition",
        "detail_string": "condition {condition_type}"
    }

    section = "Permissions"
    allowable_targets = ["all_community_models", PermissionsItem]

    condition_type = field_utils.CharField(label="Type of condition to add", required=True)
    condition_data = field_utils.DictField(label="Data for condition", null_value=dict)
    permission_data = field_utils.DictField(label="Data for permissions set on condition", null_value=list)
    leadership_type = field_utils.CharField(label="Type of leadership condition is set on")
    mode = field_utils.CharField(label="Condition mode", required=True)

    def validate(self, actor, target):

        if not super().validate(actor=actor, target=target):
            return False

        if not self.condition_type:
            self.set_validation_error(message="condition_type cannont be None")
            return False

        if not Client().Conditional.is_valid_condition_type(self.condition_type):
            message = f"condition_type must be a valid condition class not {self.condition_type}"
            self.set_validation_error(message=message)
            return False

        if hasattr(target, "is_community") and target.is_community:

            if not self.leadership_type:
                self.set_validation_error(message="leadership_type cannot be None")
                return False

            if self.leadership_type not in ["owner", "governor"]:
                self.set_validation_error(message="leadership_type must be 'owner' or 'governor'")
                return False

        ### validate condition_data

        condition_model = Client(actor="system").Conditional.get_condition_class(condition_type=self.condition_type)
        model_instance = condition_model()

        for field_name, field_value in self.condition_data.items():

            if type(field_value) == str and field_value[:2] == "{{":
                continue  # don't validate if it's a replaced field

            try:
                if hasattr(model_instance, "_meta") and hasattr(model_instance._meta, "get_field"):
                    field_instance = model_instance._meta.get_field(field_name)
                else:
                    field_instance = getattr(model_instance, field_name)
            except AttributeError:
                self.set_validation_error(message=f"There is no field {field_name} on condition {self.condition_type}")
                return False

            try:
                if hasattr(field_instance, "clean"):
                    field_instance.clean(field_value, model_instance)
            except ValidationError:
                self.set_validation_error(message=f"{field_value} is not valid value for {field_name}")
                return False

        ### validate permission_data

        for permission in self.permission_data:

            state_change_object = get_state_change_object(permission["permission_type"])
            if condition_model not in state_change_object.get_allowable_targets():
                message = f"Permission type {permission['permission_type']} cannot be set on {condition_model}"
                self.set_validation_error(message=message)
                return False

            if "permission_roles" not in permission and "permission_actors" not in permission:
                message = f"Must supply either roles or actors to permission {permission['permission_type']}"
                self.set_validation_error(message=message)
                return False

            for field_name, field_value in permission.get("permission_configuration", {}):
                if field_name not in [field.name for field in state_change_object.input_fields]:
                    message = f"{field_name} is not an input field for {permission['permission_type']}"
                    self.set_validation_error(message=message)
                    return False
                # TODO: check field type specified in change object's InputFields against field_value
                # (skipping replaced fields)

        return True

    def implement(self, actor, target, **kwargs):

        attr_name = "condition" if not self.leadership_type else self.leadership_type + "_condition"
        manager = getattr(target, attr_name)

        if not manager:
            from concord.conditionals.models import ConditionManager
            owner = target.get_owner()
            set_on = self.leadership_type if self.leadership_type else "permission"
            manager = ConditionManager.objects.create(owner=owner, community=owner.pk, set_on=set_on)
            setattr(target, attr_name, manager)
            target.save()

        condition_data = {"condition_type": self.condition_type, "condition_data": self.condition_data,
                          "permission_data": self.permission_data}
        manager.add_condition(condition_data, mode=self.mode)
        manager.save()

        return manager


class EditConditionStateChange(BaseStateChange):
    """State change to add condition to permission or leadership role."""

    descriptive_text = {
        "verb": "edit",
        "default_string": "condition",
        "detail_string": "condition with {element_id}"
    }

    section = "Permissions"
    allowable_targets = ["all_community_models", PermissionsItem]

    element_id = field_utils.IntegerField(label="Element ID", required=True)
    condition_data = field_utils.DictField(label="New condition data", null_value=dict)
    permission_data = field_utils.DictField(label="New permission data", null_value=list)
    leadership_type = field_utils.CharField(label="Leadership type to set condition on")

    def validate(self, actor, target):

        if not super().validate(actor=actor, target=target):
            return False

        if hasattr(target, "is_community") and target.is_community:

            if not self.leadership_type:
                self.set_validation_error(message="leadership_type cannot be None")
                return False

            if self.leadership_type not in ["owner", "governor"]:
                self.set_validation_error(message="leadership_type must be 'owner' or 'governor'")
                return False

        if self.leadership_type:
            condition_manager = getattr(target, self.leadership_type + "_condition")
        else:
            condition_manager = target.condition

        condition_element = condition_manager.get_condition_dataclass(self.element_id)

        condition_model = Client(actor="system").Conditional.get_condition_class(
            condition_type=condition_element.data["condition_type"])
        model_instance = condition_model()

        ### validate condition_data
        for field_name, field_value in self.condition_data.items():

            if type(field_value) == str and field_value[:2] == "{{":
                continue  # don't validate if it's a replaced field

            try:
                field_instance = model_instance._meta.get_field(field_name)
            except AttributeError:
                self.set_validation_error(message=f"There is no field {field_name} on condition {self.condition_type}")
                return False

            try:
                field_instance.clean(field_value, model_instance)
            except ValidationError:
                self.set_validation_error(message=f"{field_value} is not valid value for {field_name}")
                return False

        ## validate permission data
        for permission in self.permission_data:

            state_change_object = get_state_change_object(permission["permission_type"])
            if condition_model not in state_change_object.get_allowable_targets():
                message = f"Permission type {permission['permission_type']} cannot be set on {condition_model}"
                self.set_validation_error(message=message)
                return False

            if "permission_roles" not in permission and "permission_actors" not in permission:
                message = f"Must supply either roles or actors to permission {permission['permission_type']}"
                self.set_validation_error(message=message)
                return False

            for field_name, field_value in permission.get("permission_configuration", {}):
                if field_name not in [field.name for field in state_change_object.input_fields]:
                    message = f"{field_name} is not an input field for {permission['permission_type']}"
                    self.set_validation_error(message=message)
                    return False
                # TODO: check field type specified in change object's InputFields against field_value
                # (skipping replaced fields)

        return True

    def implement(self, actor, target, **kwargs):

        attr_name = "condition" if not self.leadership_type else self.leadership_type + "_condition"
        manager = getattr(target, attr_name)

        if self.condition_data:
            manager.edit_condition_by_key(self.element_id, "condition_data", self.condition_data)

        if self.permission_data:
            manager.edit_condition_by_key(self.element_id, "permission_data", self.permission_data)

        manager.save()
        return manager


class RemoveConditionStateChange(BaseStateChange):
    """State change to remove condition from Community."""

    descriptive_text = {
        "verb": "remove",
        "default_string": "condition",
        "detail_string": "condition with {element_id}"
    }

    is_foundational = True
    section = "Leadership"
    allowable_targets = ["all_community_models", PermissionsItem]

    element_id = field_utils.IntegerField(label="Element ID to remove")
    leadership_type = field_utils.CharField(label="Leadership type to remove condition from")

    def validate(self, actor, target):

        if not super().validate(actor=actor, target=target):
            return False

        if hasattr(target, "is_community") and target.is_community and not self.leadership_type:
            self.set_validation_error(message="leadership_type cannot be None")
            return False

        return True

    def implement(self, actor, target, **kwargs):

        attr_name = "condition" if not self.leadership_type else self.leadership_type + "_condition"
        manager = getattr(target, attr_name)

        if self.element_id:
            manager.remove_condition(self.element_id)
            manager.save()
            return manager
        else:
            manager.delete()


####################################
### Vote Condition State Changes ###
####################################


class AddVoteStateChange(BaseStateChange):
    """State change for adding a vote."""

    descriptive_text = {
        "verb": "vote",
        "default_string": "",
        "detail_string": "{vote}"
    }

    section = "Vote"
    allowable_targets = [VoteCondition]

    vote = field_utils.CharField(label="Vote", required=True)

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

    def implement(self, actor, target, **kwargs):
        target.add_vote(self.vote)
        target.add_vote_record(actor)
        target.save()
        return True


#######################################
### Approve Condition State Changes ###
#######################################


class ApproveStateChange(BaseStateChange):
    """State change for approving a condition."""

    descriptive_text = {
        "verb": "approve",
        "default_string": "",
        "preposition": ""
    }

    section = "Approval"
    allowable_targets = [ApprovalCondition]

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

    def implement(self, actor, target, **kwargs):
        target.approve()
        target.save()
        return True


class RejectStateChange(BaseStateChange):
    """State change for rejecting a condition.."""

    descriptive_text = {
        "verb": "reject",
        "default_string": "",
        "preposition": ""
    }

    section = "Approval"
    rejects_condition = True
    allowable_targets = [ApprovalCondition]

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

    def implement(self, actor, target, **kwargs):
        target.reject()
        target.save()
        return True


#########################################
### Consensus Condition State Changes ###
#########################################

class RespondConsensusStateChange(BaseStateChange):
    """State change for responding to a consensus condition"""

    descriptive_text = {
        "verb": "respond",
        "default_string": "",
        "detail_string": "with {response}",
        "preposition": ""
    }

    section = "Consensus"
    allowable_targets = [ConsensusCondition]

    response = field_utils.CharField(label="Response", required=True)

    def validate(self, actor, target):
        """Checks that the actor is a participant."""
        if not super().validate(actor=actor, target=target):
            return False

        if self.response not in target.response_choices:
            self.set_validation_error(
                f"Response must be one of {', '.join(target.response_choices)}, not {self.response}")
            return False

        return True

    def implement(self, actor, target, **kwargs):
        target.add_response(actor, self.response)
        target.save()
        return self.response


class ResolveConsensusStateChange(BaseStateChange):
    """State change for resolving a consensus condition."""

    descriptive_text = {
        "verb": "resolve",
        "default_string": "",
        "preposition": ""
    }

    section = "Consensus"
    allowable_targets = [ConsensusCondition]

    def validate(self, actor, target):
        """Checks that the actor is a participant."""
        if not super().validate(actor=actor, target=target):
            return False

        if not target.ready_to_resolve():
            self.set_validation_error("The minimum duration of discussion has not yet passed.")
            return False

        return True

    def implement(self, actor, target, **kwargs):
        target.resolved = True
        target.save()
        return target
