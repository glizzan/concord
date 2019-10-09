import json
from typing import Tuple, List, Any, Dict

from django.db.models import Model

from concord.actions.client import BaseClient
from concord.actions.models import Action  # Just needed for type hinting

from concord.conditionals.models import ApprovalCondition, VoteCondition, ConditionTemplate
from concord.conditionals import state_changes as sc

'''
The conditionals app is one of the more confusing core apps, and the client is fairly confusing 
as well.  One day we'll refactor it to make it easier to understand.

For now, it's important to distinguish between *condition templates* and *conditions*.  A condition 
template keeps track of how to set conditions on actions in various contexts.  A condition template is
theoretical: it says, "if someone does X, they'll need to pass condition Y".  A condition is practical:
it says, "someone did X, and this is the status of Y".  

For any "Condition" client, the target is the corresponding condition.  So, for example, the target
of an ApprovalConditionClient must be an ApprovalCondition instance.  Note that the condition is 
always linked to a specific action, but the action is not the target of the client.  You may start off
only knowing the identity of the action, in which case you'll need to do some extra work to get the 
corresponding condition.

For any "Condition Template" client, the target is a conditional template.  Generally speaking,
we use two kinds of condition templates.  One kind is set on individual permissions, and one kind is
set on the Owner and Governor roles in communities.  The process for generating conditions from
these two types of condition templates is practically the same.  There are a number of steps that
circumvent the typical permissions process. The following steps do NOT go through the permissions 
pipelines themselves because they are considered approved through the process by which the 
condition template was originally set: 
1) creating the condition
2) setting a permission on the condition
'''


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

    def getVoteConditionAsClient(self, *, pk: int) -> VoteConditionClient:
        vote_object = VoteCondition.objects.get(pk=pk)
        return VoteConditionClient(target=vote_object, actor=self.actor)

    def getApprovalConditionAsClient(self, *, pk: int) -> ApprovalConditionClient:
        approval_object = ApprovalCondition.objects.get(pk=pk)
        return ApprovalConditionClient(target=approval_object, actor=self.actor)

    def condition_lookup_helper(self, *, lookup_string: str) -> Model:
        condition_dict = {
            "approvalcondition": ApprovalCondition,
            "votecondition": VoteCondition
        }
        return condition_dict[lookup_string]

    def get_possible_conditions(self, *, formatted_as="objects"):
        
        # FIXME: need to get this from a list of actual objects
        conditions = [ApprovalCondition, VoteCondition]

        if formatted_as == "objects":
            return conditions
        if formatted_as == "string":
            return [cond.__name__.lower() for cond in conditions]
        if formatted_as == "shortstring":
            return [cond.__name__.lower().split("condition")[0] for cond in conditions]

    # FIXME: this feels like too much logic for the client, but where else could it go?
    def create_condition_item(self, *, condition_template: ConditionTemplate, action: Action) -> Model:

        # Instantiate condition object
        data_dict = json.loads(condition_template.condition_data)
        conditionModel = self.condition_lookup_helper(lookup_string=condition_template.condition_type)
        condition_item = conditionModel.objects.create(action=action.pk, 
                owner=condition_template.get_owner(), owner_type=condition_template.owner_type,
                **data_dict)

        # Add permission
        if condition_template.permission_data is not None:
            permission_dict = json.loads(condition_template.permission_data)
            from concord.permission_resources.utils import create_permission_outside_pipeline
            # TODO: check if this is still needed once custom permission+condition field created
            create_permission_outside_pipeline(permission_dict, condition_item, condition_template)

        return condition_item

    def get_or_create_condition(self, *, condition_template: ConditionTemplate, action: Action) -> Model:
        condition_item = self.get_condition_item_given_action(action_pk=action.pk)
        if not condition_item :
            condition_item  = self.create_condition_item(condition_template=condition_template, 
                action=action)
        return condition_item 

    def override_owner_if_target_is_owned_by_community(self, *, action_target: Model) -> str:
        # FIXME: don't like the way this abstraction is leaking.  honestly I don't even remember
        # why this is here which is always a bad sign.
        return self.actor if action_target.owner_type == "ind" else action_target.owner

    def createVoteCondition(self, *, action: Action, **kwargs) -> VoteConditionClient:
        owner = self.override_owner_if_target_is_owned_by_community(action_target=action.target)
        vote_object = VoteCondition.objects.create(owner=owner, action=action.pk, **kwargs)
        return VoteConditionClient(target=vote_object, actor=self.actor)

    # Read methods which require target to be set

    # Stage changes

    def removeCondition(self, *, condition: Model) -> Tuple[int, Any]:
        change = sc.RemoveConditionStateChange(condition_pk=condition.pk)
        return self.create_and_take_action(change)


class PermissionConditionalClient(BaseConditionalClient):
    '''
    Target is always a Permission.
    '''

    # Target-less methods (don't require a target to be set ahead of time)

    # Read methods which require target to be set

    def get_condition_template(self) -> ConditionTemplate:
        result = ConditionTemplate.objects.filter(conditioned_object=self.target.pk,
            conditioning_choices="permission")
        if result:
            return result[0]
        return
        # FIXME: should probably return empty list, but that breaks a bunch of tests, so need to refactor

    # State changes

    # FIXME: should be add_condition not addCondition
    def addCondition(self, *, condition_type: str, permission_data: Dict = None, 
            condition_data: Dict = None) -> Tuple[int, Any]:
        # TODO: It would be nice to be able to pass in the ConditionTemplate 
        change = sc.AddConditionStateChange(condition_type=condition_type,
            permission_data=permission_data, condition_data=condition_data, 
            conditioning_choices="permission")
        return self.create_and_take_action(change)

    def change_condition(self, *, condition_pk: int, permission_data: Dict = None, 
        condition_data: Dict = None) -> Tuple[int, Any]:
        change = sc.ChangeConditionStateChange(condition_pk=condition_pk,
            permission_data=permission_data, condition_data=condition_data)
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
        temp_condition = conditionModel(owner=condition_template.get_owner(), owner_type=condition_template.owner_type,
            **data_dict)
        return temp_condition

    def get_condition_info(self, condition_template):
        temp_condition = self.instantiate_condition(condition_template)
        display_string = temp_condition.description_for_passing_condition()
        if condition_template.permission_data:
            display_string += str(condition_template.permission_data)
        return display_string

    def get_condition_template_for_owner(self) -> ConditionTemplate:
        result = ConditionTemplate.objects.filter(conditioned_object=self.target.pk,
            conditioning_choices="community_owner")
        return result[0] if result else None

    def get_condition_info_for_owner(self):
        condition_template = self.get_condition_template_for_owner()
        if condition_template:
            return self.get_condition_info(condition_template)

    def get_condition_template_for_governor(self) -> ConditionTemplate:
        result = ConditionTemplate.objects.filter(conditioned_object=self.target.pk,
            conditioning_choices="community_governor")
        return result[0] if result else None

    def get_condition_info_for_governor(self):
        condition_template = self.get_condition_template_for_governor()
        if condition_template:
            return self.get_condition_info(condition_template)

    # State Changes

    def addConditionToGovernors(self, *, condition_type: str, permission_data: Dict = None, 
            condition_data: Dict = None) -> Tuple[int, Any]:
        change = sc.AddConditionStateChange(condition_type=condition_type,
            permission_data=permission_data, condition_data=condition_data, 
            conditioning_choices="community_governor")
        return self.create_and_take_action(change)        

    def addConditionToOwners(self, *, condition_type: str, permission_data: Dict = None, 
            condition_data: Dict = None) -> Tuple[int, Any]:
        change = sc.AddConditionStateChange(condition_type=condition_type,
            permission_data=permission_data, condition_data=condition_data, 
            conditioning_choices="community_owner")
        return self.create_and_take_action(change) 





