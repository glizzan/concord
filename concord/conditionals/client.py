import json
from typing import Tuple, List, Any, Dict

from django.db.models import Model

from concord.actions.client import BaseClient
from concord.actions.models import Action  # Just needed for type hinting

from concord.conditionals.models import ApprovalCondition, VoteCondition, ConditionTemplate
from concord.conditionals import state_changes as sc


"""The conditionals app is one of the more confusing core apps, and the client is fairly confusing 
as well.  One day we'll refactor it to make it easier to understand but for now, if you are 
confused, *please* go read the documentation on conditionals!"""


class ApprovalConditionClient(BaseClient):
    '''
    The target of the ApprovalConditionClient must always be an ApprovalCondition instance.
    '''

    def approve(self) -> Tuple[int, Any]:
        change = sc.ApproveStateChange()
        return self.create_and_take_action(change)

    def reject(self) -> Tuple[int, Any]:
        change = sc.RejectStateChange()
        return self.create_and_take_action(change)
        

class VoteConditionClient(BaseClient):
    '''
    The target of the VoteConditionClient must always be a VoteCondition instance.
    '''

    # Read only

    def publicize_votes(self) -> bool:
        return self.target.publicize_votes

    def can_abstain(self) -> bool:
        return self.target.allow_abstain

    def get_current_results(self) -> Dict:
        return self.target.current_results()

    # State changes

    def vote(self, *, vote: str) -> Tuple[int, Any]:
        change = sc.AddVoteStateChange(vote=vote)
        return self.create_and_take_action(change)


class BaseConditionalClient(BaseClient):
    '''
    The BaseConditionClient should not be called directly, but contains methods that are common to 
    both PermissionConditionalClient and CommunityConditionalClient.

    Most of the methods on the BaseConditional are client-less, but there are a couple that do
    require targets.  For those, either the target of PermissionConditionalClient (Permission) or
    CommunityConditionalClient (Community) are allowed.
    '''

    # Target-less methods (don't require a target to be set ahead of time)

    def get_condition_item_given_action(self, *, action_pk: int) -> Model:
        # HACK
        condition_items = ApprovalCondition.objects.filter(action=action_pk)
        if not condition_items:
            condition_items = VoteCondition.objects.filter(action=action_pk)
        return condition_items[0] if condition_items else None

    def get_condition_item(self, *, condition_pk, condition_type):
        condition_class = self.get_condition_class(condition_type=condition_type)
        return condition_class.objects.get(pk=int(condition_pk))

    def get_conditions_given_targets(self, *, target_pks: list):
        return ConditionTemplate.objects.filter(permission__in=target_pks)

    def get_vote_condition_as_client(self, *, pk: int) -> VoteConditionClient:
        vote_object = VoteCondition.objects.get(pk=pk)
        return VoteConditionClient(target=vote_object, actor=self.actor)

    def get_approval_condition_as_client(self, *, pk: int) -> ApprovalConditionClient:
        approval_object = ApprovalCondition.objects.get(pk=pk)
        return ApprovalConditionClient(target=approval_object, actor=self.actor)

    def condition_lookup_helper(self, *, lookup_string: str) -> Model:
        return ConditionTemplate().get_condition_type_class(lookup_string=lookup_string)

    def get_condition_class(self, *, condition_type):
        for condition in self.get_possible_conditions():
            if condition.__name__.lower() == condition_type.lower():
                return condition

    def get_possible_conditions(self, *, formatted_as="objects"):
        
        # FIXME: need to get this from a list of actual objects
        conditions = [ApprovalCondition, VoteCondition]

        if formatted_as == "objects":
            return conditions
        if formatted_as == "string":
            return [cond.__name__.lower() for cond in conditions]
        if formatted_as == "shortstring":
            return [cond.__name__.lower().split("condition")[0] for cond in conditions]

    def create_condition_item(self, *, condition_template: ConditionTemplate, action: Action) -> Model:
        return condition_template.condition_data.create_condition_and_permissions(
                action=action, owner=condition_template.get_owner())

    def get_or_create_condition(self, *, condition_template: ConditionTemplate, action: Action) -> Model:
        condition_item = self.get_condition_item_given_action(action_pk=action.pk)
        if not condition_item:
            condition_item  = self.create_condition_item(condition_template=condition_template, action=action)
        return condition_item 

    def create_vote_condition(self, *, action: Action, **kwargs) -> VoteConditionClient:
        vote_object = VoteCondition.objects.create(owner=action.target.get_owner(), 
            action=action.pk, **kwargs)
        return VoteConditionClient(target=vote_object, actor=self.actor)

    # Requires target to be set

    def get_condition_template(self) -> ConditionTemplate:
        result = self.target.condition.all()
        # result = ConditionTemplate.objects.filter(conditioned_object=self.target)
        if result:
            return result[0]
        return
        # FIXME: should probably return empty list, but that breaks a bunch of tests, so need to refactor


class PermissionConditionalClient(BaseConditionalClient):
    '''
    Target is always a Permission.
    '''

    # Stage changes

    # FIXME: It would be nice to be able to pass in the ConditionTemplate, and/or to be able to pass in
    # condition kwargs directly
    def add_condition(self, *, condition_type: str, permission_data: Dict = None, 
            condition_data: Dict = None, action_sourced_fields: Dict = None, target_type: str = None):
        change = sc.AddConditionStateChange(condition_type=condition_type, permission_data=permission_data,
            condition_data=condition_data, action_sourced_fields=action_sourced_fields, target_type=target_type)
        return self.create_and_take_action(change)

    def change_condition(self, *, condition_pk: int, permission_data: Dict = None, 
        condition_data: Dict = None) -> Tuple[int, Any]:
        # FIXME: this unnecessarily requires target (a permission) to be set 
        change = sc.ChangeConditionStateChange(condition_pk=condition_pk,
            permission_data=permission_data, condition_data=condition_data)
        return self.create_and_take_action(change)

    def remove_condition(self, *, condition: Model) -> Tuple[int, Any]:
        change = sc.RemoveConditionStateChange(condition_pk=condition.pk)
        return self.create_and_take_action(change)


class CommunityConditionalClient(BaseConditionalClient):
    '''
    Target is always a Community.  Specifically, a conditional may be set on the Governors role, 
    the Owners role, or both, to place limits on their decision-making authority.
    '''

    # Target-less methods (don't require a target to be set ahead of time)

    # Read methods which require target to be set

    def instantiate_condition(self, condition_template):
        """Helper method, does not save condition instance."""
        data_dict = json.loads(condition_template.condition_data)
        conditionModel = self.condition_lookup_helper(lookup_string=condition_template.condition_type)
        temp_condition = conditionModel(owner=condition_template.get_owner(), **data_dict)
        return temp_condition

    def get_condition_info(self, condition_template):
        temp_condition = self.instantiate_condition(condition_template)
        display_string = temp_condition.description_for_passing_condition()
        if condition_template.permission_data:
            display_string += str(condition_template.permission_data)
        return display_string

    def get_condition_template_for_owner(self) -> ConditionTemplate:
        for condition in self.target.condition.all():
            if condition.condition_data.target_type == "own":
                return condition
        return None

    def get_condition_info_for_owner(self):

        condition_template = self.get_condition_template_for_owner()
        if condition_template:
            return self.get_condition_info(condition_template)

    def get_condition_template_for_governor(self) -> ConditionTemplate:
        for condition in self.target.condition.all():
            if condition.condition_data.target_type == "gov":
                return condition
        return None

    def get_condition_info_for_governor(self):
        condition_template = self.get_condition_template_for_governor()
        if condition_template:
            return self.get_condition_info(condition_template)

    # State Changes

    def add_condition(self, *, condition_type: str, target_type: str, permission_data: Dict = None, 
            condition_data: Dict = None):
        change = sc.AddLeaderConditionStateChange(condition_type=condition_type,
            permission_data=permission_data, condition_data=condition_data, target_type=target_type)
        return self.create_and_take_action(change)

    def change_condition(self, *, condition_pk: int, permission_data: Dict = None, 
        condition_data: Dict = None) -> Tuple[int, Any]:
        # FIXME: this unnecessarily requires target (a permission) to be set 
        change = sc.ChangeLeaderConditionStateChange(condition_pk=condition_pk,
            permission_data=permission_data, condition_data=condition_data)
        return self.create_and_take_action(change)

    def remove_condition(self, *, condition: Model) -> Tuple[int, Any]:
        change = sc.RemoveLeaderConditionStateChange(condition_pk=condition.pk)
        return self.create_and_take_action(change)

    def add_condition_to_governors(self, *, condition_type: str, permission_data: Dict = None, 
            condition_data: Dict = None) -> Tuple[int, Any]:
            return self.add_condition(condition_type=condition_type, condition_data=condition_data,
                permission_data=permission_data, target_type="gov")

    def add_condition_to_owners(self, *, condition_type: str, permission_data: Dict = None, 
            condition_data: Dict = None) -> Tuple[int, Any]:
            return self.add_condition(condition_type=condition_type, condition_data=condition_data,
                permission_data=permission_data, target_type="own")





