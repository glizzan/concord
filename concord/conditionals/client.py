"""Clients for conditionals."""

from typing import Tuple, Any, Dict

from django.db.models import Model

from concord.actions.client import BaseClient
from concord.actions.utils import Client, get_all_conditions
from concord.conditionals import state_changes as sc


class ApprovalConditionClient(BaseClient):
    """The target of the ApprovalConditionClient must always be an ApprovalCondition instance."""

    def approve(self) -> Tuple[int, Any]:
        """Approve the target condition."""
        change = sc.ApproveStateChange()
        return self.create_and_take_action(change)

    def reject(self) -> Tuple[int, Any]:
        """Reject the taret condition."""
        change = sc.RejectStateChange()
        return self.create_and_take_action(change)


class VoteConditionClient(BaseClient):
    """The target of the VoteConditionClient must always be a VoteCondition instance."""

    # Read only

    def publicize_votes(self) -> bool:
        """Returns True if condition is set to publicize votes, otherwise False."""
        return self.target.publicize_votes

    def can_abstain(self) -> bool:
        """Returns True if users can abstain, otherwise False."""
        return self.target.allow_abstain

    def get_current_results(self) -> Dict:
        """Gets current results of vote condition."""
        return self.target.current_results()

    # State changes

    def vote(self, *, vote: str) -> Tuple[int, Any]:
        """Add vote to condition."""
        change = sc.AddVoteStateChange(vote=vote)
        return self.create_and_take_action(change)


class ConditionalClient(BaseClient):
    """ConditionalClient is largely used as an easy way to access all the specific conditionclients at once, but
    can also has some helper methods and one state change - add_condition_to_action."""

    # Target-less methods (don't require a target to be set ahead of time)

    def get_condition_item(self, *, condition_pk, condition_type):
        """Get condition item given pk and type."""
        condition_class = self.get_condition_class(condition_type=condition_type)
        return condition_class.objects.get(pk=int(condition_pk))

    def get_condition_as_client(self, *, condition_type: str, pk: int) -> BaseClient:
        """Given a condition type and pk, gets that condition object and returns it wrapped in a client.
        Note: condition type MUST be capitalized to match the client name."""
        client = getattr(Client(actor=self.actor), condition_type, None)
        if not client:
            raise ValueError(f"No client '{condition_type}', must be one of: {', '.join(Client().client_names)}")
        client.set_target(target=self.get_condition_item(condition_pk=pk, condition_type=condition_type.lower()))
        return client

    def get_possible_conditions(self):
        """Get all possible conditions."""
        return get_all_conditions()

    def get_condition_class(self, *, condition_type):
        """Get condition class object given condition type."""
        for condition in self.get_possible_conditions():
            if condition.__name__.lower() == condition_type.lower():
                return condition

    def get_condition_item_given_action_and_source(self, *, action_pk: int, source_id: str) -> Model:
        """Given the action_pk and source_id corresponding to a condition item, get that item."""
        for condition_class in self.get_possible_conditions():
            condition_items = condition_class.objects.filter(action=action_pk, source_id=source_id)
            if condition_items:
                return condition_items[0]
        return None

    def get_condition_items_for_action(self, *, action_pk):
        """Get all condition items set on an action."""
        all_condition_items = []
        for condition_class in self.get_possible_conditions():
            condition_items = condition_class.objects.filter(action=action_pk)
            if condition_items:
                all_condition_items = all_condition_items + list(condition_items)
        return all_condition_items

    def get_condition_item_on_permission(self, *, action_pk: int, permission_pk: int):
        """Get condition item corresponding to a specific action and permission."""
        source_id = "perm_" + str(permission_pk)
        return self.get_condition_item_given_action_and_source(action_pk=action_pk, source_id=source_id)

    def get_condition_item_on_community(self, *, action_pk: int, community_pk: int, leadership_type: str):
        """Get condition item on an action given the community & leadership type that triggered it."""
        source_id = leadership_type + "_" + str(community_pk)
        return self.get_condition_item_given_action_and_source(action_pk=action_pk, source_id=source_id)

    def get_or_create_condition_on_permission(self, action, permission):
        """Given an action and permission, if a condition item exists get it, otherwise create it."""
        condition_item = self.get_condition_item_on_permission(action_pk=action.pk, permission_pk=permission.pk)
        if not condition_item:
            condition, container = self.trigger_condition_creation(action=action, permission=permission)
            if container.summary_status == "committed":    # should always be the case with system???
                condition_item = self.get_condition_item_on_permission(
                    action_pk=action.pk, permission_pk=permission.pk)
            else:
                print("Warning: container generated by get_or_create_condition_on_permission did not commit.")
        return condition_item

    def get_or_create_condition_on_community(self, action, community, leadership_type):
        """Given an action and community & leadership type, if a condition item exists get it, otherwise create it."""
        condition_item = self.get_condition_item_on_community(action_pk=action.pk, community_pk=community.pk,
                                                              leadership_type=leadership_type)
        if not condition_item:
            condition_item, container = self.trigger_condition_creation(
                action=action, community=community, leadership_type=leadership_type)
            if container.summary_status != "committed":
                print("Warning: container generated by get_or_create_condition_on_community did not commit.")
        return condition_item

    def trigger_condition_creation(self, *, action, permission=None, community=None, leadership_type=None):
        """Create a condition given action and corresponding info about what triggered it."""
        if community and leadership_type:
            if leadership_type == "owner":
                container, log = community.owner_condition.apply_template(trigger_action=action)
            elif leadership_type == "governor":
                container, log = community.governor_condition.apply_template(trigger_action=action)
            else:
                raise ValueError("Leadership type supplied to trigger_condition_creation must be owner or governor")
        elif permission:
            container, log = permission.condition.apply_template(trigger_action=action)
        else:
            raise ValueError("Must supply permission or community & leadership type to trigger_condition_creation")
        # We know that a condition template has a condition as the result of the first action, so we can find it
        # and return it here
        condition = container.context.get_result(position=0)
        return condition, container

    def trigger_condition_creation_from_source_id(self, *, action, source_id):
        """Trigger condition creation given an action and the source_id that triggered it."""

        source, pk = source_id.split("_")

        if source == "perm":
            permission = Client().PermissionResource.get_permission(pk=int(pk))
            return self.trigger_condition_creation(action=action, permission=permission)
        else:
            community = Client().Community.get_community(community_pk=pk)
            return self.trigger_condition_creation(action=action, community=community, leadership_type=source)

    # State changes

    def set_condition_on_action(self, condition_type, condition_data=None, permission_pk=None,
                                community_pk=None, leadership_type=None):
        """This is almost always created as a mock to be used in a condition TemplateField. Typically when
        creating the mock we want to supply condition_type and condition_data but leave the rest to be
        supplied later. When the action is actually run, the target should *always* be an action!"""
        change = sc.SetConditionOnActionStateChange(
            condition_type=condition_type, condition_data=condition_data, permission_pk=permission_pk,
            community_pk=community_pk, leadership_type=leadership_type)
        return self.create_and_take_action(change)
