import json

from actions.clients import BaseActionClient

from conditionals.models import ApprovalCondition, VoteCondition, ConditionTemplate
from conditionals import state_changes as sc


class ConditionTemplateClient(BaseActionClient):
    """
    This is a helper client to make it easier to generate conditions to add to 
    permissions.
    """

    def __init__(self, *args, **kwargs):
        pass

class ApprovalConditionClient(BaseActionClient):

    def approve(self, target=None):
        change = sc.ApproveStateChange()
        return self.create_and_take_action(change, target)


class VoteConditionClient(BaseActionClient):

    # Read only

    def publicize_votes(self):
        return self.target.publicize_votes

    def can_abstain(self):
        return self.target.allow_abstain

    def get_current_results(self):
        return self.target.current_results()

    # State changes

    def vote(self, vote, target=None):
        change = sc.AddVoteStateChange(vote=vote)
        return self.create_and_take_action(change, target)


class ConditionalClient(BaseActionClient):

    # Read only

    def get_condition_item_given_action(self, action_pk):
        # HACK
        condition_items = ApprovalCondition.objects.filter(action=action_pk)
        if not condition_items:
            condition_items = VoteCondition.objects.filter(action=action_pk)
        return condition_items[0] if condition_items else None

    def get_condition_template_given_permission(self, permission_pk):
        result = ConditionTemplate.objects.filter(conditioned_object=permission_pk,
            conditioned_object_type="permission")
        if result:
            return result[0]
        return None

    def get_condition_template_given_community(self, community_pk):
        result = ConditionTemplate.objects.filter(conditioned_object=community_pk,
            conditioned_object_type="community")
        if result:
            return result[0]
        return None

    def getVoteCondition(self, pk):
        vote_object = VoteCondition.objects.get(pk=pk)
        return VoteConditionClient(target=vote_object, actor=self.actor)

    # Create only

    # TODO: Does this logic really belong here?  Shouldn't a client just be a pointer
    # to business logic implemented elsewhere?  But the logic here is state change logic.
    # IMPORTANT: note that the permission referenced here is the permission controlling
    # changes to the conditional, not the permission the conditional is being set on.

    def set_permission_on_condition_item(self, condition_item, action, condition_template):
        if condition_template.permission_data is not None:
            from permission_resources.client import PermissionResourceClient
            # HACK! wow this needs to be cleaned up
            prc = PermissionResourceClient(actor=condition_template.get_owner())
            pr = prc.create_permission_resource(permitted_object=condition_item)
            prc.set_target(target=pr)
            permission_dict = json.loads(condition_template.permission_data)
            action_pk, permission = prc.add_permission(
                permission_type=permission_dict["permission_type"],
                permission_actor=permission_dict["permission_actor"])

    def create_condition_item(self, condition_template, action):
        data_dict = json.loads(condition_template.condition_data)
        if condition_template.condition_type == "approvalcondition":
            condition_item = ApprovalCondition.objects.create(action=action.pk, 
                owner=condition_template.get_owner(), **data_dict)
            self.set_permission_on_condition_item(condition_item, 
                action, condition_template)
        elif condition_template.condition_type == "votecondition":
            condition_item = VoteCondition.objects.create(action=action.pk, 
                owner=condition_template.get_owner(), **data_dict)
            self.set_permission_on_condition_item(condition_item, action, condition_template)
        return condition_item

    def get_or_create_condition_item(self, condition_template, action):
        condition_item = self.get_condition_item_given_action(action.pk)
        if not condition_item :
            condition_item  = self.create_condition_item(condition_template, action)
        return condition_item 

    def createApprovalCondition(self, action):
        return ApprovalCondition.objects.create(owner=self.actor, action=action)

    def createVoteCondition(self, action, **kwargs):
        vote_object = VoteCondition.objects.create(owner=self.actor, action=action,
            **kwargs)
        return VoteConditionClient(target=vote_object, actor=self.actor)

    # Stage changes

    def addConditionToGovernors(self, condition_type, permission_data=None, target=None, condition_data=None):
        change = sc.AddConditionStateChange(condition_type, condition_data, 
            permission_data, "community")
        return self.create_and_take_action(change, target)        

    # Note that the permission is the target here
    def addConditionToPermission(self, condition_type, permission_data=None, target=None, condition_data=None):
        # It would be nice to be able to pass in the ConditionTemplate 
        change = sc.AddConditionStateChange(condition_type, condition_data, 
            permission_data, "permission")
        return self.create_and_take_action(change, target)

    def removeCondition(self, condition, target=None):
        # NOTE: the target is the permission the condition is being removed from
        change = sc.RemoveConditionStateChange(condition_pk=condition.pk)
        return self.create_and_take_action(change, target)

    def copyConditionToPermission(self, condition, permission):
        ...