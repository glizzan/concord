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


class ConditionalClient(BaseClient):

    mode = "permission"

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

    def get_condition_item_for_action_and_template(self, action_pk, template_pk, condition_type):
        condition_class = self.get_condition_class(condition_type=condition_type)
        matches = condition_class.objects.filter(action=action_pk).filter(condition_template=template_pk)
        if matches:
            return matches[0] # should be only one
        return None

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

    def get_or_create_condition_item(self, *, template_pk, action_pk, condition_type):
        condition_item = self.get_condition_item_for_action_and_template(action_pk, template_pk, condition_type)
        if condition_item:
            return condition_item, False
        condition_template = self.get_condition_template(template_pk)





        get_condition_item_for_action_and_template(self, action, condition_template, condition_type)
    
    def get_or_create_condition(self, *, condition_template: ConditionTemplate, action: Action) -> Model:
        condition_item = self.get_condition_item_given_action(action_pk=action.pk)
        if not condition_item:
            condition_item  = self.create_condition_item(condition_template=condition_template, action=action)
        return condition_item 

    def create_vote_condition(self, *, action: Action, **kwargs) -> VoteConditionClient:
        vote_object = VoteCondition.objects.create(owner=action.target.get_owner(), 
            action=action.pk, **kwargs)
        return VoteConditionClient(target=vote_object, actor=self.actor)

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

    # Requires target to be set

    def get_target_type(self):
        if hasattr(self.target, "is_community") and self.target.is_community:
            return "community"
        return "permission"

    def get_condition_template(self, leadership_type=None) -> ConditionTemplate:

        if leadership_type and self.get_target_type() == "permission":
            raise AttributeError("You are trying to get a community leadership condition from a permission")

        if leadership_type == "owner":
            return self.get_condition_template_for_owner()
        if leadership_type == "governor":
            return self.get_condition_template_for_governor()

        result = self.target.condition.all()
        return result[0] if result else None
        # FIXME: should probably return empty list, but that breaks a bunch of tests, so need to refactor

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

    # State changes

    def add_condition(self, *, condition_type: str, permission_data: Dict = None, 
            condition_data: Dict = None, action_sourced_fields: Dict = None, target_type: str = None):
        if self.get_target_type() == "permission":
            change = sc.AddConditionStateChange(condition_type=condition_type, permission_data=permission_data,
                condition_data=condition_data, action_sourced_fields=action_sourced_fields, target_type=target_type)
        else:
            change = sc.AddLeaderConditionStateChange(condition_type=condition_type,
                permission_data=permission_data, condition_data=condition_data, target_type=target_type)
        return self.create_and_take_action(change)

    def change_condition(self, *, condition_pk: int, permission_data: Dict = None, 
        condition_data: Dict = None) -> Tuple[int, Any]:
        if self.get_target_type() == "permission":
            change = sc.ChangeConditionStateChange(condition_pk=condition_pk,
                permission_data=permission_data, condition_data=condition_data)
        else:
            change = sc.ChangeLeaderConditionStateChange(condition_pk=condition_pk,
                permission_data=permission_data, condition_data=condition_data)        
        return self.create_and_take_action(change)
    
    def remove_condition(self, *, condition: Model) -> Tuple[int, Any]:
        if self.get_target_type() == "permission":
            change = sc.RemoveConditionStateChange(condition_pk=condition.pk)
        else:      
            change = sc.RemoveLeaderConditionStateChange(condition_pk=condition.pk)
        return self.create_and_take_action(change)

    # FIXME: these maybe should be refactored away but for now they're used

    def add_condition_to_governors(self, *, condition_type: str, permission_data: Dict = None, 
            condition_data: Dict = None) -> Tuple[int, Any]:
            return self.add_condition(condition_type=condition_type, condition_data=condition_data,
                permission_data=permission_data, target_type="gov")

    def add_condition_to_owners(self, *, condition_type: str, permission_data: Dict = None, 
            condition_data: Dict = None) -> Tuple[int, Any]:
            return self.add_condition(condition_type=condition_type, condition_data=condition_data,
                permission_data=permission_data, target_type="own")





