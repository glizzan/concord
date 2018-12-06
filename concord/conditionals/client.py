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

    def get_condition_template_for_permission(self, permission_pk):
        result = ConditionTemplate.objects.filter(conditioned_object=permission_pk,
            conditioning_choices="permission")
        if result:
            return result[0]
        return None

    def get_condition_template_for_owner(self, community_pk):
        result = ConditionTemplate.objects.filter(conditioned_object=community_pk,
            conditioning_choices="community_owner")
        if result:
            return result[0]
        return None

    def get_condition_template_for_governor(self, community_pk):
        result = ConditionTemplate.objects.filter(conditioned_object=community_pk,
            conditioning_choices="community_governor")
        if result:
            return result[0]
        return None

    def get_condition_item_given_action(self, action_pk):
        # HACK
        condition_items = ApprovalCondition.objects.filter(action=action_pk)
        if not condition_items:
            condition_items = VoteCondition.objects.filter(action=action_pk)
        return condition_items[0] if condition_items else None

    def getVoteCondition(self, pk):
        vote_object = VoteCondition.objects.get(pk=pk)
        return VoteConditionClient(target=vote_object, actor=self.actor)

    # Create only
    def condition_lookup_helper(self, lookup_string):
        condition_dict = {
            "approvalcondition": ApprovalCondition,
            "votecondition": VoteCondition
        }
        return condition_dict[lookup_string]

    # FIXME: this feels like too much logic for the client, but where should it go?
    def create_condition_item(self, condition_template, action):
        """
        This method is a little wonky, because we want to include the permission that goes on 
        the condition action item *in* the template but we *don't* want to put it through the
        permissions pipeline when instantiating.
        """

        # Instantiate condition object
        data_dict = json.loads(condition_template.condition_data)
        conditionModel = self.condition_lookup_helper(condition_template.condition_type)
        condition_item = conditionModel.objects.create(action=action.pk, 
                owner=condition_template.get_owner(), owner_type=condition_template.owner_type,
                **data_dict)

        # Add permission
        if condition_template.permission_data is not None:
            permission_dict = json.loads(condition_template.permission_data)
            # HACK to prevent permission addition from going through permissions pipeline
            from permission_resources.models import PermissionsItem
            PermissionsItem.objects.create(
                permitted_object=condition_item,
                actors = json.dumps(permission_dict["permission_actor"]),
                change_type = permission_dict["permission_type"],
                owner = condition_template.get_owner(),
                owner_type = condition_template.owner_type)

        return condition_item

    def get_or_create_condition_item(self, condition_template, action):
        condition_item = self.get_condition_item_given_action(action.pk)
        if not condition_item :
            condition_item  = self.create_condition_item(condition_template, action)
        return condition_item 

    def override_owner_if_target_is_owned_by_community(self, target):
        # FIXME: don't like the way this abstraction is leaking
        if target.owner_type == "ind":
            return self.actor
        else:
            return target.owner

    def createApprovalCondition(self, action):
        owner = self.override_owner_if_target_is_owned_by_community(action.target)
        approval_object = ApprovalCondition.objects.create(owner=owner, action=action.pk)
        return ApprovalConditionClient(target=approval_object, actor=self.actor)

    def createVoteCondition(self, action, **kwargs):
        owner = self.override_owner_if_target_is_owned_by_community(action.target)
        vote_object = VoteCondition.objects.create(owner=owner, action=action.pk, **kwargs)
        return VoteConditionClient(target=vote_object, actor=self.actor)

    # Stage changes

    def addConditionToGovernors(self, condition_type, permission_data=None, target=None, condition_data=None):
        change = sc.AddConditionStateChange(condition_type, condition_data, 
            permission_data, "community_governor")
        return self.create_and_take_action(change, target)        

    def addConditionToOwners(self, condition_type, permission_data=None, target=None, condition_data=None):
        change = sc.AddConditionStateChange(condition_type, condition_data, 
            permission_data, "community_owner")
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