import json
from decimal import Decimal
import time
from collections import namedtuple
from unittest import skip
from datetime import timedelta
import inspect

from django.utils import timezone
from django.test import TestCase
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from concord.actions.models import Action, TemplateModel
from concord.utils.helpers import Changes, Client, get_all_state_changes
from concord.permission_resources.models import PermissionsItem
from concord.conditionals.models import ApprovalCondition, ConsensusCondition
from concord.conditionals.state_changes import AddConditionStateChange
from concord.utils.text_utils import condition_to_text


class DataTestCase(TestCase):

    @classmethod
    def setUpTestData(self):

        # Create a single set of users for all tests

        class Users(object):
            pass

        self.users = Users()

        # let's go woso
        self.users.pinoe = User.objects.create(username="meganrapinoe")
        self.users.rose = User.objects.create(username="roselavelle")
        self.users.tobin = User.objects.create(username="tobinheath")
        self.users.christen = User.objects.create(username="christenpress")
        self.users.crystal = User.objects.create(username="crystaldunn")
        self.users.jmac = User.objects.create(username="jessicamacdonald")
        self.users.sonny = User.objects.create(username="emilysonnett")
        self.users.jj = User.objects.create(username="julieertz")
        self.users.sully = User.objects.create(username="andisullivan")
        self.users.aubrey = User.objects.create(username="aubreybledsoe")
        self.users.lindsey = User.objects.create(username="lindseyhoran")
        self.users.midge = User.objects.create(username="midgepurce")

    def display_last_actions(self, number=10):
        """Helper method which shows the last N actions to be created, useful for debugging."""
        actions = Action.objects.all().order_by('-id')[:number]
        for action in reversed(actions):
            print(action)

    list_resource_params = {
        "name": "Go USWNT!",
        "configuration": {"player name": {"required": True}, "team": {"required": False}},
        "description": "Our favorite players"
    }


class PermissionResourceModelTests(DataTestCase):

    def setUp(self):
        self.client = Client(actor=self.users.pinoe)
        self.instance = self.client.Community.create_community(name="USWNT")
        self.client.update_target_on_all(target=self.instance)

    def test_add_permission_to_community(self):
        """
        Test addition of permisssion to community.
        """
        action, permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Communities.ChangeName, actors=[self.users.pinoe.pk])
        items = self.client.PermissionResource.get_permissions_on_object(target_object=self.instance)
        self.assertEquals(items.last().get_name(), 'Permission 4 (ChangeNameStateChange on USWNT)')

    def test_remove_permission_from_community(self):
        """
        Test removal of permission from community.
        """
        # We start out with 3 (default) permissions and add one
        items = self.client.PermissionResource.get_permissions_on_object(target_object=self.instance)
        self.assertEquals(len(items), 3)
        action, permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Communities.ChangeName, actors=[self.users.pinoe.pk])
        items = self.client.PermissionResource.get_permissions_on_object(target_object=self.instance)
        self.assertEquals(items.last().get_name(), 'Permission 4 (ChangeNameStateChange on USWNT)')

        # Now we remove it
        self.client.PermissionResource.set_target(permission)
        self.client.PermissionResource.remove_permission()
        items = self.client.PermissionResource.get_permissions_on_object(target_object=self.instance)
        self.assertEquals(len(items), 3)


class PermissionSystemTest(DataTestCase):
    """
    This set of tests looks at the basic functioning of the permissions system including
    permissions set on permissions.
    """

    def setUp(self):
        self.client = Client(actor=self.users.pinoe)
        self.instance = self.client.Community.create_community(name="USWNT")
        self.client.update_target_on_all(target=self.instance)
        self.client.Community.add_members_to_community(member_pk_list=[self.users.rose.pk])

    def test_granting_permission_to_non_governor(self):
        """
        Add a specific permission for a non-owner actor.
        """
        action, permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Communities.ChangeName, actors=[self.users.rose.pk])

        # Now the non-owner actor (Rose) takes the permitted action on the resource
        self.client.update_actor_on_all(actor=self.users.rose)
        action, item = self.client.Community.change_name_of_community(name="Test New")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(self.instance.name, "Test New")

    def test_recursive_permission(self):
        """
        Tests setting permissions on permission.
        """

        # Pinoe creates a community and adds a first level permission for Rose and a second level
        # permission for Tobin
        action, permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Communities.ChangeName, actors=[self.users.rose.pk])
        self.client.PermissionResource.set_target(target=permission)
        action, permission = self.client.PermissionResource.add_permission(
             change_type=Changes().Permissions.AddPermission, actors=[self.users.tobin.pk])

        # Tobin can't take the first level permission
        self.client.update_actor_on_all(actor=self.users.tobin)
        self.client.update_target_on_all(target=self.instance)
        action, item = self.client.Community.change_name_of_community(name="Tobin's Community")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.instance.name, "USWNT")

        # But she can take the second
        self.client.PermissionResource.set_target(target=permission)
        action, permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Permissions.AddPermission, actors=[self.users.rose.pk])
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

    def test_multiple_specific_permission(self):
        """Tests that when multiple permissions are set, they're handled in an OR fashion."""

        # Pinoe creates two different permissions - same change type, different actors
        action, permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Communities.ChangeName, actors=[self.users.christen.pk])
        action, permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Communities.ChangeName, actors=[self.users.tobin.pk])

        # Both of the actors specified can do the thing.
        self.client.update_actor_on_all(actor=self.users.christen)
        action, item = self.client.Community.change_name_of_community(name="Christen's Community")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(self.instance.name, "Christen's Community")

        self.client.update_actor_on_all(actor=self.users.tobin)
        action, item = self.client.Community.change_name_of_community(name="Tobin's Community")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(self.instance.name, "Tobin's Community")

    def test_multiple_specific_permission_with_conditions(self):
        """test multiple specific permissions with conditionals"""

        # Pinoe creates two different permissions - same change type, different actors
        action, permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Communities.ChangeName, actors=[self.users.christen.pk])
        action, permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Communities.ChangeName, actors=[self.users.tobin.pk])

        # Then she adds a condition to the second one
        self.client.Conditional.set_target(permission)
        permission_data = [
            { "permission_type": Changes().Conditionals.Approve,
              "permission_actors": [self.users.pinoe.pk]}
        ]
        action, condition = self.client.Conditional.add_condition(
            condition_type="approvalcondition", permission_data=permission_data)

        # The first (Christen) is accepted while the second (Tobin) has to wait
        self.client.update_actor_on_all(actor=self.users.christen)
        action, item = self.client.Community.change_name_of_community(name="Christen's Community")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(self.instance.name, "Christen's Community")

        self.client.update_actor_on_all(actor=self.users.tobin)
        action, item = self.client.Community.change_name_of_community(name="Tobin's Community")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "waiting")
        self.assertEquals(self.instance.name, "Christen's Community")

    def test_inverse_permission(self):
        """Tests that when inverse toggle is flipped, permissions match appropriately."""

        # Pinoe creates a permission
        action, permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Communities.ChangeName, actors=[self.users.midge.pk])

        # Midge can use the permission
        self.client.update_actor_on_all(actor=self.users.midge)
        action, item = self.client.Community.change_name_of_community(name="Midge's Community")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(self.instance.name, "Midge's Community")

        # Pinoe toggles the permission
        self.client.update_actor_on_all(actor=self.users.pinoe)
        self.client.PermissionResource.set_target(permission)
        action, result = self.client.PermissionResource.toggle_inverse_field_on_permission(change_to=True)
        permission.refresh_from_db()
        self.assertEquals(permission.inverse, True)

        # Midge can no longer use the permission
        self.client.update_actor_on_all(actor=self.users.midge)
        action, item = self.client.Community.change_name_of_community(name="Midge O'Clock")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.instance.name, "Midge's Community")

        # but anyone who is not Midge can
        self.client.update_actor_on_all(actor=self.users.tobin)
        action, item = self.client.Community.change_name_of_community(name="Tobin's Community")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(self.instance.name, "Tobin's Community")

    def test_nested_object_permission_no_conditions(self):

        # Pinoe adds a list to the group
        action, new_list = self.client.List.add_list(**self.list_resource_params)

        # Tobin doesn't have permission to do anything to the list
        self.client.update_actor_on_all(actor=self.users.tobin)
        self.client.update_target_on_all(target=new_list)
        action, result = self.client.List.add_row_to_list(row_content={"player name": "Sam Staab"})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")

        # Pinoe sets a permission on the group that does let Tobin do it, now it works
        self.client.update_actor_on_all(actor=self.users.pinoe)
        self.client.PermissionResource.set_target(target=self.instance)
        action, permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Resources.AddRow,
            actors=[self.users.tobin.pk])

        self.client.update_actor_on_all(actor=self.users.tobin)
        self.client.update_target_on_all(target=new_list)
        action, result = self.client.List.add_row_to_list(row_content={"player name": "Sam Staab"})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

    def test_nested_object_permission_with_conditions(self):

        # Pinoe adds a list to the group & sets permissions for Tobin on both the list & group
        action, new_list = self.client.List.add_list(**self.list_resource_params)
        action, permission_1 = self.client.PermissionResource.add_permission(
            change_type=Changes().Resources.AddRow, actors=[self.users.tobin.pk])
        self.client.update_target_on_all(target=new_list)
        action, permission_2 = self.client.PermissionResource.add_permission(
            change_type=Changes().Resources.AddRow, actors=[self.users.tobin.pk])

        # She adds a condition on the permission set on the list
        self.client.update_target_on_all(target=permission_2)
        permission_data = [{ "permission_type": Changes().Conditionals.Approve, "permission_actors": [self.users.crystal.pk]}]
        action, result = self.client.Conditional.add_condition(
            condition_type="approvalcondition", permission_data=permission_data)

        # Tobin adds a row and it works without setting off the conditional
        self.client.update_actor_on_all(actor=self.users.tobin)
        self.client.update_target_on_all(target=new_list)
        action, result = self.client.List.add_row_to_list(row_content={"player name": "Sam Staab"})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

        # Once Pinoe sets a condition on the group too, there's no non-conditioned permission Tobin has
        self.client.update_target_on_all(target=permission_1)
        self.client.update_actor_on_all(actor=self.users.pinoe)
        permission_data = [{ "permission_type": Changes().Conditionals.Approve, "permission_actors": [self.users.crystal.pk]}]
        action, result = self.client.Conditional.add_condition(
            condition_type="approvalcondition", permission_data=permission_data)

        # Tobin's next attempt triggers a condition
        self.client.update_actor_on_all(actor=self.users.tobin)
        self.client.update_target_on_all(target=new_list)
        action, result = self.client.List.add_row_to_list(row_content={"player name": "Lindsey Horan"})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "waiting")

    def test_anyone_permission_toggle(self):

        # Create a group with members, give members permission to change the group name
        self.instance = self.client.Community.create_community(name="USWNT")
        self.client.Community.set_target(self.instance)
        self.client.Community.add_members_to_community(member_pk_list=[self.users.rose.pk, self.users.crystal.pk,
            self.users.tobin.pk])
        self.client.PermissionResource.set_target(self.instance)
        action, result = self.client.PermissionResource.add_permission(change_type=Changes().Communities.ChangeName,
            roles=['members'])
        self.target_permission = result

        # Test someone in the group can do the thing
        self.roseClient = Client(actor=self.users.rose, target=self.instance)
        action, result = self.roseClient.Community.change_name_of_community(name="USWNT!!!!")
        self.assertEquals(action.status, "implemented")
        self.assertEquals(self.instance.name, "USWNT!!!!")

        # Test that another user, Sonny, who is not in the group, can't do the thing
        self.sonnyClient = Client(actor=self.users.sonny, target=self.instance)
        action, result = self.sonnyClient.Community.change_name_of_community(name="USWNT????")
        self.assertEquals(action.status, "rejected")
        self.assertEquals(self.instance.name, "USWNT!!!!")

        # Now we give that permission to "anyone"
        self.client.PermissionResource.set_target(self.target_permission)
        action, result = self.client.PermissionResource.give_anyone_permission()

        # Our non-member can do the thing now!
        action, result = self.sonnyClient.Community.change_name_of_community(name="USWNT????")
        self.assertEquals(action.status, "implemented")
        self.assertEquals(self.instance.name, "USWNT????")

        # Let's toggle anyone back to disabled
        action, result = self.client.PermissionResource.remove_anyone_from_permission()

        # Once again our non-member can no longer do the thing
        action, result = self.sonnyClient.Community.change_name_of_community(name="USWNT :D :D :D")
        self.assertEquals(action.status, "rejected")
        self.assertEquals(self.instance.name, "USWNT????")

    def test_condition_form_generation(self):
        self.maxDiff = None

         # Pinoe adds a permission and a condition to the permission.
        action, permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Resources.AddRow, actors=[self.users.tobin.pk])
        self.client.update_target_on_all(target=permission)
        permission_data = [
            {"permission_type": Changes().Conditionals.Approve, "permission_actors": [self.users.pinoe.pk]}
        ]
        action, condition = self.client.Conditional.add_condition(
            condition_type="approvalcondition", permission_data=permission_data)

        permission = PermissionsItem.objects.get(pk=permission.pk)  #refresh
        permission_form = list(permission.get_condition_data().values())[0]
        permission_form.pop("element_id")  # can't compare it below since we don't know the value
        self.assertDictEqual(permission_form,
            {'type': 'ApprovalCondition', 'display_name': 'Approval Condition',
            'how_to_pass': 'individual 1 needs to approve this action',
            'fields':
            {'self_approval_allowed':
                {'display': 'Can individuals approve their own actions?', 'field_name': 'self_approval_allowed',
                'type': 'BooleanField', 'required': '', 'value': False, 'can_depend': False},
            'approve_roles':
                {'display': 'Roles who can approve', 'type': 'RoleListField', 'required': False, 'can_depend': True,
                'value': None, 'field_name': 'approve_roles', 'for_permission': True,
                'full_name': 'concord.conditionals.state_changes.ApproveStateChange'},
            'approve_actors':
                {'display': 'People who can approve', 'type': 'ActorListField', 'required': False, 'value': [1], 'can_depend': True,
                'field_name': 'approve_actors', 'for_permission': True,
                'full_name': 'concord.conditionals.state_changes.ApproveStateChange'},
            'reject_roles':
                {'display': 'Roles who can reject', 'type': 'RoleListField', 'required': False, 'value': None, 'can_depend': True,
                'field_name': 'reject_roles', 'for_permission': True,
                'full_name': 'concord.conditionals.state_changes.RejectStateChange'},
            'reject_actors':
                {'display': 'People who can reject', 'type': 'ActorListField', 'required': False, 'value': None, 'can_depend': True,
                'field_name': 'reject_actors', 'for_permission': True,
                'full_name': 'concord.conditionals.state_changes.RejectStateChange'}}})

    def test_has_permission(self):

        # Create a group with members, give members permission to change the group name
        self.instance = self.client.Community.create_community(name="USWNT")
        self.client.Community.set_target(self.instance)
        self.client.Community.add_members_to_community(member_pk_list=[self.users.rose.pk, self.users.crystal.pk,
            self.users.tobin.pk])
        self.client.update_target_on_all(target=self.instance)
        action, result = self.client.PermissionResource.add_permission(change_type=Changes().Communities.ChangeName,
            roles=['members'])

        self.client.update_actor_on_all(actor=self.users.rose)
        result = self.client.PermissionResource.has_permission(self.client, "change_name_of_community", {})
        self.assertTrue(result)


class ConditionSystemTest(DataTestCase):

    def test_condition_text_util_with_vote_condition(self):
        permission = PermissionsItem()
        permission_data = [{ "permission_type": Changes().Conditionals.AddVote,
            "permission_actors": [self.users.crystal.pk, self.users.jmac.pk] }]
        change = AddConditionStateChange(condition_type="votecondition", leadership_type=None,
            condition_data={"permission_data": permission_data})
        text = condition_to_text(change)
        self.assertEquals(text, "on the condition that individuals 5 and 6 vote")

    def test_condition_text_util_with_approval_condition(self):
        self.client = Client(actor=self.users.pinoe)
        community = self.client.Community.create_community(name="Test community")
        permission_data = [{ "permission_type": Changes().Conditionals.Approve, "permission_roles": ["members"] },
            { "permission_type": Changes().Conditionals.Reject, "permission_actors": [self.users.crystal.pk]}]
        change = AddConditionStateChange(condition_type="approvalcondition", condition_data={"permission_data": permission_data},
            leadership_type="governor")
        text = condition_to_text(change)
        self.assertEquals(text, "on the condition that those with role members approve and individual 5 does not reject")


class ConditionalsTest(DataTestCase):

    def setUp(self):

        self.client = Client(actor=self.users.pinoe)
        self.instance = self.client.Community.create_community(name="USWNT")
        self.client.update_target_on_all(target=self.instance)
        self.client.Community.add_members_to_community(member_pk_list=[self.users.rose.pk])
        action, self.new_list = self.client.List.add_list(**self.list_resource_params)

    def test_vote_conditional(self):

        # Pinoe adds a permission that says that Rose can add items to a list
        self.client.PermissionResource.set_target(target=self.new_list)
        action, permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Resources.AddRow, actors=[self.users.rose.pk])

        # But she places a vote condition on the permission
        self.client.update_target_on_all(target=permission)
        permission_data = [{ "permission_type": Changes().Conditionals.AddVote,
            "permission_actors": [self.users.jmac.pk, self.users.crystal.pk] }]
        action, result = self.client.Conditional.add_condition(condition_type="votecondition",
            permission_data=permission_data)

        # Rose tries to add an item, triggering the condition
        self.client.update_actor_on_all(actor=self.users.rose)
        self.client.update_target_on_all(target=self.new_list)
        action, result = self.client.List.add_row_to_list(row_content={"player name": "Sam Staab"})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "waiting")

        # We get the vote condition
        item = self.client.Conditional.get_condition_items_given_action_and_source(
            action=action, source=permission)[0]
        vote_condition = self.client.Conditional.get_condition_as_client(condition_type="VoteCondition", pk=item.pk)

        # Now Crystal and JMac can vote but Rose can't
        vote_condition.set_actor(actor=self.users.crystal)
        action,result = vote_condition.vote(vote="yea")
        self.assertDictEqual(vote_condition.get_current_results(),
            { "yeas": 1, "nays": 0, "abstains": 0 })

        vote_condition.set_actor(actor=self.users.jmac)
        action, result = vote_condition.vote(vote="abstain")
        self.assertDictEqual(vote_condition.get_current_results(),
            { "yeas": 1, "nays": 0, "abstains": 1})

        vote_condition.set_actor(actor=self.users.rose)
        vote_condition.vote(vote="abstain")
        self.assertDictEqual(vote_condition.get_current_results(),
            { "yeas": 1, "nays": 0, "abstains": 1})

    def test_approval_conditional(self):
        """
        Tests that changes to a resource require approval from a specific person,
        check that that person can approve the change and others can't.
        """

        # Pinoe adds a permission that says that Rose can add items to a list
        self.client.PermissionResource.set_target(target=self.new_list)
        action, permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Resources.AddRow, actors=[self.users.rose.pk])

        # But she places a condition on the permission that Rose has to get
        # approval (without specifying permissions, so it uses the default governing/foundational.
        self.client.update_target_on_all(target=permission)
        self.client.Conditional.add_condition(condition_type="approvalcondition")

        # Rose tries to add an item, triggering the condition
        self.client.update_actor_on_all(actor=self.users.rose)
        self.client.update_target_on_all(target=self.new_list)
        rose_action, result = self.client.List.add_row_to_list(row_content={"player name": "Sam Staab"})
        self.assertEquals(Action.objects.get(pk=rose_action.pk).status, "waiting")

        # We get the approval condition
        item = self.client.Conditional.get_condition_items_given_action_and_source(
            action=rose_action, source=permission)[0]
        approval_condition = self.client.Conditional.get_condition_as_client(
            condition_type="ApprovalCondition", pk=item.pk)
        approval_condition.set_actor(actor=self.users.pinoe)
        action, result = approval_condition.approve()
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

        # And Rose's item has been added
        self.assertEquals(Action.objects.get(pk=rose_action.pk).status, "implemented")

    def test_add_and_remove_condition_on_permission(self):

        # Pinoe adds a permission that says that Rose can add items to a list
        self.client.PermissionResource.set_target(target=self.new_list)
        action, permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Resources.AddRow, actors=[self.users.rose.pk])

        # But she places a condition on the permission that Rose has to get
        # approval (without specifying permissions, so it uses the default governing/foundational.
        self.client.update_target_on_all(target=permission)
        self.client.Conditional.add_condition(condition_type="approvalcondition")

        # Rose is stuck waiting
        self.client.update_actor_on_all(actor=self.users.rose)
        self.client.update_target_on_all(target=self.new_list)
        rose_action, result = self.client.List.add_row_to_list(row_content={"player name": "Sam Staab"})
        self.assertEquals(Action.objects.get(pk=rose_action.pk).status, "waiting")

        # Now Pinoe removes the condition
        self.client.update_actor_on_all(actor=self.users.pinoe)
        self.client.update_target_on_all(target=permission)
        action, result = self.client.Conditional.remove_condition()

        # When Rose tries again, it passes
        self.client.update_actor_on_all(actor=self.users.rose)
        self.client.update_target_on_all(target=self.new_list)
        rose_action_two, result = self.client.List.add_row_to_list(row_content={"player name": "Paige Nielsen"})
        self.assertEquals(Action.objects.get(pk=rose_action_two.pk).status, "implemented")

    def test_multiple_permissions_on_condition(self):

        # Pinoe adds a permission that says that Rose can add items to a list
        self.client.PermissionResource.set_target(target=self.new_list)
        action, permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Resources.AddRow, actors=[self.users.rose.pk])

        # But she places a condition on the permission that Rose has to get
        # approval.  She specifies that *Crystal* has to approve it.  She also
        # specifies that Andi Sullivan can reject it.
        self.client.update_target_on_all(target=permission)
        permission_data = [
            { "permission_type": Changes().Conditionals.Approve, "permission_actors": [self.users.crystal.pk] },
            { "permission_type": Changes().Conditionals.Reject, "permission_actors": [self.users.sully.pk] }
        ]
        action, result = self.client.Conditional.add_condition(
            condition_type="approvalcondition", permission_data=permission_data)

        # When Rose tries to add a row, Crystal can approve it
        self.client.update_actor_on_all(actor=self.users.rose)
        self.client.update_target_on_all(target=self.new_list)
        rose_action_one, result = self.client.List.add_row_to_list(row_content={"player name": "Sam Staab"})
        conditional_action = self.client.Conditional.get_condition_items_given_action_and_source(
            action=rose_action_one, source=permission)[0]
        crystalClient = Client(target=conditional_action, actor=self.users.crystal)
        action, result = crystalClient.ApprovalCondition.approve()

        # When Rose tries to add an item, Andi Sullivan can reject it
        rose_action_two, result = self.client.List.add_row_to_list(row_content={"player name": "Paige Nielsen"})
        conditional_action = self.client.Conditional.get_condition_items_given_action_and_source(
            action=rose_action_two, source=permission)[0]
        sullyClient = Client(target=conditional_action, actor=self.users.sully)
        action, result = sullyClient.ApprovalCondition.reject()

        # We see Rose's first item but not her second has been added
        self.assertEquals(Action.objects.get(pk=rose_action_one.pk).status, "implemented")
        self.assertEquals(Action.objects.get(pk=rose_action_two.pk).status, "rejected")
        self.new_list.refresh_from_db()
        self.assertEquals(self.new_list.get_rows(), [{"player name": "Sam Staab", "team": ""}])

        # Rose tries one more time - Andi can't approve and Crystal can't reject, so the action is waiting
        rose_action_three, result = self.client.List.add_row_to_list(row_content={"player name": "Paige Nielsen"})
        conditional_action = self.client.Conditional.get_condition_items_given_action_and_source(
            action=rose_action_three, source=permission)[0]

        crystalClient.ApprovalCondition.set_target(target=conditional_action)
        action, result = crystalClient.ApprovalCondition.reject()
        sullyClient.ApprovalCondition.set_target(target=conditional_action)
        action, result = sullyClient.ApprovalCondition.approve()
        self.assertEquals(Action.objects.get(pk=rose_action_three.pk).status, "waiting")

    def test_multiple_conditions_pass(self):

        # Pinoe creates a permission and adds two conditions to it
        self.client.PermissionResource.set_target(target=self.new_list)
        action, permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Resources.AddRow, actors=[self.users.rose.pk])
        self.client.update_target_on_all(target=permission)
        permission_data = [
            {"permission_type": Changes().Conditionals.Approve, "permission_actors": [self.users.crystal.pk]}
        ]
        action, result = self.client.Conditional.add_condition(
            condition_type="approvalcondition", permission_data=permission_data)
        action, result = self.client.Conditional.add_condition(
            condition_type="approvalcondition", permission_data=permission_data)

        # Rose takes action, it's waiting
        self.client.update_actor_on_all(actor=self.users.rose)
        self.client.update_target_on_all(target=self.new_list)
        rose_action, result = self.client.List.add_row_to_list(row_content={"player name": "Paige Nielsen"})
        self.assertEquals(rose_action.status, "waiting")

        # Resolve first condition but Rose is still waiting
        condition_items = self.client.Conditional.get_condition_items_given_action_and_source(
            action=rose_action, source=permission)
        crystalClient = Client(target=condition_items[0], actor=self.users.crystal)
        action, result = crystalClient.ApprovalCondition.approve()
        self.assertEquals(rose_action.status, "waiting")

        # Resolve second condition and Rose's action has passed
        crystalClient.update_target_on_all(condition_items[1])
        action, result = crystalClient.ApprovalCondition.approve()
        rose_action = Action.objects.get(pk=rose_action.pk)  # refresh
        self.assertEquals(rose_action.status, "implemented")

    def test_multiple_conditions_fail(self):

        # Pinoe creates a permission and adds two conditions to it
        self.client.PermissionResource.set_target(target=self.new_list)
        action, permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Resources.AddRow, actors=[self.users.rose.pk])
        self.client.update_target_on_all(target=permission)
        permission_data = [
            {"permission_type": Changes().Conditionals.Approve,
             "permission_actors": [self.users.crystal.pk]},
            {"permission_type": Changes().Conditionals.Reject,
             "permission_actors": [self.users.crystal.pk]},
        ]
        action, result = self.client.Conditional.add_condition(
            condition_type="approvalcondition", permission_data=permission_data)
        action, result = self.client.Conditional.add_condition(
            condition_type="approvalcondition", permission_data=permission_data)

        # Rose takes action, it's waiting
        self.client.update_actor_on_all(actor=self.users.rose)
        self.client.update_target_on_all(target=self.new_list)
        rose_action, result = self.client.List.add_row_to_list(row_content={"player name": "Paige Nielsen"})
        self.assertEquals(rose_action.status, "waiting")

        # Resolve first condition but Rose is still waiting
        condition_items = self.client.Conditional.get_condition_items_given_action_and_source(
            action=rose_action, source=permission)
        crystalClient = Client(target=condition_items[0], actor=self.users.crystal)
        action, result = crystalClient.ApprovalCondition.approve()
        self.assertEquals(rose_action.status, "waiting")

        # Reject second condition and Rose's action has failed
        crystalClient = Client(target=condition_items[1], actor=self.users.crystal)
        action, result = crystalClient.ApprovalCondition.reject()
        rose_action = Action.objects.get(pk=rose_action.pk)  # refresh
        self.assertEquals(rose_action.status, "rejected")

    def test_remove_one_condition(self):

        # Pinoe creates a permission and adds two conditions to it
        self.client.PermissionResource.set_target(target=self.new_list)
        action, permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Resources.AddRow, actors=[self.users.rose.pk])
        self.client.update_target_on_all(target=permission)
        permission_data = [
            {"permission_type": Changes().Conditionals.Approve,
             "permission_actors": [self.users.crystal.pk]},
            {"permission_type": Changes().Conditionals.Reject,
             "permission_actors": [self.users.crystal.pk]},
        ]
        action, result = self.client.Conditional.add_condition(
            condition_type="approvalcondition", permission_data=permission_data)
        action, result = self.client.Conditional.add_condition(
            condition_type="approvalcondition", permission_data=permission_data)

        # Then removes one
        element_ids = self.client.Conditional.get_element_ids()
        action, result = self.client.Conditional.remove_condition(element_id=element_ids[0])

        # Rose takes action, it's waiting
        self.client.update_actor_on_all(actor=self.users.rose)
        self.client.update_target_on_all(target=self.new_list)
        rose_action, result = self.client.List.add_row_to_list(row_content={"player name": "Paige Nielsen"})
        self.assertEquals(rose_action.status, "waiting")

        # Resolve first condition, Rose's action passes
        condition_items = self.client.Conditional.get_condition_items_given_action_and_source(
            action=rose_action, source=permission)
        crystalClient = Client(target=condition_items[0], actor=self.users.crystal)
        action, result = crystalClient.ApprovalCondition.approve()

        rose_action = Action.objects.get(pk=rose_action.pk)  # refresh
        self.assertEquals(rose_action.status, "implemented")

    def test_edit_condition(self):

        # Pinoe creates a permission and adds a condition to it
        self.client.PermissionResource.set_target(target=self.new_list)
        action, permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Resources.AddRow, actors=[self.users.rose.pk])
        self.client.update_target_on_all(target=permission)
        permission_data = [
            {"permission_type": Changes().Conditionals.Approve,
             "permission_actors": [self.users.crystal.pk]},
            {"permission_type": Changes().Conditionals.Reject,
             "permission_actors": [self.users.crystal.pk]},
        ]
        action, result = self.client.Conditional.add_condition(
            condition_type="approvalcondition", permission_data=permission_data)

        # Rose takes action, it's waiting
        self.client.update_actor_on_all(actor=self.users.rose)
        self.client.update_target_on_all(target=self.new_list)
        rose_action, result = self.client.List.add_row_to_list(row_content={"player name": "Paige Nielsen"})
        self.assertEquals(rose_action.status, "waiting")

        # Condition resolved, Rose's action passes
        condition_items = self.client.Conditional.get_condition_items_given_action_and_source(
            action=rose_action, source=permission)
        crystalClient = Client(target=condition_items[0], actor=self.users.crystal)
        action, result = crystalClient.ApprovalCondition.approve()

        rose_action = Action.objects.get(pk=rose_action.pk)  # refresh
        self.assertEquals(rose_action.status, "implemented")

        # Edit condition
        self.client.update_actor_on_all(actor=self.users.pinoe)
        self.client.update_target_on_all(target=permission)
        element_ids = self.client.Conditional.get_element_ids()
        permission_data = [
            {"permission_type": Changes().Conditionals.Approve, "permission_actors": [self.users.sully.pk]},
            {"permission_type": Changes().Conditionals.Reject, "permission_actors": [self.users.sully.pk]}
        ]
        action, result = self.client.Conditional.edit_condition(
            element_id=element_ids[0], permission_data=permission_data)

        # Rose takes second action, it's waiting
        self.client.update_actor_on_all(actor=self.users.rose)
        self.client.update_target_on_all(target=self.new_list)
        rose_action, result = self.client.List.add_row_to_list(row_content={"player name": "Paige Nielsen"})
        self.assertEquals(rose_action.status, "waiting")

        # Crystal can't approve
        condition_items = self.client.Conditional.get_condition_items_given_action_and_source(
            action=rose_action, source=permission)
        self.client.update_target_on_all(target=condition_items[0])
        self.client.update_actor_on_all(self.users.crystal)
        action, result = self.client.ApprovalCondition.approve()
        rose_action = Action.objects.get(pk=rose_action.pk)  # refresh
        self.assertEquals(rose_action.status, "waiting")

        # Sully can
        self.client.update_actor_on_all(self.users.sully)
        action, result = self.client.ApprovalCondition.approve()
        rose_action = Action.objects.get(pk=rose_action.pk)  # refresh
        self.assertEquals(rose_action.status, "implemented")


class BasicCommunityTest(DataTestCase):

    def setUp(self):
        self.client = Client(actor=self.users.pinoe)

    def test_create_community(self):
        community = self.client.Community.create_community(name="A New Community")
        self.assertEquals(community.get_unique_id(), "communities_community_1")
        self.assertEquals(community.name, "A New Community")

    def test_community_is_itself_collectively_owned(self):
        community = self.client.Community.create_community(name="A New Community")
        self.assertEquals(community.get_owner(), community)

    def test_change_name_of_community(self):
        community = self.client.Community.create_community(name="A New Community")
        self.client.Community.set_target(target=community)
        action, result = self.client.Community.change_name_of_community(name="A Newly Named Community")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(community.name, "A Newly Named Community")

    def test_reject_change_name_of_community_from_nongovernor(self):
        community = self.client.Community.create_community(name="A New Community")
        self.client.Community.set_target(target=community)
        self.client.Community.set_actor(actor=self.users.jj)
        action, result = self.client.Community.change_name_of_community(name="A Newly Named Community")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(community.name, "A New Community")

    def test_add_governor_to_community(self):
        community = self.client.Community.create_community(name="A New Community")
        self.client.Community.set_target(community)
        action, result = self.client.Community.add_members_to_community(member_pk_list=[self.users.crystal.pk])
        action, result = self.client.Community.add_governor_to_community(governor_pk=self.users.crystal.pk)
        self.assertEquals(community.roles.get_governors(),
            {'actors': [self.users.pinoe.pk, self.users.crystal.pk], 'roles': []})

    def test_cant_remove_permission_referenced_role(self):
        """Tests that we can't remove a role if it is referenced by permissions."""

        # create a community with a role on it & person in role
        community = self.client.Community.create_community(name="A New Community")
        self.client.update_target_on_all(target=community)
        action, result = self.client.Community.add_role_to_community(role_name="forwards")
        self.client.Community.add_members_to_community(member_pk_list=[self.users.christen.pk])
        action, result = self.client.Community.add_people_to_role(role_name="forwards",
            people_to_add=[self.users.christen.pk])
        self.assertEquals(community.roles.get_custom_roles(), {'forwards': [self.users.christen.pk]})

        # add a permission that references that role
        action, permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Communities.ChangeName, roles=["forwards"])

        # can't remove that role
        action, result = self.client.Community.remove_role_from_community(role_name="forwards")
        self.assertEquals(action.error_message,
            f"Role cannot be deleted until it is removed from permissions: {permission.pk}")

        # remove the permission
        self.client.PermissionResource.set_target(target=permission)
        action, result = self.client.PermissionResource.remove_permission()

        # now you can remove the role
        action, result = self.client.Community.remove_role_from_community(role_name="forwards")
        self.assertEquals(action.status, "implemented")
        self.assertEquals(community.roles.get_custom_roles(), {})

    def test_cant_remove_role_set_as_owner_role(self):
        """Tests that we can only remove a role if it's not an owner role."""

        # create a community with a role on it & person in role
        community = self.client.Community.create_community(name="A New Community")
        self.client.update_target_on_all(target=community)
        action, result = self.client.Community.add_role_to_community(role_name="forwards")
        self.client.Community.add_members_to_community(member_pk_list=[self.users.christen.pk])
        action, result = self.client.Community.add_people_to_role(role_name="forwards",
            people_to_add=[self.users.christen.pk])
        self.assertEquals(community.roles.get_custom_roles(), {'forwards': [self.users.christen.pk]})

        # add it to the owners & remove current owner
        action, result = self.client.Community.add_owner_role_to_community(role_name="forwards")

        # can't remove that role
        action, result = self.client.Community.remove_role_from_community(role_name="forwards")
        self.assertEquals(action.error_message, "Cannot remove role with ownership privileges")

        # remove owner role
        action, result = self.client.Community.remove_owner_role_from_community(role_name="forwards")

        # now we can remove the role
        action, result = self.client.Community.remove_role_from_community(role_name="forwards")
        self.assertEquals(action.status, "implemented")
        self.assertEquals(community.roles.get_custom_roles(), {})

    def test_cant_remove_people_from_role_when_they_are_the_only_owner(self):
        """Tests that people can't be removed from a role if the role is an owner role and
        removing them from said role would leave the community without an owner."""

        # create a community with a role on it & person in role
        community = self.client.Community.create_community(name="A New Community")
        self.client.update_target_on_all(target=community)
        action, result = self.client.Community.add_role_to_community(role_name="forwards")
        self.client.Community.add_members_to_community(member_pk_list=[self.users.christen.pk, self.users.crystal.pk])
        action, result = self.client.Community.add_people_to_role(role_name="forwards",
            people_to_add=[self.users.christen.pk])
        self.assertEquals(community.roles.get_custom_roles(), {'forwards': [self.users.christen.pk]})

        # add it to the owners & remove current owner
        action, result = self.client.Community.add_owner_role_to_community(role_name="forwards")
        action, result = self.client.Community.remove_owner_from_community(owner_pk=self.users.pinoe.pk)

        # Christen can't remove herself from role
        self.client.update_actor_on_all(actor=self.users.christen)
        action, result = self.client.Community.remove_people_from_role(role_name="forwards",
            people_to_remove=[self.users.christen.pk])
        self.assertEquals(action.error_message,
            "Cannot remove everyone from this role as doing so would leave the community without an owner")

        # add an actor to owners
        self.client.Community.add_owner_to_community(owner_pk=self.users.crystal.pk)
        self.client.Community.refresh_target()

        # now christen can remove herself from the role
        action, result = self.client.Community.remove_people_from_role(role_name="forwards",
            people_to_remove=[self.users.christen.pk])
        self.assertEquals(action.status, "implemented")
        self.assertEquals(community.roles.custom_roles, {'forwards': []})

    def test_cant_remove_owner_role_when_they_are_only_owner(self):
        """Tests that a role can't be removed as an owner role if doing so would leave the community
        without an owner."""

        # create a community with a role on it & person in role
        community = self.client.Community.create_community(name="A New Community")
        self.client.update_target_on_all(target=community)
        action, result = self.client.Community.add_role_to_community(role_name="forwards")
        self.client.Community.add_members_to_community(member_pk_list=[self.users.christen.pk, self.users.crystal.pk])
        action, result = self.client.Community.add_people_to_role(role_name="forwards",
            people_to_add=[self.users.pinoe.pk])
        self.assertEquals(community.roles.get_custom_roles(), {'forwards': [self.users.pinoe.pk]})

        # add it to the owners & remove current owner (though Pinoe is still owner via role)
        action, result = self.client.Community.add_owner_role_to_community(role_name="forwards")
        action, result = self.client.Community.remove_owner_from_community(owner_pk=self.users.pinoe.pk)

        # can't remove that role as owner role
        action, result = self.client.Community.remove_owner_role_from_community(role_name="forwards")
        self.assertEquals(action.error_message,
            "Cannot remove this role as doing so would leave the community without an owner")

        # add an actor to owners
        self.client.Community.add_owner_to_community(owner_pk=self.users.crystal.pk)
        self.client.Community.refresh_target()

        # now christen can remove the role
        action, result = self.client.Community.remove_owner_role_from_community(role_name="forwards")
        self.assertEquals(action.status, "implemented")
        self.assertEquals(community.roles.get_owners(), {'actors': [self.users.crystal.pk], 'roles': []})

    def test_cant_remove_self_when_you_are_the_only_owner(self):
        """Tests that people can't be removed as individual owner if doing so would leave the community
        without an owner."""

        # create a community with another member
        community = self.client.Community.create_community(name="A New Community")
        self.client.update_target_on_all(target=community)
        self.client.Community.add_members_to_community(member_pk_list=[self.users.christen.pk])

        # can't remove self as owner
        action, result = self.client.Community.remove_owner_from_community(owner_pk=self.users.pinoe.pk)
        self.assertEquals(action.error_message,
            "Cannot remove owner as doing so would leave the community without an owner")

        # add an actor to owners
        self.client.Community.add_owner_to_community(owner_pk=self.users.christen.pk)

        # now christen can remove the role
        action, result = self.client.Community.remove_owner_from_community(owner_pk=self.users.pinoe.pk)
        self.assertEquals(action.status, "implemented")
        self.assertEquals(community.roles.get_owners(), {'actors': [self.users.christen.pk], 'roles': []})

    def test_removing_person_from_role_when_role_is_owner_role_requires_foundational_permission(self):
        """Removing a person from a role is typically not a foundational change, but if the role in
        question has been set as an owner role and/or a governing role, it should be considered
        foundational."""

        # create a community & members with role. governor and owner are different
        community = self.client.Community.create_community(name="A New Community")
        self.client.update_target_on_all(target=community)
        action, result = self.client.Community.add_role_to_community(role_name="forwards")
        self.client.Community.add_members_to_community(member_pk_list=[self.users.christen.pk, self.users.crystal.pk])
        action, result = self.client.Community.add_governor_to_community(governor_pk=self.users.christen.pk)
        self.christenClient = Client(actor=self.users.christen, target=community)

        # governor can add and remove people from role
        action, result = self.client.Community.add_people_to_role(role_name="forwards",
            people_to_add=[self.users.crystal.pk])
        self.assertEquals(community.roles.get_custom_roles(), {'forwards': [self.users.crystal.pk]})

        # make role a governing role
        action, result = self.client.Community.add_governor_role_to_community(role_name="forwards")

        # governor can no longer add and remove people from role
        action, result = self.christenClient.Community.remove_people_from_role(role_name="forwards",
            people_to_remove=[self.users.crystal.pk])
        self.assertEquals(action.status, "rejected")
        self.assertEquals(community.roles.get_custom_roles(), {'forwards': [self.users.crystal.pk]})

        # make role an owner role instead
        action, result = self.client.Community.remove_governor_role_from_community(role_name="forwards")
        action, result = self.client.Community.add_owner_role_to_community(role_name="forwards")

        # governor can still not add and remove people from role
        action, result = self.christenClient.Community.remove_people_from_role(role_name="forwards",
            people_to_remove=[self.users.crystal.pk])
        self.assertEquals(action.status, "rejected")
        self.assertEquals(community.roles.get_custom_roles(), {'forwards': [self.users.crystal.pk]})

        # remove owner role
        action, result = self.client.Community.remove_owner_role_from_community(role_name="forwards")

        # Gov can finally remove from role
        action, result = self.christenClient.Community.remove_people_from_role(role_name="forwards",
            people_to_remove=[self.users.crystal.pk])
        self.assertEquals(action.status, "implemented")
        self.assertEquals(community.roles.get_custom_roles(), {'forwards': []})


class PermissionResourceUtilsTest(DataTestCase):

    def test_delete_permissions_on_target(self):  # HERE
        from concord.permission_resources.utils import delete_permissions_on_target

        # create target, set permission and nested permission
        self.client = Client(actor=self.users.pinoe)
        community = self.client.Community.create_community(name="A New Community")
        self.client.PermissionResource.set_target(target=community)
        action, permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Communities.ChangeName, actors=[self.users.pinoe.pk])
        self.client.PermissionResource.set_target(target=permission)
        action2, permission2 = self.client.PermissionResource.add_permission(
            change_type=Changes().Permissions.AddRoleToPermission, actors=[self.users.pinoe.pk])
        self.assertEquals(len(PermissionsItem.objects.all()), 5)

        # call delete_permissions_on_target
        delete_permissions_on_target(community)
        self.assertEquals(len(PermissionsItem.objects.all()), 0)


class GoverningAuthorityTest(DataTestCase):

    def setUp(self):
        self.client = Client(actor=self.users.pinoe)
        self.community = self.client.Community.create_community(name="A New Community")
        self.client.update_target_on_all(target=self.community)
        self.client.Community.add_members_to_community(member_pk_list=[self.users.sonny.pk])
        self.client.Community.add_governor_to_community(governor_pk=self.users.sonny.pk)

    def test_with_conditional_on_governer_decision_making(self):

        # Set conditional on governor decision making.  Only Sonny can approve condition.
        permission_data = [{ "permission_type": Changes().Conditionals.Approve, "permission_actors": [self.users.sonny.pk]}]
        action, result = self.client.Conditional.add_condition(
            leadership_type="governor", condition_type="approvalcondition", permission_data=permission_data)
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented") # Action accepted

        # Governor Pinoe does a thing, creates a conditional action to be approved
        action, result = self.client.Community.change_name_of_community(name="A Newly Named Community")
        # self.assertEquals(Action.objects.get(pk=action.pk).status, "waiting")
        # self.assertEquals(self.community.name, "A New Community")
        # conditional_action = self.condClient.get_condition_item_given_action_and_source(action_pk=action.pk,
        #     source_id="governor_"+str(self.community.pk))

        # # Governer Sonny reviews
        # acc = ApprovalConditionClient(target=conditional_action, actor=self.users.sonny)
        # review_action, result = acc.approve()
        # self.assertEquals(Action.objects.get(pk=review_action.pk).status, "implemented")

        # # Now Governor Pinoe's thing passes.
        # self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        # self.community.refresh_from_db()
        # self.assertEquals(self.community.name, "A Newly Named Community")


class FoundationalAuthorityTest(DataTestCase):

    def setUp(self):

        self.client = Client(actor=self.users.pinoe)
        self.community = self.client.Community.create_community(name="A New Community")
        self.client.update_target_on_all(target=self.community)
        action, self.resource = self.client.List.add_list(**self.list_resource_params)

    def test_foundational_authority_override_on_community_owned_object(self):

        # By default, Aubrey's actions are not successful
        self.client.update_actor_on_all(actor=self.users.aubrey)
        self.client.update_target_on_all(target=self.resource)
        action, result = self.client.List.add_row_to_list(row_content={"player name": "Sam Staab"})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.get_rows(), [])

        # Owner Pinoe adds a specific permission for Aubrey
        self.client.update_actor_on_all(actor=self.users.pinoe)
        owner_action, result = self.client.PermissionResource.add_permission(
            change_type=Changes().Resources.AddRow, actors=[self.users.aubrey.pk])

        # Aubrey's action now passes
        self.client.update_actor_on_all(actor=self.users.aubrey)
        action, result = self.client.List.add_row_to_list(row_content={"player name": "Sam Staab"})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(self.resource.get_rows(), [{'player name': 'Sam Staab', 'team': ''}])

        # Now switch foundational override.
        self.client.update_actor_on_all(actor=self.users.pinoe)
        fp_action, result = self.client.PermissionResource.enable_foundational_permission()

        # Aubrey's actions are no longer successful
        self.client.update_actor_on_all(actor=self.users.aubrey)
        action, result = self.client.List.add_row_to_list(row_content={"player name": "Trinity Rodman"})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.get_rows(), [{'player name': 'Sam Staab', 'team': ''}])

    def test_foundational_authority_override_on_community_owned_object_with_conditional(self):

        # Pinoe, Tobin, Christen and JMac are members of the community.
        self.client.update_target_on_all(self.community)
        action, result = self.client.Community.add_members_to_community(member_pk_list=[self.users.tobin.pk, self.users.christen.pk,
            self.users.jmac.pk])
        com_members = self.client.Community.get_members()
        self.assertCountEqual(com_members,
            [self.users.pinoe, self.users.tobin, self.users.christen, self.users.jmac])

        # In this community, all members are owners but for the foundational authority to do
        # anything they must agree via majority vote.
        action, result = self.client.Community.add_owner_role_to_community(role_name="members") # Add member role
        permission_data = [{ "permission_type": Changes().Conditionals.AddVote, "permission_roles": ["members"]}]
        action, result = self.client.Conditional.add_condition(
            leadership_type="owner", condition_type="votecondition",
            condition_data={"voting_period": 1 }, permission_data=permission_data)

        # Christen tries to  add a row to the list but is not successful because it's not something
        # that triggers foundational authority.
        self.client.update_target_on_all(self.resource)
        self.client.update_actor_on_all(actor=self.users.christen)
        action, result = self.client.List.add_row_to_list(row_content={"player name": "Sam Staab"})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")

        # Christen tries to switch on foundational override.  This is a foundational change and thus it
        # enter the foundational pipeline, triggers a vote condition, and generates a vote. Everyone votes
        # and it's approved.
        key_action, result = self.client.List.enable_foundational_permission()
        self.assertEquals(Action.objects.get(pk=key_action.pk).status, "waiting")

        condition_item = self.client.Conditional.get_condition_items_given_action_and_source(action=key_action,
            source=self.community, leadership_type="owner")[0]

        client = Client(target=condition_item, actor=self.users.pinoe)
        client.VoteCondition.vote(vote="yea")
        client.VoteCondition.set_actor(actor=self.users.tobin)
        client.VoteCondition.vote(vote="yea")
        client.VoteCondition.set_actor(actor=self.users.jmac)
        client.VoteCondition.vote(vote="yea")
        client.VoteCondition.set_actor(actor=self.users.christen)
        client.VoteCondition.vote(vote="yea")

        # hack to get around the one hour minimum voting period
        condition_item.voting_starts = timezone.now() - timedelta(hours=2)
        condition_item.save(override_check=True)

        self.assertEquals(Action.objects.get(pk=key_action.pk).status, "implemented")
        self.resource.refresh_from_db()
        self.assertTrue(self.resource.foundational_permission_enabled)

    def test_change_governors_requires_foundational_authority(self):

        # Pinoe is the owner, Sully and Pinoe are governors.
        self.client.Community.set_target(self.community)
        self.client.Community.add_members_to_community(member_pk_list=[self.users.sully.pk, self.users.aubrey.pk])
        action, result = self.client.Community.add_governor_to_community(governor_pk=self.users.sully.pk)
        self.assertEquals(self.community.roles.get_governors(),
            {'actors': [self.users.pinoe.pk, self.users.sully.pk], 'roles': []})

        # Sully tries to add Aubrey as a governor.  She cannot, she is not an owner.
        self.client.Community.set_actor(actor=self.users.sully)
        action, result = self.client.Community.add_governor_to_community(governor_pk=self.users.aubrey.pk)
        self.assertEquals(self.community.roles.get_governors(),
            {'actors': [self.users.pinoe.pk, self.users.sully.pk], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")

        # Rose tries to add Aubrey as a governor.  She cannot, she is not an owner.
        self.client.Community.set_actor(actor=self.users.rose)
        action, result = self.client.Community.add_governor_to_community(governor_pk=self.users.aubrey.pk)
        self.assertEquals(self.community.roles.get_governors(),
            {'actors': [self.users.pinoe.pk, self.users.sully.pk], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")

        # Pinoe tries to add Aubrey as a governor.  She can, since has foundational authority.
        self.client.Community.set_actor(actor=self.users.pinoe)
        action, result = self.client.Community.add_governor_to_community(governor_pk=self.users.aubrey.pk)
        self.assertEquals(self.community.roles.get_governors(),
            {'actors': [self.users.pinoe.pk, self.users.sully.pk, self.users.aubrey.pk],
            'roles': []})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

    def test_change_owners_requires_foundational_authority(self):

        # Pinoe adds Crystal as owner.  There are now two owners with no conditions.
        self.client.Community.set_target(self.community)
        self.client.Community.add_members_to_community(member_pk_list=[self.users.crystal.pk, self.users.christen.pk])
        action, result = self.client.Community.add_owner_to_community(owner_pk=self.users.crystal.pk)
        self.assertEquals(self.community.roles.get_owners(),
            {'actors': [self.users.pinoe.pk, self.users.crystal.pk], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

        # Tobin tries to add Christen as owner.  She cannot, she is not an owner.
        self.client.Community.set_actor(actor=self.users.tobin)
        action, result = self.client.Community.add_owner_to_community(owner_pk=self.users.christen.pk)
        self.assertEquals(self.community.roles.get_owners(),
            {'actors': [self.users.pinoe.pk, self.users.crystal.pk], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")

        # Crystal tries to add Christen as owner.  She can, since has foundational authority.
        self.client.Community.set_actor(actor=self.users.crystal)
        action, result = self.client.Community.add_owner_to_community(owner_pk=self.users.christen.pk)
        self.assertEquals(self.community.roles.get_owners(),
            {'actors': [self.users.pinoe.pk, self.users.crystal.pk, self.users.christen.pk],
            'roles': []})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

    def test_change_foundational_override_requires_foundational_authority(self):

        # Pinoe is the owner, Pinoe and Crystal are governors.
        self.client.Community.set_target(self.community)
        self.client.Community.add_members_to_community(member_pk_list=[self.users.crystal.pk])
        action, result = self.client.Community.add_governor_to_community(governor_pk=self.users.crystal.pk)
        self.assertEquals(self.community.roles.get_governors(),
            {'actors': [self.users.pinoe.pk, self.users.crystal.pk], 'roles': []})
        self.client.update_target_on_all(target=self.resource)

        # JJ tries to enable foundational override on resource.
        # She cannot, she is not an owner.
        self.client.update_actor_on_all(actor=self.users.jj)
        action, result = self.client.List.enable_foundational_permission()
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.resource.refresh_from_db()
        self.assertFalse(self.resource.foundational_permission_enabled)

        # Crystal tries to enable foundational override on resource.
        # She cannot, she is not an owner.
        self.client.update_actor_on_all(actor=self.users.crystal)
        action, result = self.client.List.enable_foundational_permission()
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.resource.refresh_from_db()
        self.assertFalse(self.resource.foundational_permission_enabled)

        # Pinoe tries to enable foundational override on resource.
        # She can, since she is an owner and has foundational authority.
        self.client.update_actor_on_all(actor=self.users.pinoe)
        action, result = self.client.List.enable_foundational_permission()
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.resource.refresh_from_db()
        self.assertTrue(self.resource.foundational_permission_enabled)


class RolesetTest(DataTestCase):

    def setUp(self):

        self.client = Client(actor=self.users.pinoe)
        self.community = self.client.Community.create_community(name="USWNT")
        self.client.update_target_on_all(target=self.community)
        action, self.resource = self.client.List.add_list(**self.list_resource_params)

    # Test custom roles

    def test_basic_custom_role(self):

        # No custom roles so far
        roles = self.client.Community.get_custom_roles()
        self.assertEquals(roles, {})

        # Add a role
        action, result = self.client.Community.add_role_to_community(role_name="forwards")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        roles = self.client.Community.get_custom_roles()
        self.assertEquals(roles, {'forwards': []})

        # Add people to role
        self.client.Community.add_members_to_community(member_pk_list=[self.users.christen.pk, self.users.crystal.pk])
        action, result = self.client.Community.add_people_to_role(role_name="forwards",
            people_to_add=[self.users.christen.pk, self.users.crystal.pk, self.users.pinoe.pk])
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        roles = self.client.Community.get_roles()
        self.assertCountEqual(roles["forwards"],
            [self.users.christen.pk, self.users.crystal.pk, self.users.pinoe.pk])

        # Remove person from role
        action, result = self.client.Community.remove_people_from_role(role_name="forwards",
            people_to_remove=[self.users.crystal.pk])
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        roles = self.client.Community.get_roles()
        self.assertCountEqual(roles["forwards"], [self.users.christen.pk, self.users.pinoe.pk])

        # Remove role
        action, result = self.client.Community.remove_role_from_community(role_name="forwards")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        roles = self.client.Community.get_custom_roles()
        self.assertEquals(roles, {})

    def test_basic_role_works_with_permission_item(self):

        # Aubrey wants to add an item to the list, she can't
        self.client.Community.add_members_to_community(member_pk_list=[self.users.aubrey.pk])
        self.client.update_actor_on_all(actor=self.users.aubrey)
        self.client.update_target_on_all(target=self.resource)
        action, result = self.client.List.add_row_to_list(row_content={"player name": "Sam Staab"})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")

        # Pinoe adds a 'list_mod' role to the community which owns the resource
        self.client.update_actor_on_all(actor=self.users.pinoe)
        self.client.update_target_on_all(target=self.community)
        action, result = self.client.Community.add_role_to_community(role_name="list_mod")

        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.client.Community.refresh_target()
        roles = self.client.Community.get_custom_roles()
        self.assertEquals(roles, {'list_mod': []})

        # Pinoe gives that role permission to add lists
        action, permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Resources.AddRow, roles=["list_mod"])

        # Pinoe adds Aubrey to the 'namers' role in the community
        action, result = self.client.Community.add_people_to_role(role_name="list_mod",
            people_to_add=[self.users.aubrey.pk])

        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.community.refresh_from_db()
        roles = self.client.Community.get_roles()
        self.assertCountEqual(roles["list_mod"], [self.users.aubrey.pk])

        # Aubrey can now add items
        self.client.update_actor_on_all(actor=self.users.aubrey)
        self.client.update_target_on_all(target=self.resource)
        action, result = self.client.List.add_row_to_list(row_content={"player name": "Trinity Rodman"})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.resource.refresh_from_db()
        self.assertEquals(self.resource.get_rows(), [{'player name': 'Trinity Rodman', 'team': ''}])

        # Pinoe removes Aubrey from the namers role in the community
        self.client.update_actor_on_all(actor=self.users.pinoe)
        self.client.update_target_on_all(target=self.community)
        action, result = self.client.Community.remove_people_from_role(role_name="list_mod",
            people_to_remove=[self.users.aubrey.pk])
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.community.refresh_from_db()
        roles = self.client.Community.get_roles()
        self.assertCountEqual(roles["list_mod"], [])

        # Aubrey can no longer add items
        self.client.update_actor_on_all(actor=self.users.aubrey)
        self.client.update_target_on_all(target=self.resource)
        action, result = self.client.List.add_row_to_list(row_content={"player name": "Sam Staab"})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.resource.refresh_from_db()
        self.assertEquals(self.resource.get_rows(), [{'player name': 'Trinity Rodman', 'team': ''}])

    def test_basic_role_works_with_governor(self):

        # Aubrey wants to add a row and can't
        self.client.update_actor_on_all(actor=self.users.aubrey)
        self.client.update_target_on_all(target=self.resource)
        action, result = self.client.List.add_row_to_list(row_content={"player name": "Sam Staab"})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")

        # Pinoe adds member role to governors
        self.client.update_actor_on_all(actor=self.users.pinoe)
        self.client.update_target_on_all(target=self.community)
        action, result = self.client.Community.add_governor_role_to_community(role_name="members")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.client.Community.refresh_target()
        gov_info = self.client.Community.get_governorship_info()
        self.assertDictEqual(gov_info, {'actors': [self.users.pinoe.pk], 'roles': ['members']})

        # Aubrey tries again and still can't
        self.client.update_actor_on_all(actor=self.users.aubrey)
        self.client.update_target_on_all(target=self.resource)
        action, result = self.client.List.add_row_to_list(row_content={"player name": "Sam Staab"})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")

        # Pinoe adds Aubrey as a member
        self.client.update_actor_on_all(actor=self.users.pinoe)
        self.client.update_target_on_all(target=self.community)
        action, result = self.client.Community.add_members_to_community(member_pk_list=[self.users.aubrey.pk])
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        roles = self.client.Community.get_roles()
        self.assertCountEqual(roles["members"], [self.users.pinoe.pk, self.users.aubrey.pk])

        # Aubrey tries to do a thing and can
        self.client.update_actor_on_all(actor=self.users.aubrey)
        self.client.update_target_on_all(target=self.resource)
        action, result = self.client.List.add_row_to_list(row_content={"player name": "Sam Staab"})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

    def test_add_member_and_remove_member_from_roleset(self):

        self.assertEquals(self.client.Community.get_members(), [self.users.pinoe])

        # Pinoe adds Aubrey to the community
        self.client.Community.add_members_to_community(member_pk_list=[self.users.aubrey.pk])
        self.assertCountEqual(self.client.Community.get_members(),
            [self.users.pinoe, self.users.aubrey])

        # Pinoe removes Aubrey from the community
        action, result = self.client.Community.remove_members_from_community(member_pk_list=[self.users.aubrey.pk])
        self.assertEquals(self.client.Community.get_members(), [self.users.pinoe])


class FieldMatchesFilterTest(DataTestCase):
    """NOTE: this was a configurable permission test, but we've swapped out configurable permissions for filters.
    Nevertheless, this tests approximately the same user-facing functionality."""

    def setUp(self):

        self.client = Client(actor=self.users.pinoe)

        # Create a community & client
        self.instance = self.client.Community.create_community(name="USWNT")
        self.client.update_target_on_all(self.instance)

        # Add roles to community and assign members
        self.client.Community.add_members_to_community(member_pk_list=[self.users.rose.pk, self.users.tobin.pk,
            self.users.christen.pk, self.users.crystal.pk, self.users.jmac.pk,
            self.users.aubrey.pk, self.users.sonny.pk, self.users.sully.pk,
            self.users.jj.pk])
        self.client.Community.add_role_to_community(role_name="forwards")
        self.client.Community.add_role_to_community(role_name="spirit players")

        # Make separate clients for other users.
        self.tobinClient = Client(actor=self.users.tobin, target=self.instance)
        self.roseClient = Client(actor=self.users.rose, target=self.instance)
        self.sonnyClient = Client(actor=self.users.sonny, target=self.instance)

        # Create request objects
        Request = namedtuple('Request', 'user')
        self.request = Request(user=self.users.pinoe)

    def test_generated_description_fields(self):
        """Tests how the "Add people to role" change and linked filter generate text."""

        # Add permission and condition
        action, permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Communities.AddPeopleToRole, actors=[self.users.rose.pk])
        self.client.update_target_on_all(target=permission)
        action, condition = self.client.Conditional.add_condition(condition_type="RoleMatchesFilter",
            condition_data={"role_name": "spirit players"})

        # test text on change object
        created_change_obj = permission.get_state_change_object()
        self.assertEquals(created_change_obj.change_description(), "Add people to role")
        self.assertEquals(created_change_obj.change_description(capitalize=False), "add people to role")

        # test text on action
        action, result = self.roseClient.Community.add_people_to_role(role_name="spirit players",
            people_to_add=[self.users.aubrey.pk])
        self.assertEquals(action.change.description_present_tense(), "add people with IDs (10) to role 'spirit players'")
        self.assertEquals(action.change.description_past_tense(), "added people with IDs (10) to role 'spirit players'")

        # test text on condition
        condition_data = list(permission.get_condition_data().values())[0]
        self.assertEquals(condition_data["how_to_pass"], "the role's name is 'spirit players'")

    def test_permission_with_rolematches_condition(self):

        # Pinoe configures a position so that only Rose can add people to the Spirit Players role
        # and not the Forwards role
        action, permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Communities.AddPeopleToRole, actors=[self.users.rose.pk])
        self.client.update_target_on_all(target=permission)
        action, condition = self.client.Conditional.add_condition(condition_type="RoleMatchesFilter",
            condition_data={"role_name": "spirit players"})

        # Rose can add Aubrey to to the Spirit Players role
        self.client.update_target_on_all(target=self.instance)
        action, result = self.roseClient.Community.add_people_to_role(role_name="spirit players",
            people_to_add=[self.users.aubrey.pk])
        roles = self.client.Community.get_roles()
        self.assertEquals(roles["spirit players"], [self.users.aubrey.pk])

        # Rose cannot add Christen to the forwards role
        self.roseClient.Community.add_people_to_role(role_name="forwards", people_to_add=[self.users.christen.pk])
        roles = self.client.Community.get_roles()
        self.assertEquals(roles["forwards"], [])


class MockActionTest(DataTestCase):

    def setUp(self):

        self.client = Client(actor=self.users.pinoe)

        # Create a Community and Client and some members
        self.instance = self.client.Community.create_community(name="USWNT")
        self.client.update_target_on_all(self.instance)
        self.client.Community.add_members_to_community(member_pk_list=[self.users.rose.pk, self.users.tobin.pk,
            self.users.christen.pk, self.users.aubrey.pk])

    def test_single_mock_action(self):

        self.client.Community.mode = "mock"
        action = self.client.Community.add_role_to_community(role_name="forwards")
        self.assertTrue(action.is_mock)

    def test_check_permissions_for_action_group_when_user_has_unconditional_permission(self):

        from concord.actions.utils import check_permissions_for_action_group
        self.client.Community.mode = "mock"

        add_forwards_action = self.client.Community.add_role_to_community(role_name="forwards")
        add_mids_action = self.client.Community.add_role_to_community(role_name="midfielders")

        summary_status, log = check_permissions_for_action_group([add_forwards_action, add_mids_action])

        self.assertEquals(summary_status, "approved")
        self.assertEquals(log[0]["status"], "approved")
        self.assertEquals(log[1]["status"], "approved")

    def test_check_permissions_for_action_group_when_user_does_not_have_permission(self):

        # Pinoe sets specific permission that Tobin does not have
        action, permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Communities.AddRole, actors=[self.users.christen.pk])

        from concord.actions.utils import check_permissions_for_action_group
        self.client.Community.mode = "mock"
        self.client.Community.set_actor(actor=self.users.tobin)

        add_forwards_action = self.client.Community.add_role_to_community(role_name="forwards")
        add_mids_action = self.client.Community.add_role_to_community(role_name="midfielders")

        summary_status, log = check_permissions_for_action_group([add_forwards_action, add_mids_action])

        self.assertEquals(summary_status, "rejected")
        self.assertEquals(log[0]["status"], "rejected")
        self.assertEquals(log[1]["status"], "rejected")

    def test_check_permissions_for_action_group_when_user_has_conditional_permission(self):

         # Pinoe sets specific permission & condition on that permission
        action, permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Communities.AddRole, actors=[self.users.tobin.pk])
        self.client.Conditional.set_target(permission)
        perm_data = [ { "permission_type": Changes().Conditionals.Approve, "permission_actors": [self.users.christen.pk] } ]
        self.client.Conditional.add_condition(condition_type="approvalcondition", permission_data=perm_data)

        from concord.actions.utils import check_permissions_for_action_group
        self.client.Community.mode = "mock"
        self.client.Community.set_actor(actor=self.users.tobin)

        add_forwards_action = self.client.Community.add_role_to_community(role_name="forwards")
        add_mids_action = self.client.Community.add_role_to_community(role_name="midfielders")

        summary_status, log = check_permissions_for_action_group([add_forwards_action, add_mids_action])

        self.assertEquals(summary_status, "waiting")
        self.assertEquals(log[0]["status"], "waiting")
        self.assertEquals(log[1]["status"], "waiting")


class TemplateTest(DataTestCase):

    def setUp(self):

        self.client = Client(actor=self.users.pinoe)

        # Create a Community and Client
        self.instance = self.client.Community.create_community(name="USWNT")
        self.client.update_target_on_all(self.instance)
        self.client.Community.add_role_to_community(role_name="forwards")
        self.client.Community.add_members_to_community(member_pk_list=[self.users.tobin.pk])
        self.client.Community.add_people_to_role(role_name="forwards", people_to_add=[self.users.tobin.pk])

        # Create templates (note that this servces as a test that all templates can be instantiated)
        from django.core.management import call_command
        call_command('update_templates', recreate=True, verbosity=0)

    def test_create_invite_only_template_creates_template(self):
        template_model = TemplateModel.objects.filter(name="Invite Only")[0]
        self.assertEquals(template_model.name, "Invite Only")

    def test_apply_invite_only_template_to_community(self):

        # Delete default permissions which interfere with our assumptions
        from concord.permission_resources.utils import delete_permissions_on_target
        delete_permissions_on_target(self.instance)

        # Before applying template, Tobin (with role Forward) cannot add members
        self.client.Community.set_actor(actor=self.users.tobin)
        action, result = self.client.Community.add_members_to_community(member_pk_list=[self.users.christen.pk])
        self.assertEquals(action.status, "rejected")
        self.assertEquals(self.client.Community.get_members(), [self.users.pinoe, self.users.tobin])

        # Pinoe applies template model to community
        supplied_fields = { "addmembers_permission_roles": ["forwards"],
            "addmembers_permission_actors": [] }
        template_model = TemplateModel.objects.filter(name="Invite Only")[0]
        action, actions_and_results = self.client.Template.apply_template(template_model_pk=template_model.pk,
            supplied_fields=supplied_fields)
        self.assertEquals(action.status, "implemented")
        self.assertEquals(actions_and_results[0]["result"].__class__.__name__, "PermissionsItem")
        self.assertDictEqual(action.get_template_info(),
            {'actions': ["add permission 'add members to community' to USWNT",
                         "add condition approvalcondition to the result of action number 1 in this template"],
             'name': 'Invite Only',
             'supplied_fields': {'has_data': True, 'fields': ["What roles can invite new members? ['forwards']",
                                                              'What actors can invite new members? []']},
             'foundational': 'None of the actions are foundational, so they do not necessarily require owner approval to pass.'})

        # now Tobin can add members but conditionally
        action, result = self.client.Community.add_members_to_community(member_pk_list=[self.users.christen.pk])
        self.assertEquals(action.status, "waiting")

        # the added member approves and is added to community
        condition_item = self.client.Conditional.get_condition_items_for_action(action_pk=action.pk)[0]
        self.client.ApprovalCondition.set_actor(actor=self.users.christen)
        self.client.ApprovalCondition.set_target(target=condition_item)
        action, result = self.client.ApprovalCondition.approve()
        self.assertEquals(action.status, "implemented")
        self.client.Community.target.refresh_from_db()
        self.assertEquals(self.client.Community.get_members(),
                          [self.users.pinoe, self.users.tobin, self.users.christen])


class PermissionedReadTest(DataTestCase):

    def setUp(self):

        self.client = Client(actor=self.users.pinoe)

        # Create a community with roles
        self.instance = self.client.Community.create_community(name="USWNT")
        self.client.update_target_on_all(self.instance)
        self.client.Community.add_role_to_community(role_name="forwards")
        self.client.Community.add_members_to_community(member_pk_list=[self.users.tobin.pk, self.users.rose.pk])
        self.client.Community.add_people_to_role(role_name="forwards", people_to_add=[self.users.tobin.pk])

        # Create a resource
        action, self.resource = self.client.List.add_list(**self.list_resource_params)

        # create clients for users
        self.tobinClient = Client(actor=self.users.tobin, target=self.resource)
        self.roseClient = Client(actor=self.users.rose, target=self.resource)

    def test_permission_read(self):
        # Only people with role "forwards" can view the resource
        action, result = self.client.PermissionResource.add_permission(change_type=Changes().Actions.View, roles=["forwards"])

        # User Rose without role 'forwards' can't see object
        self.client.update_target_on_all(target=self.resource)
        action, result = self.roseClient.List.view_fields()
        self.assertEquals(action.status, "rejected")

        # User Tobin with role 'forwards' can see object
        action, result = self.tobinClient.List.view_fields()
        self.assertEquals(action.status, "implemented")
        self.assertEquals(result,
            {
                'id': 1,
                'creator': self.users.pinoe,
                'name': 'Go USWNT!',
                'description': 'Our favorite players',
                'rows': '[]',
                'row_configuration': '{"player name": {"required": true, "default_value": null}, "team": {"required": false, "default_value": null}}',
                'foundational_permission_enabled': False,
                'governing_permission_enabled': True,
                'owner': "USWNT"
            })

    def test_permissioned_read_limited_by_condition(self):

        # Only people with role "forwards" can view the resource
        action, permission = self.client.PermissionResource.add_permission(change_type=Changes().Actions.View, roles=["forwards"])

        # They are limited by condition to only see name or ID
        self.client.update(target=permission)
        action, result = self.client.Conditional.add_condition(condition_type="LimitedFieldsFilter",
            condition_data={"limited_fields": json.dumps(["name", "id"])})

        # They try to get other fields, get error
        action, result = self.tobinClient.Community.view_fields(fields_to_include=["owner"])
        self.assertEquals(action.status, "rejected")

        # They try to get the right field, success
        action, result = self.tobinClient.Community.view_fields(fields_to_include=["name"])
        self.assertEquals(action.status, "implemented")
        self.assertEquals(result, {'name': 'Go USWNT!'})

        # They try to get two fields at once, success
        action, result = self.tobinClient.Community.view_fields(fields_to_include=["name", "id"])
        self.assertEquals(action.status, "implemented")
        self.assertEquals(result, {'name': 'Go USWNT!', "id": 1})

        # They try to get one allowed field and one unallowed field, error
        action, result = self.tobinClient.Community.view_fields(fields_to_include=["name", "owner"])
        self.assertEquals(action.status, "rejected")

        # They try to get a nonexistent field, error
        result = self.tobinClient.Community.view_fields(fields_to_include=["potato"])
        self.assertTrue(result, "Attempting to view field(s) potato that are not on target Resource object (1)")

    def test_multiple_readpermissions(self):

        # Permission 1: user Tobin can only see field "name"
        action, permission_1 = self.client.PermissionResource.add_permission(change_type=Changes().Actions.View,
            actors=[self.users.tobin.pk])
        self.client.update(target=permission_1)
        action, result = self.client.Conditional.add_condition(condition_type="LimitedFieldsFilter",
            condition_data={"limited_fields": json.dumps(["name"])})

        # Permission 2: user Rose can only see field "owner"
        self.client.update(target=self.instance)
        action, permission_1 = self.client.PermissionResource.add_permission(change_type=Changes().Actions.View,
            actors=[self.users.rose.pk])
        self.client.update(target=permission_1)
        action, result = self.client.Conditional.add_condition(condition_type="LimitedFieldsFilter",
            condition_data={"limited_fields": json.dumps(["owner"])})

        # Tobin can see name but not owner
        action, result = self.tobinClient.List.view_fields(fields_to_include=["name"])
        self.assertEquals(action.status, "implemented")
        self.assertEquals(result, {'name': 'Go USWNT!'})
        action, result = self.tobinClient.List.view_fields(fields_to_include=["owner"])
        self.assertEquals(action.status, "rejected")

        # Rose can see owner but not name
        action, result = self.roseClient.List.view_fields(fields_to_include=["owner"])
        self.assertEquals(action.status, "implemented")
        self.assertEquals(result, {'owner': 'USWNT'})
        action, result = self.roseClient.List.view_fields(fields_to_include=["name"])
        self.assertEquals(action.status, "rejected")


class CommentTest(DataTestCase):

    def setUp(self):

        self.client = Client(actor=self.users.pinoe)

        # Create a community with roles
        self.instance = self.client.Community.create_community(name="USWNT")
        self.client.update_target_on_all(target=self.instance)
        self.client.Community.add_role_to_community(role_name="forwards")
        self.client.Community.add_members_to_community(member_pk_list=[self.users.tobin.pk, self.users.rose.pk])
        self.client.Community.add_people_to_role(role_name="forwards", people_to_add=[self.users.tobin.pk])

        # Create a resource and put it in the community
        action, self.resource = self.client.List.add_list(**self.list_resource_params)

        # Create target of comment client
        self.client.update_target_on_all(target=self.resource)

    def test_add_comment(self):

        # we start off with no comments
        comments = list(self.client.Comment.get_all_comments_on_target())
        self.assertEquals(comments, [])

        # we add a comment and now we have one on the target
        self.client.Comment.add_comment(text="This is a new comment")
        comments = self.client.Comment.get_all_comments_on_target()
        self.assertEquals(comments.first().text, "This is a new comment")

    def test_edit_comment(self):

        # we start off by adding a comment
        self.client.Comment.add_comment(text="This is a new comment")
        comments = self.client.Comment.get_all_comments_on_target()
        self.assertEquals(comments.first().text, "This is a new comment")

        # when we edit it, the text changes
        self.client.Comment.set_target(comments.first())
        action, comment = self.client.Comment.edit_comment(text="This is an edited comment")
        self.client.Comment.set_target(self.resource)
        comments = self.client.Comment.get_all_comments_on_target()  # refresh
        self.assertEquals(comments.first().text, "This is an edited comment")

    def test_delete_comment(self):

        # we start off by adding a comment
        self.client.Comment.add_comment(text="This is a new comment")
        comments = self.client.Comment.get_all_comments_on_target()
        self.assertEquals(comments.first().text, "This is a new comment")

        # when we delete it, it disappears
        self.client.Comment.set_target(comments.first())
        self.client.Comment.delete_comment()
        self.client.Comment.set_target(self.resource)
        comments = self.client.Comment.get_all_comments_on_target()  # refresh
        self.assertEquals(list(comments), [])


class SimpleListTest(DataTestCase):

    def setUp(self):

        self.client = Client(actor=self.users.pinoe)

        # Create a community with roles
        self.instance = self.client.Community.create_community(name="USWNT")
        self.client.update_target_on_all(self.instance)
        self.client.Community.add_role_to_community(role_name="forwards")
        self.client.Community.add_members_to_community(member_pk_list=[self.users.tobin.pk, self.users.rose.pk])
        self.client.Community.add_people_to_role(role_name="forwards", people_to_add=[self.users.tobin.pk])

    def test_basic_list_functionality(self):

        # add a list
        self.assertEquals(len(self.client.List.get_all_lists_given_owner(self.instance)), 0)
        action, list_instance = self.client.List.add_list(name="Awesome Players",
            configuration={"player name": {"required": True}, "team": {"required": False}},
            description="Our fave players")
        self.assertEquals(len(self.client.List.get_all_lists_given_owner(self.instance)), 1)
        self.assertEquals(list_instance.name, "Awesome Players")

        # edit the list
        self.client.List.set_target(list_instance)
        action, list_instance = self.client.List.edit_list(name="Awesome Players!",
            description="Our fave players!")
        self.assertEquals(list_instance.name, "Awesome Players!")

        # add a few rows
        action, list_instance = self.client.List.add_row_to_list(row_content={"player name": "Sam Staab"})
        action, list_instance = self.client.List.add_row_to_list(row_content={"player name": "Tziarra King"}, index=0)
        action, list_instance = self.client.List.add_row_to_list(row_content={"player name": "Bethany Balcer"}, index=1)
        action, list_instance = self.client.List.add_row_to_list(row_content={"player name": "Ifeoma Onumonu"})
        self.assertEquals(list_instance.get_rows(),
            [{'player name': 'Tziarra King', 'team': ''},
            {'player name': 'Bethany Balcer', 'team': ''},
            {'player name': 'Sam Staab', 'team': ''},
            {'player name': 'Ifeoma Onumonu', 'team': ''}])

        # edit a row
        action, list_instance = self.client.List.edit_row_in_list(
            row_content={'player name': 'Tziarra King', "team": "Utah Royals"}, index=0)
        action, list_instance = self.client.List.edit_row_in_list(
            row_content={'player name': 'Bethany Balcer', "team": "OL Reign"}, index=1)
        action, list_instance = self.client.List.edit_row_in_list(
            row_content={'player name': 'Sam Staab', "team": "Washington Spirit"}, index=2)
        action, list_instance = self.client.List.edit_row_in_list(
            row_content={'player name': 'Ifeoma Onumonu', "team": "Sky Blue FC"}, index=3)
        self.assertEquals(list_instance.get_rows(),
            [{'player name': 'Tziarra King', 'team': 'Utah Royals'},
            {'player name': 'Bethany Balcer', 'team': 'OL Reign'},
            {'player name': 'Sam Staab', 'team': 'Washington Spirit'},
            {'player name': 'Ifeoma Onumonu', 'team': 'Sky Blue FC'}])

        # delete a row
        action, list_instance = self.client.List.delete_row_in_list(index=1)
        self.assertEquals(list_instance.get_rows(),
            [{'player name': 'Tziarra King', 'team': 'Utah Royals'},
            {'player name': 'Sam Staab', 'team': 'Washington Spirit'},
            {'player name': 'Ifeoma Onumonu', 'team': 'Sky Blue FC'}])

        # delete list
        action, deleted_list_pk = self.client.List.delete_list()
        self.assertEquals(len(self.client.List.get_all_lists_given_owner(self.instance)), 0)

    def test_edit_configuration_of_list(self):

        # add a list & rows
        action, list_instance = self.client.List.add_list(name="Awesome Players",
            configuration={"player name": {"required": True}, "team": {"required": False}},
            description="Our fave players")
        self.client.List.set_target(list_instance)
        action, list_instance = self.client.List.add_row_to_list(
            row_content={'player name': 'Tziarra King', "team": "Utah Royals"}, index=0)
        action, list_instance = self.client.List.add_row_to_list(
            row_content={'player name': 'Bethany Balcer', "team": "OL Reign"}, index=1)
        action, list_instance = self.client.List.add_row_to_list(
            row_content={'player name': 'Sam Staab', "team": "Washington Spirit"}, index=2)
        action, list_instance = self.client.List.add_row_to_list(
            row_content={'player name': 'Ifeoma Onumonu'}, index=3)

        # can't make team required since Ify is missing a team and there's no default value
        action, list_instance = self.client.List.edit_list(
            configuration={"player name": {"required": True}, "team": {"required": True}})
        self.assertEquals(action.error_message, 'Need default value for required field team')

        # add default value for Ify, and now we can make team required
        action, list_instance = self.client.List.edit_row_in_list(
            row_content={'player name': 'Ifeoma Onumonu', 'team': 'Sky Blue FC'}, index=3)
        action, list_instance = self.client.List.edit_list(
            configuration={"player name": {"required": True}, "team": {"required": True}})
        self.assertEquals(action.status, "implemented")

        # now when we try to add a new player without a team it's rejected
        action, list_instance = self.client.List.add_row_to_list(
            row_content={'player name': 'Paige Nielson'}, index=3)
        self.assertEquals(action.error_message,
            'Field team is required with no default_value, so must be supplied')

        # add position field with default value
        action, list_instance = self.client.List.edit_list(
            configuration={"player name": {"required": True}, "team": {"required": True},
                "position": {"required": True, "default_value": "forward"} })
        action, list_instance = self.client.List.add_row_to_list(
            row_content={'player name': 'Paige Nielson', 'team': 'Washington Spirit'}, index=3)
        self.assertEquals(list_instance.get_rows(),
            [{'player name': 'Tziarra King', 'team': 'Utah Royals', 'position': 'forward'},
            {'player name': 'Bethany Balcer', 'team': 'OL Reign', 'position': 'forward'},
            {'player name': 'Sam Staab', 'team': 'Washington Spirit', 'position': 'forward'},
            {'player name': 'Paige Nielson', 'team': 'Washington Spirit', 'position': 'forward'},
            {'player name': 'Ifeoma Onumonu', 'team': 'Sky Blue FC', 'position': 'forward'}])

        # remove position from config and it's gone
        action, list_instance = self.client.List.edit_list(
            configuration={"player name": {"required": True}, "team": {"required": True}})
        self.assertEquals(list_instance.get_rows(),
            [{'player name': 'Tziarra King', 'team': 'Utah Royals'},
            {'player name': 'Bethany Balcer', 'team': 'OL Reign'},
            {'player name': 'Sam Staab', 'team': 'Washington Spirit'},
            {'player name': 'Paige Nielson', 'team': 'Washington Spirit'},
            {'player name': 'Ifeoma Onumonu', 'team': 'Sky Blue FC'}])


class ConsensusConditionTest(DataTestCase):

    def setUp(self):

        self.client = Client(actor=self.users.pinoe)

        # Create a community with roles
        self.instance = self.client.Community.create_community(name="USWNT")
        self.client.update_target_on_all(self.instance)
        self.client.Community.add_role_to_community(role_name="midfielders")
        self.client.Community.add_role_to_community(role_name="forwards")
        self.client.Community.add_members_to_community(member_pk_list=[self.users.lindsey.pk, self.users.midge.pk, self.users.jj.pk,
            self.users.rose.pk, self.users.christen.pk])
        self.client.Community.add_people_to_role(
            role_name="midfielders", people_to_add=[self.users.lindsey.pk, self.users.jj.pk, self.users.rose.pk])
        self.client.Community.add_people_to_role(role_name="forwards", people_to_add=[self.users.midge.pk, self.users.rose.pk])

        # Create permission and condition
        action, self.permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Communities.ChangeName, roles=["forwards"])
        self.client.Conditional.set_target(self.permission)
        self.permission_data = [{"permission_type": Changes().Conditionals.RespondConsensus,
                            "permission_roles": ["midfielders", "forwards"] },
                           {"permission_type": Changes().Conditionals.ResolveConsensus,
                            "permission_roles": ["midfielders"]}]

    def test_initialize_consensus_condition(self):

        # add & trigger condition
        action, result = self.client.Conditional.add_condition(
            condition_type="consensuscondition", permission_data=self.permission_data)
        self.client.update_actor_on_all(self.users.midge)
        self.trigger_action, result = self.client.Community.change_name_of_community(name="United States Women's National Team")
        self.condition_item = self.client.Conditional.get_condition_items_for_action(action_pk=self.trigger_action.pk)[0]

        self.assertDictEqual(self.condition_item.get_responses(),
                          {"8": "no response", "2": "no response", "11": "no response", "12": "no response"})
        self.assertFalse(self.condition_item.ready_to_resolve())  # two days (default) have not passed

    def test_initialize_consensus_condition_on_governors(self):

        # test on governor (single)
        self.client.Conditional.set_target(self.instance)
        permission_data = [{"permission_type": Changes().Conditionals.RespondConsensus,
                            "permission_roles": ["governors"] },
                           {"permission_type": Changes().Conditionals.ResolveConsensus,
                            "permission_roles": ["governors"]}]
        action, result = self.client.Conditional.add_condition(
            condition_type="consensuscondition", leadership_type="governor",
            permission_data=permission_data)
        self.trigger_action, result = self.client.Community.change_name_of_community(name="United States Women's National Team")
        self.condition_item = self.client.Conditional.get_condition_items_for_action(action_pk=self.trigger_action.pk)[0]
        self.assertDictEqual(self.condition_item.get_responses(),
            {str(self.users.pinoe.pk): "no response" })
        self.assertFalse(self.condition_item.ready_to_resolve())  # two days (default) have not passed

        # test on governors (many)
        self.client.Community.add_governor_role_to_community(role_name="forwards")
        permission_data = [{"permission_type": Changes().Conditionals.RespondConsensus,
                            "permission_roles": ["governors"] },
                           {"permission_type": Changes().Conditionals.ResolveConsensus,
                            "permission_roles": ["governors"]}]
        action, result = self.client.Conditional.add_condition(
            condition_type="consensuscondition", leadership_type="governor", permission_data=permission_data)
        self.trigger_action, result = self.client.Community.change_name_of_community(name="United States Women's National Team")
        self.condition_item = self.client.Conditional.get_condition_items_for_action(action_pk=self.trigger_action.pk)[0]
        self.assertDictEqual(self.condition_item.get_responses(),
            {str(self.users.pinoe.pk): "no response", str(self.users.rose.pk): "no response",
             str(self.users.midge.pk): "no response"})
        self.assertFalse(self.condition_item.ready_to_resolve())  # two days (default) have not passed

    def test_initialize_consensus_condition_on_owners(self):

        self.client.Conditional.set_target(self.instance)
        self.client.Community.add_owner_role_to_community(role_name="forwards")
        permission_data = [{"permission_type": Changes().Conditionals.RespondConsensus,
                            "permission_roles": ["owners"] },
                           {"permission_type": Changes().Conditionals.ResolveConsensus,
                            "permission_roles": ["owners"]}]
        action, result = self.client.Conditional.add_condition(
            condition_type="consensuscondition", leadership_type="owner", permission_data=permission_data)
        self.trigger_action, result = self.client.Community.add_owner_role_to_community(
            role_name="members")
        self.condition_item = self.client.Conditional.get_condition_items_for_action(action_pk=self.trigger_action.pk)[0]
        self.assertDictEqual(self.condition_item.get_responses(),
            {str(self.users.pinoe.pk): "no response", str(self.users.rose.pk): "no response",
             str(self.users.midge.pk): "no response"})
        self.assertFalse(self.condition_item.ready_to_resolve())  # two days (default) have not passed

    def test_consensus_condition_timing(self):

        # add & trigger condition
        action, result = self.client.Conditional.add_condition(
            condition_type="consensuscondition", condition_data={"minimum_duration": 332},
            permission_data=self.permission_data)
        self.client.update_actor_on_all(self.users.midge)
        self.trigger_action, result = self.client.Community.change_name_of_community(name="United States Women's National Team")
        self.condition_item = self.client.Conditional.get_condition_items_for_action(action_pk=self.trigger_action.pk)[0]

        self.assertEquals(self.condition_item.duration_display(), "1 week, 6 days and 20 hours")
        self.assertEquals(int(self.condition_item.time_until_duration_passed()), 331)
        self.assertFalse(self.condition_item.ready_to_resolve())

    def test_loose_consensus_accept(self):

        # add & trigger condition
        action, result = self.client.Conditional.add_condition(
            condition_type="consensuscondition", condition_data={"minimum_duration": 0},
            permission_data=self.permission_data)

        self.client.update_actor_on_all(self.users.midge)
        self.trigger_action, result = self.client.Community.change_name_of_community(name="United States Women's National Team")
        self.condition_item = self.client.Conditional.get_condition_items_for_action(action_pk=self.trigger_action.pk)[0]

        self.assertTrue(self.condition_item.ready_to_resolve())  # can be resolved right away since duration is 0
        self.assertEquals(self.condition_item.current_result(), "rejected")  # no support yet

        # users respond, but not all users
        self.client.update_target_on_all(self.condition_item)
        self.client.update_actor_on_all(self.users.rose)
        self.client.ConsensusCondition.respond(response="support")
        self.client.update_actor_on_all(self.users.midge)
        self.client.ConsensusCondition.respond(response="stand aside")
        self.client.update_actor_on_all(self.users.lindsey)
        self.client.ConsensusCondition.respond(response="support with reservations")

        self.assertDictEqual(self.condition_item.get_responses(),
                          {"8": "no response", "2": "support", "11": "support with reservations", "12": "stand aside"})
        self.assertEquals(self.condition_item.current_result(), "approved")  # still no blocks

        self.assertEquals(self.condition_item.condition_status(), "waiting")
        self.client.ConsensusCondition.resolve()
        self.assertEquals(self.condition_item.condition_status(), "approved")

    def test_loose_consensus_reject(self):

        # add & trigger condition
        action, result = self.client.Conditional.add_condition(
            condition_type="consensuscondition", condition_data={"minimum_duration": 0},
            permission_data=self.permission_data)
        self.client.update_actor_on_all(self.users.midge)
        self.trigger_action, result = self.client.Community.change_name_of_community(name="United States Women's National Team")
        self.condition_item = self.client.Conditional.get_condition_items_for_action(action_pk=self.trigger_action.pk)[0]

        # users respond, some block
        self.client.update_target_on_all(self.condition_item)
        self.client.update_actor_on_all(self.users.rose)
        self.client.ConsensusCondition.respond(response="block")
        self.client.update_actor_on_all(self.users.midge)
        self.client.ConsensusCondition.respond(response="stand aside")
        self.client.update_actor_on_all(self.users.lindsey)
        self.client.ConsensusCondition.respond(response="support with reservations")
        self.assertEquals(self.condition_item.current_result(), "rejected")  # still no blocks

        self.assertEquals(self.condition_item.condition_status(), "waiting")
        self.client.ConsensusCondition.resolve()
        self.assertEquals(self.condition_item.condition_status(), "rejected")

    def test_strict_consensus_accept(self):

        # add & trigger condition
        action, result = self.client.Conditional.add_condition(
            condition_type="consensuscondition",
            condition_data={"minimum_duration": 0, "is_strict": True},
            permission_data=self.permission_data)
        self.client.update_actor_on_all(self.users.midge)
        self.trigger_action, result = self.client.Community.change_name_of_community(name="United States Women's National Team")
        self.condition_item = self.client.Conditional.get_condition_items_for_action(action_pk=self.trigger_action.pk)[0]
        self.assertTrue(self.condition_item.is_strict)

        # update some but not all users
        self.client.update_target_on_all(self.condition_item)
        self.client.update_actor_on_all(self.users.rose)
        self.client.ConsensusCondition.respond(response="support")
        self.client.update_actor_on_all(self.users.midge)
        self.client.ConsensusCondition.respond(response="stand aside")
        self.assertEquals(self.condition_item.current_result(), "rejected")  # missing participants = reject in strict mode

        # update the rest
        self.client.update_actor_on_all(self.users.lindsey)
        self.client.ConsensusCondition.respond(response="support with reservations")
        self.client.update_actor_on_all(self.users.jj)
        self.client.ConsensusCondition.respond(response="support")

        self.assertEquals(self.condition_item.condition_status(), "waiting")
        self.client.ConsensusCondition.resolve()
        self.assertEquals(self.condition_item.condition_status(), "approved")

    def test_strict_consensus_reject_with_blocks(self):

        # add & trigger condition
        action, result = self.client.Conditional.add_condition(
            condition_type="consensuscondition", condition_data={"minimum_duration": 0, "is_strict": True},
            permission_data=self.permission_data)
        self.client.update_actor_on_all(self.users.midge)
        self.trigger_action, result = self.client.Community.change_name_of_community(name="United States Women's National Team")
        self.condition_item = self.client.Conditional.get_condition_items_for_action(action_pk=self.trigger_action.pk)[0]
        self.assertTrue(self.condition_item.is_strict)

        # update some but not all users
        self.client.update_target_on_all(self.condition_item)
        self.client.update_actor_on_all(self.users.rose)
        self.client.ConsensusCondition.respond(response="support")
        self.client.update_actor_on_all(self.users.midge)
        self.client.ConsensusCondition.respond(response="stand aside")
        self.client.update_actor_on_all(self.users.lindsey)
        self.client.ConsensusCondition.respond(response="support with reservations")
        self.client.update_actor_on_all(self.users.jj)
        self.client.ConsensusCondition.respond(response="block")

        self.assertEquals(self.condition_item.condition_status(), "waiting")
        self.client.ConsensusCondition.resolve()
        self.assertEquals(self.condition_item.condition_status(), "rejected")

    def test_strict_consensus_reject_with_missing_participants(self):

        # add & trigger condition
        action, result = self.client.Conditional.add_condition(
            condition_type="consensuscondition",
            condition_data={"minimum_duration": 0, "is_strict": True},
            permission_data=self.permission_data)
        self.client.update_actor_on_all(self.users.midge)
        self.trigger_action, result = self.client.Community.change_name_of_community(name="United States Women's National Team")
        self.condition_item = self.client.Conditional.get_condition_items_for_action(action_pk=self.trigger_action.pk)[0]
        self.assertTrue(self.condition_item.is_strict)

        # update some but not all users
        self.client.update_target_on_all(self.condition_item)
        self.client.update_actor_on_all(self.users.rose)
        self.client.ConsensusCondition.respond(response="support")
        self.client.update_actor_on_all(self.users.jj)
        self.client.ConsensusCondition.respond(response="stand aside")

        self.assertEquals(self.condition_item.condition_status(), "waiting")
        action, response = self.client.ConsensusCondition.resolve()
        self.assertEquals(self.condition_item.condition_status(), "rejected")

    def test_consensus_condition_permissions(self):

        # add & trigger condition
        action, result = self.client.Conditional.add_condition(
            condition_type="consensuscondition",
            condition_data={"minimum_duration": 0},
            permission_data=self.permission_data)
        self.client.update_actor_on_all(self.users.midge)
        self.trigger_action, result = self.client.Community.change_name_of_community(name="United States Women's National Team")
        self.condition_item = self.client.Conditional.get_condition_items_for_action(action_pk=self.trigger_action.pk)[0]
        self.client.update_target_on_all(self.condition_item)

        # test respond permissions
        self.client.update_actor_on_all(self.users.midge)  # forward can respond
        action, result = self.client.ConsensusCondition.respond(response="support")
        self.assertEquals(action.status, "implemented")
        self.client.update_actor_on_all(self.users.jj)     # mid can respond
        action, result = self.client.ConsensusCondition.respond(response="stand aside")
        self.assertEquals(action.status, "implemented")
        self.client.update_actor_on_all(self.users.christen)     # person without role cannot respond
        action, result = self.client.ConsensusCondition.respond(response="stand aside")
        self.assertEquals(action.status, "rejected")

        # test resolve permissions
        action, result = self.client.ConsensusCondition.resolve()   # person without role cannot resolve
        self.assertEquals(action.status, "rejected")
        self.client.update_actor_on_all(self.users.midge)  # forward cannot resolve
        action, result = self.client.ConsensusCondition.resolve()
        self.assertEquals(action.status, "rejected")
        self.client.update_actor_on_all(self.users.jj)     # mid can resolve
        action, result = self.client.ConsensusCondition.resolve()
        self.assertEquals(action.status, "implemented")

    def test_cant_mispell_response(self):

        # add & trigger condition
        action, result = self.client.Conditional.add_condition(
            condition_type="consensuscondition", condition_data={"minimum_duration": 0, "is_strict": True},
            permission_data=self.permission_data)

        self.client.update_actor_on_all(self.users.midge)
        self.trigger_action, result = self.client.Community.change_name_of_community(name="United States Women's National Team")
        self.condition_item = self.client.Conditional.get_condition_items_for_action(action_pk=self.trigger_action.pk)[0]

        # update some but not all users
        self.client.update_target_on_all(self.condition_item)
        self.client.update_actor_on_all(self.users.rose)
        action, result = self.client.ConsensusCondition.respond(response="support w reservation")
        self.assertEquals(action.error_message,
            "Response must be one of support, support with reservations, stand aside, block, no response, not support w reservation")
        self.assertDictEqual(self.condition_item.get_responses(),
                          {"8": "no response", "2": "no response", "11": "no response", "12": "no response"})

    def test_can_override_previous_response(self):

        # add & trigger condition
        action, result = self.client.Conditional.add_condition(
            condition_type="consensuscondition", condition_data={"minimum_duration": 0},
            permission_data=self.permission_data)

        self.client.update_actor_on_all(self.users.midge)
        self.trigger_action, result = self.client.Community.change_name_of_community(name="United States Women's National Team")
        self.condition_item = self.client.Conditional.get_condition_items_for_action(action_pk=self.trigger_action.pk)[0]
        self.client.update_target_on_all(self.condition_item)

        # midge responds
        self.client.update_actor_on_all(self.users.midge)
        self.client.ConsensusCondition.respond(response="stand aside")
        self.assertDictEqual(self.condition_item.get_responses(),
                          {"8": "no response", "2": "no response", "11": "no response", "12": "stand aside"})

        # midge responds again
        self.client.update_actor_on_all(self.users.midge)
        self.client.ConsensusCondition.respond(response="support")
        self.assertDictEqual(self.condition_item.get_responses(),
                          {"8": "no response", "2": "no response", "11": "no response", "12": "support"})


class DefaultPermissionsTest(DataTestCase):

    def setUp(self):

        self.client = Client(actor=self.users.pinoe)

    def test_default_permissions(self):

        # test community
        self.instance = self.client.Community.create_community(name="USWNT")
        items = self.client.PermissionResource.get_permissions_on_object(target_object=self.instance)
        self.assertEquals(len(items), 3)
        self.assertCountEqual([item.change_type for item in items],
                              [Changes().Resources.AddComment, Changes().Actions.ApplyTemplate,
                               Changes().Communities.AddMembers])
        self.assertEquals([item.roles.role_list for item in items],
                          [["members"], ["members"], []])

        # # test simplelist defaults
        # self.client.update_target_on_all(self.instance)
        # action, list_instance = self.client.List.add_list(name="Awesome Players",
        #     configuration={"player name": {"required": True}, "team": {"required": False}},
        #     description="Our fave players")
        # items = self.client.PermissionResource.get_permissions_on_object(target_object=list_instance)
        # self.assertEquals(len(items), 6)
        # self.assertCountEqual(
        #     [item.change_type for item in items],
        #     [Changes().Resources.EditList, Changes().Resources.DeleteList, Changes().Resources.AddRow,
        #      Changes().Resources.EditRow, Changes().Resources.MoveRow, Changes().Resources.DeleteRow])


@skip
class FilterConditionTestOld(DataTestCase):

    def setUp(self):

        self.client = Client(actor=self.users.pinoe)
        self.instance = self.client.Community.create_community(name="USWNT")
        self.client.update_target_on_all(target=self.instance)

    def test_single_filter_condition(self):

        # create new user & add her to group; give her a permission
        self.users.kmew = User.objects.create(username="kristiemewis")
        self.client.Community.add_members_to_community(member_pk_list=[self.users.kmew.pk])
        action, target_permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Communities.ChangeName, roles=['members'])

        # add filter condition, user must have been created more than 1 second ago
        self.client.Conditional.set_target(target=target_permission)
        action, condition = self.client.Conditional.add_condition(condition_type="ActorUserCondition",
            condition_data={"duration":1})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

        # Kristie tries to change name and fails
        self.kristieClient = Client(actor=self.users.kmew)
        self.kristieClient.update_target_on_all(target=self.instance)
        action, result = self.kristieClient.Community.change_name_of_community(name="KMEW!!!")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")

        # wait 1 second
        time.sleep(1)

        # Kristie tries to change name and succeeds
        self.kristieClient = Client(actor=self.users.kmew)
        self.kristieClient.update_target_on_all(target=self.instance)
        action, result = self.kristieClient.Community.change_name_of_community(name="KMEW!!!")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

    def test_single_filter_condition_inverse(self):

        # create new user & add her to group; give her a permission
        self.users.kmew = User.objects.create(username="kristiemewis")
        self.client.Community.add_members_to_community(member_pk_list=[self.users.kmew.pk])
        action, target_permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Communities.ChangeName, roles=['members'])

        # add filter condition, user must have been created more than 1 second ago
        self.client.Conditional.set_target(target=target_permission)
        action, condition = self.client.Conditional.add_condition(condition_type="ActorUserCondition",
            condition_data={"duration":1, "inverse": True})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

        # Kristie tries to change name and fails
        self.kristieClient = Client(actor=self.users.kmew)
        self.kristieClient.update_target_on_all(target=self.instance)
        action, result = self.kristieClient.Community.change_name_of_community(name="KMEW!!!")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

        # wait 1 second
        time.sleep(1)

        # Kristie tries to change name and succeeds
        self.kristieClient = Client(actor=self.users.kmew)
        self.kristieClient.update_target_on_all(target=self.instance)
        action, result = self.kristieClient.Community.change_name_of_community(name="USWNT")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")

    def test_manager_form(self):

        action, target_permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Communities.ChangeName, roles=['members'])
        self.client.Conditional.set_target(target=target_permission)

        # add acceptance condition
        permission_data = [
            {"permission_type": Changes().Conditionals.Approve, "permission_actors": [self.users.pinoe.pk]}
        ]
        action, condition = self.client.Conditional.add_condition(
            condition_type="approvalcondition", permission_data=permission_data)

        # add filter condition, user must have been created more than 1 second ago
        action, condition = self.client.Conditional.add_condition(condition_type="ActorUserCondition",
            condition_data={"duration":1, "inverse": True}, mode="filter")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

        form_data = target_permission.get_condition_data()
        self.assertEquals(form_data.pop("how_to_pass_overall"),
            "individual 1 needs to approve this action, and actor has been user longer than 1 second")

        for key, value in form_data.items():
            if value["display_name"] == 'Actor has been user longer than':
                filter_field_dict = value["fields"]


        self.assertEquals(len(form_data), 2)
        self.assertEquals(filter_field_dict,
            {'duration': {'type': 'DurationField', 'required': True, 'value': 1, 'can_depend': False,
                          'display': 'Length of time that must pass', 'field_name': 'duration',
                          'label': 'Length of time that must pass', "default": None, 'full_name': None},
             'inverse': {'type': 'BooleanField', 'required': False, 'value': True, 'can_depend': False,
                          'display': 'Flip to inverse (actor has been user less than...)',
                          'label': 'Flip to inverse (actor has been user less than...)', "default": None,
                          'field_name': 'inverse', 'full_name': None}})


class PermissionClientTest(DataTestCase):

    def setUp(self):

        self.client = Client(actor=self.users.pinoe)
        self.community = self.client.Community.create_community(name="USWNT")
        self.client.update_target_on_all(target=self.community)
        self.client.Community.add_role_to_community(role_name="forwards")
        action, self.list = self.client.List.add_list(name="Awesome Players",
            configuration={"player name": {"required": True}, "team": {"required": False}},
            description="Our fave players")

    def add_permissions(self):

        # add permissions to group
        action, permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Communities.AddRole, roles=["forwards"])
        action, permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Communities.RemoveRole, roles=["forwards"])

        # add permissions targetting objects owned by group but set on group (aka nested)
        action, permission = self.client.PermissionResource.add_permission(
            change_type=Changes().Resources.EditList, roles=["forwards"])

        # add permissions directly to objects owned by group
        self.client.update_target_on_all(target=self.list)
        self.client.PermissionResource.add_permission(
            change_type=Changes().Resources.DeleteList, roles=["forwards"])

    def test_get_permissions_in_group(self):

        # check default permissions & generate our test permissions
        permissions = self.client.PermissionResource.get_all_permissions_in_community(community=self.community)
        self.assertEquals(len(permissions), 3)
        self.add_permissions()

        # we should now get 7 permissions, one of which is set on an object owned by the group, not the group
        self.client.update_target_on_all(target=self.community)
        permissions = self.client.PermissionResource.get_all_permissions_in_community(community=self.community)
        self.assertEquals(len(permissions), 7)
        list_permissions = [p for p in permissions if p.permitted_object == self.list]
        self.assertEquals(len(list_permissions), 1)

    def test_get_nested_permissions(self):

        # check default permissions
        permissions = self.client.PermissionResource.get_all_permissions_in_community(community=self.community)
        perm_names = [perm.change_type.split(".")[-1] for perm in permissions]
        self.assertCountEqual(perm_names, ['AddCommentStateChange', 'ApplyTemplateStateChange', 'AddMembersStateChange'])

        # generate our test permissions
        self.add_permissions()
        permissions = self.client.PermissionResource.get_all_permissions_in_community(community=self.community)
        perm_names = [perm.change_type.split(".")[-1] for perm in permissions]
        self.assertCountEqual(perm_names, ['AddCommentStateChange', 'ApplyTemplateStateChange', 'AddMembersStateChange',
            'DeleteListStateChange', 'AddRoleStateChange', 'RemoveRoleStateChange', 'EditListStateChange'])

        # now we test the get_nested_permissions call
        self.client.update_target_on_all(target=self.list)
        permissions = self.client.PermissionResource.get_nested_permissions(target=self.list, include_target=True)
        perm_names = [perm.change_type.split(".")[-1] for perm in permissions]

        # because target_type for AddComment is "action" we don't get it here, even though lists can be commented
        self.assertEquals(perm_names, ['ApplyTemplateStateChange', 'EditListStateChange', 'DeleteListStateChange'])

        # when we don't include target itself (just get nested), we lose DeleteList which is set on the list itself, not group
        permissions = self.client.PermissionResource.get_nested_permissions(target=self.list)
        perm_names = [perm.change_type.split(".")[-1] for perm in permissions]
        self.assertEquals(perm_names, ['ApplyTemplateStateChange', 'EditListStateChange'])


class FilterConditionTest(DataTestCase):

    def setUp(self):

        self.client = Client(actor=self.users.pinoe)

        # Create a community with roles
        self.instance = self.client.Community.create_community(name="USWNT")
        self.client.update_target_on_all(self.instance)
        self.client.Community.add_role_to_community(role_name="midfielders")
        self.client.Community.add_members_to_community(member_pk_list=[self.users.lindsey.pk, self.users.jj.pk,
            self.users.rose.pk, self.users.christen.pk])
        self.client.Community.add_people_to_role(
            role_name="midfielders", people_to_add=[self.users.lindsey.pk, self.users.jj.pk, self.users.rose.pk])

    def test_membership_filter_condition(self):

        # Pinoe creates a permission that says anyone may add members
        action, permission = self.client.PermissionResource.add_permission(change_type=Changes().Communities.AddMembers,
            anyone=True)

        # Then she adds a filter condition so that people can only add themselves
        self.client.update_target_on_all(target=permission)
        action, condition = self.client.Conditional.add_condition(condition_type="SelfMembershipFilter")

        # Midge, who is not in the group, is able to join
        self.client.update_target_on_all(target=self.instance)
        self.client.update_actor_on_all(actor=self.users.midge)
        action, result = self.client.Community.add_members_to_community(member_pk_list=[self.users.midge.pk])
        self.assertTrue(self.users.midge.pk in self.instance.roles.members)

        # Lindsey, who is in the group, is unable to add Sonny
        self.client.update_actor_on_all(actor=self.users.lindsey)
        action, result = self.client.Community.add_members_to_community(member_pk_list=[self.users.sonny.pk])
        self.assertFalse(self.users.sonny.pk in self.instance.roles.members)

        # Sonny is unable to add herself when she sends a request with another person too, but can do it alone
        self.client.update_actor_on_all(actor=self.users.sonny)
        action, result = self.client.Community.add_members_to_community(member_pk_list=[self.users.sonny.pk, self.users.aubrey.pk])
        self.assertFalse(self.users.sonny.pk in self.instance.roles.members)
        action, result = self.client.Community.add_members_to_community(member_pk_list=[self.users.sonny.pk])
        self.assertTrue(self.users.sonny.pk in self.instance.roles.members)

    def test_two_filters_work_together_on_add_comment(self):

        # Pinoe creates two permissions that says anyone may make a list and add a comment
        action, permission = self.client.PermissionResource.add_permission(change_type=Changes().Resources.AddList,
            anyone=True)
        action, permission = self.client.PermissionResource.add_permission(change_type=Changes().Resources.AddComment,
            anyone=True)

        # Then she adds a filter condition to the add comment permission so that they can only comment on actions
        self.client.update(target=permission)
        action, condition = self.client.Conditional.add_condition(condition_type="TargetTypeFilter",
            condition_data={"target_type": "simplelist"})

        # Midge can comment on lists
        self.client.update(target=self.instance, actor=self.users.midge)
        action, first_list = self.client.List.add_list(**self.list_resource_params)
        self.client.update(target=first_list)
        action, comment = self.client.Comment.add_comment(text="Weee a comment")
        self.assertEquals(action.status, "implemented")

        # But Midge cannot comment on actions
        self.client.Comment.target = action
        action, comment = self.client.Comment.add_comment(text="Weee a comment")
        self.assertEquals(action.status, "rejected")

        # Now Pinoe adds a filter that says only the original creator may comment
        self.client.update(target=permission, actor=self.users.pinoe)
        action, condition = self.client.Conditional.add_condition(
            condition_type="CreatorOfCommentedFilter")
        self.client.update(target=self.instance)
        action, second_list = self.client.List.add_list(**self.list_resource_params)

        # Midge can still comment on the list she made
        self.client.update(target=first_list, actor=self.users.midge)
        action, comment = self.client.Comment.add_comment(text="Weee a comment")
        self.assertEquals(action.status, "implemented")

        # But Midge cannot comment not the list Pinoe made
        self.client.update(target=second_list)
        action, comment = self.client.Comment.add_comment(text="Weee a comment")
        self.assertEquals(action.status, "rejected")


class DocumentTest(DataTestCase):

    def setUp(self):

        self.client = Client(actor=self.users.pinoe)

        # Create a community with roles
        self.instance = self.client.Community.create_community(name="USWNT")
        self.client.update_target_on_all(self.instance)
        self.client.Community.add_role_to_community(role_name="forwards")
        self.client.Community.add_members_to_community(member_pk_list=[self.users.tobin.pk, self.users.rose.pk])
        self.client.Community.add_people_to_role(role_name="forwards", people_to_add=[self.users.tobin.pk])

    def test_basic_document_functionality(self):

        # add a document
        self.assertEquals(len(self.client.Document.get_all_documents_given_owner(self.instance)), 0)
        action, doc = self.client.Document.add_document(name="What's Up Doc")
        self.assertEquals(len(self.client.Document.get_all_documents_given_owner(self.instance)), 1)
        self.assertEquals(doc.name, "What's Up Doc")
        self.assertEquals(doc.description, "")
        self.assertEquals(doc.content, "")

        # edit name & description, content remains the default ("")
        self.client.update_target_on_all(target=doc)
        action, doc = self.client.Document.edit_document(name="What's up, doc?", description="test document")
        self.assertEquals(len(self.client.Document.get_all_documents_given_owner(self.instance)), 1)
        self.assertEquals(doc.name, "What's up, doc?")
        self.assertEquals(doc.description, "test document")
        self.assertEquals(doc.content, "")

        # edit content, name and description remain what they were
        action, doc = self.client.Document.edit_document(content="some content")
        self.assertEquals(len(self.client.Document.get_all_documents_given_owner(self.instance)), 1)
        self.assertEquals(doc.name, "What's up, doc?")
        self.assertEquals(doc.description, "test document")
        self.assertEquals(doc.content, "some content")

        # edit nothing - invalid
        action, empty_result = self.client.Document.edit_document()
        self.assertEquals(action.error_message, "Must edit name, description or content")

        # delete
        pk = doc.pk
        action, deleted_pk = self.client.Document.delete_document()
        self.assertEquals(pk, deleted_pk)
        self.assertEquals(len(self.client.Document.get_all_documents_given_owner(self.instance)), 0)

