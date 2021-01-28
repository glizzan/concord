"""Clients for conditionals."""

from typing import Tuple, Any, Dict
import logging

from django.db.models import Model

from concord.actions.client import BaseClient
from concord.utils.helpers import Client
from concord.utils.lookups import get_all_conditions, get_acceptance_conditions
from concord.conditionals import state_changes as sc
from concord.conditionals import utils


logger = logging.getLogger(__name__)


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


class ConsensusConditionClient(BaseClient):
    """The target of the ConsensusConditionClient must always be a ConsensusCondition instance."""

    # Read only

    def resolveable(self) -> tuple:
        """Returns True if condition is ready to resolve, or False if not. If not, returns time until it
        will be ready to resolve."""
        if self.target.ready_to_resolve():
            return True, None
        else:
            return False, self.target.time_until_duration_passed()

    def get_current_results(self) -> Dict:
        """Gets current results of vote condition."""
        return self.target.get_responses()

    # State changes

    def respond(self, *, response: str) -> Tuple[int, Any]:
        """Add response to consensus condition."""
        change = sc.RespondConsensusStateChange(response=response)
        return self.create_and_take_action(change)

    def resolve(self) -> Tuple[int, Any]:
        """Resolve consensus condition."""
        change = sc.ResolveConsensusStateChange()
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

    def is_valid_condition_type(self, condition_type, lower=True):
        condition_models = get_all_conditions()
        for model_type in condition_models:
            if lower and model_type.__name__.lower() == condition_type.lower(): return True
            if model_type.__name__ == condition_type: return True
        return False

    def get_possible_conditions(self):
        """Get all possible conditions."""
        return get_all_conditions()

    def get_condition_class(self, *, condition_type):
        """Get condition class object given condition type."""
        for condition in get_all_conditions():
            if condition.__name__.lower() == condition_type.lower(): return condition

    def get_condition_manager(self, source, leadership_type=None) -> Model:
        """Gets the condition manager for a source."""
        if source.__class__.__name__ == "PermissionsItem": return source.condition
        if leadership_type == "owner": return source.owner_condition
        if leadership_type == "governor": return source.governor_condition

    def check_condition_status(self, *, action, manager):
        return utils.condition_status(manager=manager, action=action)

    def create_conditions_for_action(self, action, condition_managers):
        for manager in condition_managers:
            utils.create_conditions(manager=manager, action=action)

    def get_condition_items_given_action_and_source(self, *, action, source, leadership_type=None) -> Model:
        """Given the action which triggered a condition, the source and the leadership type, get the item.
        NOTE: an action should never trigger an item from both governor and owner, as owner is its own pipeline, so
        possibly you could just check both?
        """
        manager = self.get_condition_manager(source, leadership_type)
        return list(utils.get_condition_instances(action=action, manager=manager).values())

    def get_condition_items_for_action(self, *, action_pk):
        """Get all condition items set on an action."""
        all_condition_items = []
        for condition_class in get_acceptance_conditions():
            condition_items = condition_class.objects.filter(action=action_pk)
            if condition_items:
                all_condition_items = all_condition_items + list(condition_items)
        return all_condition_items

    def get_element_ids(self, leadership_type=None):
        """Given a condition mananger, get the element IDs of the contained conditions."""
        condition_manager = self.get_condition_manager(self.target, leadership_type)
        return condition_manager.get_element_ids()

    # State changes

    def add_condition(self, *, condition_type, condition_data=None, permission_data=None, leadership_type=None,
                      mode="acceptance"):
        change = sc.AddConditionStateChange(
            condition_type=condition_type, condition_data=condition_data, permission_data=permission_data,
            leadership_type=leadership_type, mode=mode)
        return self.create_and_take_action(change)

    def edit_condition(self, *, element_id, condition_data=None, permission_data=None, leadership_type=None):
        change = sc.EditConditionStateChange(
            element_id=element_id, condition_data=condition_data, permission_data=permission_data,
            leadership_type=leadership_type)
        return self.create_and_take_action(change)

    def remove_condition(self, *, leadership_type=None, element_id=None):
        change = sc.RemoveConditionStateChange(leadership_type=leadership_type, element_id=element_id)
        return self.create_and_take_action(change)
