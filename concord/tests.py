import json
from decimal import Decimal
import time
from collections import namedtuple
from unittest import skip
from datetime import timedelta

from django.utils import timezone
from django.test import TestCase
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

from concord.resources.client import ResourceClient, CommentClient
from concord.permission_resources.client import PermissionResourceClient
from concord.conditionals.client import (ApprovalConditionClient, VoteConditionClient, 
    ConditionalClient)
from concord.communities.client import CommunityClient
from concord.actions.client import ActionClient, TemplateClient

from concord.communities.forms import RoleForm
from concord.permission_resources.forms import PermissionForm, MetaPermissionForm
from concord.conditionals.forms import ConditionSelectionForm, conditionFormDict
from concord.actions.models import Action  # NOTE: For testing action status later, do we want a client?
from concord.actions.state_changes import Changes
from concord.permission_resources.models import PermissionsItem
from concord.conditionals.models import ApprovalCondition
from concord.resources.models import Resource, Item
from concord.actions import template_library


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
        self.users.hao = User.objects.create(username="heatheroreilly")

    def display_last_actions(self, number=10):
        """Helper method which shows the last N actions to be created, useful for debugging."""
        actions = Action.objects.all().order_by('-id')[:number]
        for action in reversed(actions):
            print(action)


class ResourceModelTests(DataTestCase):

    def setUp(self):
        self.rc = ResourceClient(actor=self.users.pinoe)

    def test_create_resource(self):
        """
        Test creation of simple resource through client, and its method
        get_unique_id.
        """
        resource = self.rc.create_resource(name="Go USWNT!")
        self.assertEquals(resource.get_unique_id(), "resources_resource_1")

    def test_add_item_to_resource(self):
        """
        Test creation of item and addition to resource.
        """
        resource = self.rc.create_resource(name="Go USWNT!")
        self.rc.set_target(target=resource)
        action, item = self.rc.add_item(item_name="Equal Pay")
        self.assertEquals(item.get_unique_id(), "resources_item_1")

    def test_remove_item_from_resource(self):
        """
        Test removal of item from resource.
        """
        resource = self.rc.create_resource(name="Go USWNT!")
        self.rc.set_target(target=resource)
        action, item = self.rc.add_item(item_name="Equal Pay")
        self.assertEquals(resource.get_items(), ["Equal Pay"])
        self.rc.remove_item(item_pk=item.pk)
        self.assertEquals(resource.get_items(), [])


class PermissionResourceModelTests(DataTestCase):

    def setUp(self):
        self.rc = ResourceClient(actor=self.users.pinoe)
        self.prc = PermissionResourceClient(actor=self.users.pinoe)

    def test_add_permission_to_resource(self):
        """
        Test addition of permisssion to resource.
        """
        resource = self.rc.create_resource(name="Go USWNT!")
        self.prc.set_target(target=resource)
        action, permission = self.prc.add_permission(
            permission_type=Changes.Resources.AddItem,
            permission_actors=[self.users.pinoe.pk])
        items = self.prc.get_permissions_on_object(object=resource)
        self.assertEquals(items.first().get_name(), 'Permission 1 (for concord.resources.state_changes.AddItemResourceStateChange on Resource object (1))')

    def test_remove_permission_from_resource(self):
        """
        Test removal of permission from resource.
        """
        resource = self.rc.create_resource(name="Go USWNT!")
        self.prc.set_target(target=resource)
        action, permission = self.prc.add_permission(
            permission_type=Changes.Resources.AddItem,
            permission_actors=[self.users.pinoe.pk])
        items = self.prc.get_permissions_on_object(object=resource)
        self.assertEquals(items.first().get_name(), 'Permission 1 (for concord.resources.state_changes.AddItemResourceStateChange on Resource object (1))')
        self.prc.remove_permission(item_pk=permission.pk)
        items = self.prc.get_permissions_on_object(object=resource)
        self.assertEquals(list(items), [])


class PermissionSystemTest(DataTestCase):
    """
    The previous two sets of tests use the default permissions setting for the items
    they're modifying.  For individually owned objects, this means that the owner can do 
    whatever they want and no one else can do anything.  This set of tests looks at the basic 
    functioning of the permissions system including permissions set on permissions.
    """

    def setUp(self):
        self.rc = ResourceClient(actor=self.users.pinoe)
        self.prc = PermissionResourceClient(actor=self.users.pinoe)

    def test_permissions_system(self):
        """
        Create a resource and add a specific permission for a non-owner actor.
        """
        resource = self.rc.create_resource(name="Go USWNT!")
        self.prc.set_target(target=resource)
        action, permission = self.prc.add_permission(
            permission_type=Changes.Resources.AddItem,
            permission_actors=[self.users.rose.pk])
        items = self.prc.get_permissions_on_object(object=resource)
        self.assertEquals(items.first().get_name(), 
            'Permission 1 (for concord.resources.state_changes.AddItemResourceStateChange on Resource object (1))')

        # Now the non-owner actor (Rose) takes the permitted action on the resource
        rose_rc = ResourceClient(actor=self.users.rose, target=resource)
        action, item = rose_rc.add_item(item_name="Test New")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(item.name, "Test New")

    def test_recursive_permission(self):
        """
        Tests setting permissions on permission.
        """

        # Pinoe creates a resource and adds a permission for Rose to the resource.
        resource = self.rc.create_resource(name="Go USWNT!")
        self.prc.set_target(target=resource)
        action, permission = self.prc.add_permission(permission_type=Changes.Resources.AddItem,
            permission_actors=[self.users.rose.pk])

        # Tobin can't add an item to this resource because she's not the owner nor specified in
        # the permission.
        tobin_rc = ResourceClient(actor=self.users.tobin, target=resource)
        action, item = tobin_rc.add_item(item_name="Tobin's item")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")

        # Pinoe adds a permission on the permission which Tobin does have.
        self.prc.set_target(target=permission)
        action, rec_permission = self.prc.add_permission(permission_type=Changes.Permissions.AddPermission,
            permission_actors=[self.users.tobin.pk])
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

        # Tobin still cannot make the original change because she does not have *that* permission.
        action, item = tobin_rc.add_item(item_name="Tobin's item")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        
        # But Tobin CAN make the second-level change.
        tobin_prc = PermissionResourceClient(actor=self.users.tobin, target=permission)
        action, permission = tobin_prc.add_permission(permission_type=Changes.Permissions.AddPermission,
            permission_actors=[self.users.rose.pk])        
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

    def test_multiple_specific_permission(self):
        """Tests that when multiple permissions are set, they're handled in an OR fashion."""

        # Pinoe creates a resource and adds a permission to the resource.
        resource = self.rc.create_resource(name="Go USWNT!")
        self.prc.set_target(target=resource)
        action, permission = self.prc.add_permission(permission_type=Changes.Resources.AddItem,
            permission_actors=[self.users.christen.pk])

        # Then she adds another permission with different actors/roles.
        action, permission = self.prc.add_permission(permission_type=Changes.Resources.AddItem,
            permission_actors=[self.users.tobin.pk])

        # Both of the actors specified can do the thing.

        christen_rc = ResourceClient(actor=self.users.christen, target=resource)
        action, item = christen_rc.add_item(item_name="Christen Test")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(item.name, "Christen Test")  

        tobin_rc = ResourceClient(actor=self.users.tobin, target=resource)
        action, item = tobin_rc.add_item(item_name="Tobin Test")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(item.name, "Tobin Test")

    def test_multiple_specific_permission_with_conditions(self):
        """test multiple specific permissions with conditionals"""
        
        # Pinoe creates a resource and adds a permission to the resource.
        resource = self.rc.create_resource(name="Go USWNT!")
        self.prc.set_target(target=resource)
        action, permission = self.prc.add_permission(permission_type=Changes.Resources.AddItem,
            permission_actors=[self.users.christen.pk])

        # Then she adds another permission with different actors/roles.
        action, permission = self.prc.add_permission(permission_type=Changes.Resources.AddItem,
            permission_actors=[self.users.tobin.pk])

        # Then she adds a condition to the second one
        permission_data = [
            { "permission_type": Changes.Conditionals.Approve, "permission_actors": [self.users.pinoe.pk]}
        ]
        action, condition = self.prc.add_condition_to_permission(permission_pk=permission.pk,
            condition_type="approvalcondition", condition_data=None, permission_data=permission_data)

        # The first (Christen) is accepted while the second (Tobin) has to wait

        christen_rc = ResourceClient(actor=self.users.christen, target=resource)
        action, item = christen_rc.add_item(item_name="Christen Test")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(item.name, "Christen Test")  

        tobin_rc = ResourceClient(actor=self.users.tobin, target=resource)
        action, item = tobin_rc.add_item(item_name="Tobin Test")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "waiting")
        self.assertEquals(item, None)

    def test_inverse_permission(self):
        """Tests that when inverse toggle is flipped, permissions match appropriately."""

        # Pinoe creates a resource and adds a permission to the resource.
        resource = self.rc.create_resource(name="Go USWNT!")
        self.prc.set_target(target=resource)
        action, permission = self.prc.add_permission(permission_type=Changes.Resources.AddItem,
            permission_actors=[self.users.jj.pk])

        # JJ can use the permission
        jj_rc = ResourceClient(actor=self.users.jj, target=resource)
        action, item = jj_rc.add_item(item_name="JJ Ertz's Test")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(item.name, "JJ Ertz's Test")  

        # Pinoe toggles the permission
        action, result = self.prc.change_inverse_field_of_permission(change_to=True, 
            permission_pk=permission.pk)
        permission.refresh_from_db()
        self.assertEquals(permission.inverse, True)

        # JJ can no longer use the permission, but anyone who is not JJ can

        action, item = jj_rc.add_item(item_name="JJ Test #2")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(item, None) 

        tobin_rc = ResourceClient(actor=self.users.tobin, target=resource)
        action, item = tobin_rc.add_item(item_name="Tobin Test")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(item.name, "Tobin Test")

    def test_nested_object_permission_no_conditions(self):

        # Pinoe creates a group, then a resource, then transfers ownership of resource to group
        self.commClient = CommunityClient(actor=self.users.pinoe)
        self.instance = self.commClient.create_community(name="USWNT")
        self.commClient.set_target(self.instance)
        resource = self.rc.create_resource(name="Go USWNT!")
        self.rc.set_target(resource)
        self.rc.change_owner_of_target(self.instance)

        # She sets a permission on the resource and it works, blocking Tobin from adding an item
        self.prc.set_target(target=resource)
        action, permission = self.prc.add_permission(permission_type=Changes.Resources.AddItem,
            permission_actors=[self.users.christen.pk])
        tobin_rc = ResourceClient(actor=self.users.tobin, target=resource)
        action, item = tobin_rc.add_item(item_name="Tobin Test")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(item, None)

        # She sets a permission on the group that does let Tobin add item, now it works
        self.prc.set_target(target=self.instance)
        action, permission = self.prc.add_permission(permission_type=Changes.Resources.AddItem,
            permission_actors=[self.users.tobin.pk])
        
        tobin_rc = ResourceClient(actor=self.users.tobin, target=resource)
        action, item = tobin_rc.add_item(item_name="Tobin Test")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

    def test_nested_object_permission_with_conditions(self):
        
        # Pinoe creates a group, then a resource, then transfers ownership of resource to group
        self.commClient = CommunityClient(actor=self.users.pinoe)
        self.instance = self.commClient.create_community(name="USWNT")
        self.commClient.set_target(self.instance)
        resource = self.rc.create_resource(name="Go USWNT!")
        self.rc.set_target(resource)
        self.rc.change_owner_of_target(self.instance)

        # She sets permissions on the resource and on the group, both of which let Tobin add an item
        self.prc.set_target(target=resource)
        action, resource_permission = self.prc.add_permission(permission_type=Changes.Resources.AddItem,
            permission_actors=[self.users.tobin.pk])
        self.prc.set_target(target=self.instance)
        action, group_permission = self.prc.add_permission(permission_type=Changes.Resources.AddItem,
            permission_actors=[self.users.tobin.pk])

        # She adds a condition to the one on the resource
        permission_data = [{ "permission_type": Changes.Conditionals.Approve, "permission_actors": [self.users.crystal.pk]}]
        action, result = self.prc.add_condition_to_permission(permission_pk=resource_permission.pk, 
            condition_type="approvalcondition", permission_data=permission_data, condition_data=None)

        # Tobin adds an item and it works without setting off the conditional
        tobin_rc = ResourceClient(actor=self.users.tobin, target=resource)
        action, item = tobin_rc.add_item(item_name="Tobin Test")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

        # She adds a condition to the group, now Tobin has to wait
        permission_data = [{ "permission_type": Changes.Conditionals.Approve, "permission_actors": [self.users.crystal.pk]}]
        action, result = self.prc.add_condition_to_permission(permission_pk=group_permission.pk, 
            condition_type="approvalcondition", permission_data=permission_data, condition_data=None)
        action, item = tobin_rc.add_item(item_name="Tobin Test 2")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "waiting")

    def test_anyone_permission_toggle(self):

        # Create a group with members, give members permission to change the group name
        self.commClient = CommunityClient(actor=self.users.pinoe)
        self.instance = self.commClient.create_community(name="USWNT")
        self.commClient.set_target(self.instance)
        self.commClient.add_members([self.users.rose.pk, self.users.crystal.pk,
            self.users.tobin.pk])
        self.prc = PermissionResourceClient(actor=self.users.pinoe, target=self.instance)
        action, result = self.prc.add_permission(permission_type=Changes.Communities.ChangeName,
            permission_roles=['members'])
        self.target_permission = result

        # Test someone in the group can do the thing
        self.commClient = CommunityClient(actor=self.users.rose, target=self.instance)
        action, result = self.commClient.change_name(new_name="USWNT!!!!")
        self.assertEquals(action.status, "implemented")
        self.assertEquals(self.instance.name, "USWNT!!!!")

        # Test that our user, Sonny, who is not in the group, can't do the thing
        self.commClient = CommunityClient(actor=self.users.sonny, target=self.instance)
        action, result = self.commClient.change_name(new_name="USWNT????")
        self.assertEquals(action.status, "rejected")
        self.assertEquals(self.instance.name, "USWNT!!!!")

        # Now we give that permission to "anyone"
        action, result = self.prc.give_anyone_permission(permission_pk=self.target_permission.pk)

        # Our non-member can do the thing now!
        action, result = self.commClient.change_name(new_name="USWNT????")
        self.assertEquals(action.status, "implemented")
        self.assertEquals(self.instance.name, "USWNT????")

        # Let's toggle anyone back to disabled
        action, result = self.prc.remove_anyone_from_permission(permission_pk=self.target_permission.pk)
        
        # Once again our non-member can no longer do the thing
        action, result = self.commClient.change_name(new_name="USWNT :D :D :D")
        self.assertEquals(action.status, "rejected")
        self.assertEquals(self.instance.name, "USWNT????")

    def test_condition_form_generation(self):

         # Pinoe creates a resource and adds a permission to the resource and a condition to the permission.
        resource = self.rc.create_resource(name="Go USWNT!")
        self.prc.set_target(target=resource)
        action, permission = self.prc.add_permission(permission_type=Changes.Resources.AddItem,
            permission_actors=[self.users.tobin.pk])
        permission_data = [
            { "permission_type": Changes.Conditionals.Approve, "permission_actors": [self.users.pinoe.pk]}
        ]
        action, condition = self.prc.add_condition_to_permission(permission_pk=permission.pk,
            condition_type="approvalcondition", condition_data=None, permission_data=permission_data)

        permission = PermissionsItem.objects.get(pk=permission.pk) #refresh
        self.assertEquals(permission.get_condition_data(info="basic"),
            {'type': 'ApprovalCondition', 'display_name': 'Approval Condition', 
            'how_to_pass': 'one person needs to approve this action'})
        self.assertEquals(permission.get_condition_data(info="fields"), 
            {'self_approval_allowed': 
                {'display': 'Can individuals approve their own actions?', 'field_name': 'self_approval_allowed', 
                'type': 'BooleanField', 'required': '', 'value': False}, 
            'approve_roles': 
                {'display': 'Roles who can approve', 'type': 'PermissionRoleField', 'required': False, 
                'value': None, 'field_name': 'approve_roles', 'full_name': 'concord.conditionals.state_changes.ApproveStateChange'}, 
            'approve_actors': 
                {'display': 'People who can approve', 'type': 'PermissionActorField', 'required': False, 'value': [1], 
                'field_name': 'approve_actors', 'full_name': 'concord.conditionals.state_changes.ApproveStateChange'}, 
            'reject_roles': 
                {'display': 'Roles who can reject', 'type': 'PermissionRoleField', 'required': False, 'value': None, 
                'field_name': 'reject_roles', 'full_name': 'concord.conditionals.state_changes.RejectStateChange'}, 
            'reject_actors': 
                {'display': 'People who can reject', 'type': 'PermissionActorField', 'required': False, 'value': None, 
                'field_name': 'reject_actors', 'full_name': 'concord.conditionals.state_changes.RejectStateChange'}})
 

class ConditionSystemTest(DataTestCase):

    def test_add_permission_to_condition_state_change(self):
        from concord.permission_resources.state_changes import AddPermissionConditionStateChange
        from concord.permission_resources.state_changes import PermissionsItem
        permission = PermissionsItem()
        permission_data = [{ "permission_type": Changes.Conditionals.AddVote, 
            "permission_actors": [self.users.crystal.pk, self.users.jmac.pk] }]
        change = AddPermissionConditionStateChange(permission_pk=1, condition_type="votecondition", condition_data=None,
            permission_data=permission_data)
        mock_actions = change.generate_mock_actions(actor=self.users.pinoe, permission=permission)
        self.assertEquals(len(mock_actions), 2)
        self.assertEquals(mock_actions[0].change.get_change_type(), Changes.Conditionals.AddConditionToAction)
        self.assertEquals(mock_actions[1].change.get_change_type(), Changes.Permissions.AddPermission)     
        self.assertEquals(mock_actions[0].target, "{{trigger_action}}")  
        self.assertEquals(mock_actions[1].change.permission_actors, [self.users.crystal.pk, self.users.jmac.pk])

    def test_add_leadership_condition_state_change(self):
        from concord.communities.state_changes import AddLeadershipConditionStateChange
        community = CommunityClient(actor=self.users.pinoe).create_community(name="Test community")
        permission_data = [{ "permission_type": Changes.Conditionals.Approve, "permission_roles": ["members"] }]
        change = AddLeadershipConditionStateChange(condition_type="approvalcondition", condition_data=None, 
            permission_data=permission_data, leadership_type="governor")
        mock_actions = change.generate_mock_actions(actor=self.users.pinoe, target=community)
        self.assertEquals(len(mock_actions), 2)
        self.assertEquals(mock_actions[0].change.get_change_type(), Changes.Conditionals.AddConditionToAction)
        self.assertEquals(mock_actions[1].change.get_change_type(), Changes.Permissions.AddPermission)        
        self.assertEquals(mock_actions[0].target, "{{trigger_action}}")  
        self.assertEquals(mock_actions[1].change.permission_roles, ["members"])

    def test_condition_template_text_util_with_vote_condition(self):
        from concord.actions.text_utils import condition_template_to_text
        from concord.permission_resources.state_changes import AddPermissionConditionStateChange
        from concord.permission_resources.state_changes import PermissionsItem
        permission = PermissionsItem()
        permission_data = [{ "permission_type": Changes.Conditionals.AddVote, 
            "permission_actors": [self.users.crystal.pk, self.users.jmac.pk] }]
        change = AddPermissionConditionStateChange(permission_pk=1, condition_type="votecondition", condition_data=None,
            permission_data=permission_data)
        mock_actions = change.generate_mock_actions(actor=self.users.pinoe, permission=permission)
        text = condition_template_to_text(mock_actions[0], mock_actions[1:])
        self.assertEquals(text, "on the condition that individuals 5 and 6 vote")

    def test_condition_template_text_util_with_approval_condition(self):
        from concord.actions.text_utils import condition_template_to_text
        from concord.communities.state_changes import AddLeadershipConditionStateChange
        community = CommunityClient(actor=self.users.pinoe).create_community(name="Test community")
        permission_data = [{ "permission_type": Changes.Conditionals.Approve, "permission_roles": ["members"] },
            { "permission_type": Changes.Conditionals.Reject, "permission_actors": [self.users.crystal.pk]}]
        change = AddLeadershipConditionStateChange(condition_type="approvalcondition", condition_data=None, 
            permission_data=permission_data, leadership_type="governor")
        mock_actions = change.generate_mock_actions(actor=self.users.pinoe, target=community)
        text = condition_template_to_text(mock_actions[0], mock_actions[1:])
        self.assertEquals(text, "on the condition that everyone with role members approve and individual 5 does not reject")


class ConditionalsTest(DataTestCase):

    def setUp(self):
        self.cc = ConditionalClient(actor=self.users.pinoe)
        self.rc = ResourceClient(actor=self.users.pinoe)
        self.prc = PermissionResourceClient(actor=self.users.pinoe)
        self.target = self.rc.create_resource(name="Go USWNT!")
        from concord.resources.state_changes import ChangeResourceNameStateChange
        self.action = Action.objects.create(actor=self.users.sully, target=self.target,
            change=ChangeResourceNameStateChange(new_name="Go Spirit!"))
    
    def test_vote_conditional(self):

        # First Pinoe creates a resource
        resource = self.rc.create_resource(name="Go USWNT!")

        # Then she adds a permission that says that Rose can add items.
        self.prc.set_target(target=resource)
        action, permission = self.prc.add_permission(permission_type=Changes.Resources.AddItem,
            permission_actors=[self.users.rose.pk])
        
        # But she places a vote condition on the permission
        permission_data = [{ "permission_type": Changes.Conditionals.AddVote, 
            "permission_actors": [self.users.jmac.pk, self.users.crystal.pk] }]
        self.prc.add_condition_to_permission(permission_pk=permission.pk, condition_type="votecondition", 
            permission_data=permission_data)

        # Rose tries to add an item, triggering the condition
        self.rc.set_actor(actor=self.users.rose)
        self.rc.set_target(target=resource)
        action, result = self.rc.add_item(item_name="Rose's item")

        # We get the vote condition
        self.cc = ConditionalClient(actor=self.users.crystal)
        item = self.cc.get_condition_item_given_action_and_source(action_pk=action.pk, 
            source_id="perm_"+str(permission.pk))
        vote_condition = self.cc.get_vote_condition_as_client(pk=item.pk)

        # Now Crystal and JMac can vote but Rose can't

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

        # First Pinoe creates a resource
        resource = self.rc.create_resource(name="Go USWNT!")

        # Then she adds a permission that says that Rose can add items.
        self.prc.set_target(target=resource)
        action, permission = self.prc.add_permission(permission_type=Changes.Resources.AddItem,
            permission_actors=[self.users.rose.pk])
        
        # But she places a condition on the permission that Rose has to get
        # approval (without specifying permissions, so it uses the default governing/foundational.
        self.prc.add_condition_to_permission(permission_pk=permission.pk, condition_type="approvalcondition")

        # Now when Sonny tries to add an item she is flat out rejected
        self.rc.set_actor(actor=self.users.sonny)
        self.rc.set_target(target=resource)
        action, item = self.rc.add_item(item_name="Saucy Sonny's item")
        self.assertEquals(resource.get_items(), [])
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")

        # When Rose tries to add an item it is stuck waiting
        self.rc.set_actor(actor=self.users.rose)
        rose_action, item = self.rc.add_item(item_name="Rose's item")
        self.assertEquals(resource.get_items(), [])
        self.assertEquals(Action.objects.get(pk=rose_action.pk).status, "waiting")

        # Get the conditional action
        conditional_action = self.cc.get_condition_item_given_action_and_source(action_pk=rose_action.pk,
            source_id="perm_"+str(permission.pk))

        # Sonny tries to approve it and fails.  Sonny you goof.
        acc = ApprovalConditionClient(target=conditional_action, actor=self.users.sonny)
        action, result = acc.approve()
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(resource.get_items(), [])

        # Now Pinoe approves it
        acc.set_actor(actor=self.users.pinoe)
        action, result = acc.approve()
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
    
        # And Rose's item has been added
        self.assertEquals(Action.objects.get(pk=rose_action.pk).status, "implemented")
        self.assertEquals(resource.get_items(), ["Rose's item"])

    def test_add_and_remove_condition_on_permission(self):

        # Pinoe creates a resource and sets a permission and a condition on the permission
        resource = self.rc.create_resource(name="Go USWNT!")
        self.prc.set_target(target=resource)
        action, permission = self.prc.add_permission(permission_type=Changes.Resources.AddItem,
            permission_actors=[self.users.rose.pk])
        permission_data = [{ "permission_type": Changes.Conditionals.Approve, 
            "permission_actors" : [self.users.crystal.pk]}]
        self.prc.add_condition_to_permission(permission_pk=permission.pk, condition_type="approvalcondition", 
            permission_data=permission_data)

        # When Rose tries to add an item it is stuck waiting
        self.rc.set_actor(actor=self.users.rose)
        self.rc.set_target(target=resource)
        rose_action, item = self.rc.add_item(item_name="Rose's item")
        self.assertEquals(Action.objects.get(pk=rose_action.pk).status, "waiting")

        # Now Pinoe removes it
        self.prc.remove_condition_from_permission(permission_pk=permission.pk)

        # When Rose tries again, it passes
        self.rc.set_actor(actor=self.users.rose)
        self.rc.set_target(target=resource)
        rose_action, item = self.rc.add_item(item_name="Rose's item")
        self.assertEquals(Action.objects.get(pk=rose_action.pk).status, "implemented")
        
    def test_approval_conditional_with_second_order_permission(self):
        """
        Mostly the same as above, but instead of using the default permission on
        the conditional action, we specify that someone specific has to approve
        the action.
        """

        # First we have Pinoe create a resource
        resource = self.rc.create_resource(name="Go USWNT!")

        # Then she adds a permission that says that Rose can add items.
        self.prc.set_target(target=resource)
        action, permission = self.prc.add_permission(permission_type=Changes.Resources.AddItem,
            permission_actors=[self.users.rose.pk])
        
        # But she places a condition on the permission that Rose has to get
        # approval.  She specifies that *Crystal* has to approve it.
        permission_data = [{ "permission_type": Changes.Conditionals.Approve, 
            "permission_actors" : [self.users.crystal.pk]}]
        self.prc.add_condition_to_permission(permission_pk=permission.pk, condition_type="approvalcondition", 
            permission_data=permission_data)

        # When Rose tries to add an item it is stuck waiting
        self.rc.set_actor(actor=self.users.rose)
        self.rc.set_target(target=resource)
        rose_action, item = self.rc.add_item(item_name="Rose's item")
        self.assertEquals(resource.get_items(), [])
        self.assertEquals(Action.objects.get(pk=rose_action.pk).status, "waiting")

        # Get the conditional action
        conditional_action = self.cc.get_condition_item_given_action_and_source(action_pk=rose_action.pk,
            source_id="perm_"+ str(permission.pk))

       # Now Crystal approves it
        acc = ApprovalConditionClient(target=conditional_action, actor=self.users.crystal)
        action, result = acc.approve()
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
    
        # And Rose's item has been added
        self.assertEquals(Action.objects.get(pk=rose_action.pk).status, "implemented")
        self.assertEquals(resource.get_items(), ["Rose's item"])

    def test_multiple_permissions_on_condition(self):

        # First we have Pinoe create a resource
        resource = self.rc.create_resource(name="Go USWNT!")

        # Then she adds a permission that says that Rose can add items.
        self.prc.set_target(target=resource)
        action, permission = self.prc.add_permission(permission_type=Changes.Resources.AddItem,
            permission_actors=[self.users.rose.pk])
        
        # But she places a condition on the permission that Rose has to get
        # approval.  She specifies that *Crystal* has to approve it.  She also 
        # specifies that Andi Sullivan can reject it.
        permission_data = [
            { "permission_type": Changes.Conditionals.Approve, "permission_actors": [self.users.crystal.pk] },
            { "permission_type": Changes.Conditionals.Reject, "permission_actors": [self.users.sully.pk] }
        ]
        action, result = self.prc.add_condition_to_permission(permission_pk=permission.pk, condition_type="approvalcondition", 
            permission_data=permission_data)

        # When Rose tries to add an item, Crystal can approve it
        self.rc.set_actor(actor=self.users.rose)
        self.rc.set_target(target=resource)
        rose_action_one, item = self.rc.add_item(item_name="Rose's first item")
        conditional_action = self.cc.get_condition_item_given_action_and_source(action_pk=rose_action_one.pk,
            source_id="perm_"+str(permission.pk))
        acc = ApprovalConditionClient(target=conditional_action, actor=self.users.crystal)
        action, result = acc.approve()
    
        # When Rose tries to add an item, Andi Sullivan can reject it
        rose_action_two, item = self.rc.add_item(item_name="Rose's second item")
        conditional_action = self.cc.get_condition_item_given_action_and_source(action_pk=rose_action_two.pk,
            source_id="perm_"+str(permission.pk))
        acc = ApprovalConditionClient(target=conditional_action, actor=self.users.sully)
        action, result = acc.reject()

        # We see Rose's first item but not her second has been added
        self.assertEquals(Action.objects.get(pk=rose_action_one.pk).status, "implemented")
        self.assertEquals(Action.objects.get(pk=rose_action_two.pk).status, "rejected")
        self.assertEquals(resource.get_items(), ["Rose's first item"])

        # Rose tries one more time - Andi can't approve and Crystal can't reject, so the action is waiting
        rose_action_three, item = self.rc.add_item(item_name="Rose's third item")        
        conditional_action = self.cc.get_condition_item_given_action_and_source(action_pk=rose_action_three.pk,
            source_id="perm_"+str(permission.pk))
        acc = ApprovalConditionClient(target=conditional_action, actor=self.users.crystal)
        action, result = acc.reject()
        acc = ApprovalConditionClient(target=conditional_action, actor=self.users.sully)
        action, result = acc.approve()
        self.assertEquals(Action.objects.get(pk=rose_action_three.pk).status, "waiting")


@skip("Skipping forms for now")
class ConditionalsFormTest(DataTestCase):
    
    def setUp(self):

        # Create a community
        self.commClient = CommunityClient(actor=self.users.pinoe)
        self.instance = self.commClient.create_community(name="USWNT")
        self.commClient.set_target(self.instance)
        self.commClient.add_members([self.users.rose.pk, self.users.crystal.pk,
            self.users.tobin.pk])

        # Make separate clients 
        self.roseClient = CommunityClient(actor=self.users.rose, target=self.instance)
        self.crystalClient = CommunityClient(actor=self.users.crystal, target=self.instance)
        self.tobinClient = CommunityClient(actor=self.users.tobin, target=self.instance)

        # Create request objects
        Request = namedtuple('Request', 'user')
        self.request = Request(user=self.users.pinoe)
        self.roseRequest = Request(user=self.users.rose)  
        self.crystalRequest = Request(user=self.users.crystal)
        self.tobinRequest = Request(user=self.users.tobin)

        # Create a permission to set a condition on 
        self.prc = PermissionResourceClient(actor=self.users.pinoe, target=self.instance)
        action, result = self.prc.add_permission(permission_type=Changes.Resources.ChangeResourceName,
            permission_actors=[self.users.rose.pk])
        self.target_permission = result

        # Create ConditionalClient
        self.pcc = ConditionalClient(actor=self.users.pinoe, target=self.target_permission)

        # Create permissions data for response dict
        self.response_dict = {}
        self.prClient = PermissionResourceClient(actor=self.users.pinoe, target=ApprovalCondition)
        permissions = self.prClient.get_settable_permissions(return_format="permission_objects")
        for count, permission in enumerate(permissions):
            self.response_dict[str(count) + "~" + "name"] = permission.get_change_type()
            self.response_dict[str(count) + "~" + "roles"] = []
            self.response_dict[str(count) + "~" + "individuals"] = []
            for field in permission.get_configurable_fields():
                self.response_dict['%s~configurablefield~%s' % (count, field)] = ""

        # Create a resource client
        self.rc = ResourceClient(actor=self.users.pinoe)

    def test_conditional_selection_form_init(self):
        csForm = ConditionSelectionForm(instance=self.instance, request=self.request)
        choices = [choice[0] for choice in csForm.fields["condition"].choices]
        self.assertEquals(choices, ["approvalcondition", "votecondition"])

    def test_conditional_selection_form_get_condition_choice_method(self):
        response_data = { 'condition': ["approvalcondition"] }
        csForm = ConditionSelectionForm(instance=self.instance, request=self.request, data=response_data)
        csForm.is_valid()
        self.assertEquals(csForm.get_condition_choice(), "approvalcondition")
        response_data = { 'condition': ["votecondition"] }
        csForm = ConditionSelectionForm(instance=self.instance, request=self.request, data=response_data)
        csForm.is_valid()
        self.assertEquals(csForm.get_condition_choice(), "votecondition")

    def test_approval_condition_form_lets_you_create_condition(self):
        
        # We start off with no templates on our target permission
        result = self.pcc.get_condition_template()
        self.assertEquals(result, None)

        # We create and save an ApprovalForm
        ApprovalForm = conditionFormDict["approvalcondition"]
        response_data = {'self_approval_allowed': True}
        approvalForm = ApprovalForm(permission=self.target_permission, request=self.request, 
            data=response_data)
        approvalForm.is_valid()
        approvalForm.save()

        # Now a condition template exists, with our configuration
        result = self.pcc.get_condition_template()
        self.assertEquals(result.condition_data, '{"self_approval_allowed": true}')

    def test_approval_form_displays_inital_data_in_edit_mode(self):

        # Create condition template
        ApprovalForm = conditionFormDict["approvalcondition"]
        response_data = {'self_approval_allowed': True}
        approvalForm = ApprovalForm(permission=self.target_permission, request=self.request, 
            data=response_data)
        approvalForm.is_valid()
        approvalForm.save()
        condTemplate = self.pcc.get_condition_template()

        # Feed into form
        approvalForm = ApprovalForm(instance=condTemplate, permission=self.target_permission, 
            request=self.request)
        self.assertEquals(approvalForm.fields['self_approval_allowed'].initial, True)

    def test_approval_condition_form_lets_you_edit_condition(self):
        
        # Create condition template
        ApprovalForm = conditionFormDict["approvalcondition"]
        response_data = {'self_approval_allowed': True}
        approvalForm = ApprovalForm(permission=self.target_permission, request=self.request, 
            data=response_data)
        approvalForm.is_valid()
        approvalForm.save()
        condTemplate = self.pcc.get_condition_template()
        self.assertEquals(condTemplate.condition_data, '{"self_approval_allowed": true}')

        # Feed into form as instance along with edited data
        response_data2 = {'self_approval_allowed': False}
        approvalForm2 = ApprovalForm(instance=condTemplate, permission=self.target_permission, 
            request=self.request, data=response_data2)
        approvalForm2.is_valid()
        approvalForm2.save()

        # Now configuration is different
        condTemplate = self.pcc.get_condition_template()
        self.assertEquals(condTemplate.condition_data, '{"self_approval_allowed": false}')

    def test_vote_condition_form_lets_you_create_condition(self):

        # We start off with no templates on our target permission
        result = self.pcc.get_condition_template()
        self.assertEquals(result, None)

        # We create and save an VoteForm
        VoteForm = conditionFormDict["votecondition"]
        response_data = {'allow_abstain': False, 'require_majority': True, 
            'publicize_votes': False, 'voting_period': '5'}
        voteForm = VoteForm(permission=self.target_permission, request=self.request, 
            data=response_data)
        voteForm.is_valid()
        voteForm.save()

        # Now a condition template exists, with our configuration
        result = self.pcc.get_condition_template()
        self.assertEquals(result.condition_data, 
            '{"allow_abstain": false, "require_majority": true, "publicize_votes": false, "voting_period": 5}')

    def test_vote_form_displays_inital_data_in_edit_mode(self):

        # Create condition template
        VoteForm = conditionFormDict["votecondition"]
        response_data = {'allow_abstain': False, 'require_majority': True, 
            'publicize_votes': False, 'voting_period': '23'}
        voteForm = VoteForm(permission=self.target_permission, request=self.request, 
            data=response_data)
        voteForm.is_valid()
        voteForm.save()
        condTemplate = self.pcc.get_condition_template()

        # Feed into form
        voteForm = VoteForm(instance=condTemplate, permission=self.target_permission, 
            request=self.request)
        self.assertEquals(voteForm.fields['voting_period'].initial, 23.0)

    def test_vote_condition_form_lets_you_edit_condition(self):
    
        # Create condition template
        VoteForm = conditionFormDict["votecondition"]
        response_data = {'allow_abstain': False, 'require_majority': True, 
            'publicize_votes': False, 'voting_period': '23'}
        voteForm = VoteForm(permission=self.target_permission, request=self.request, 
            data=response_data)
        voteForm.is_valid()
        voteForm.save()
        condTemplate = self.pcc.get_condition_template()

        # Feed into form as instance along with edited data
        response_data['voting_period'] = '30'
        response_data['publicize_votes'] = True
        voteForm2 = VoteForm(instance=condTemplate, permission=self.target_permission, 
            request=self.request, data=response_data)
        voteForm2.is_valid()
        voteForm2.save()

        # Now configuration is different
        condTemplate = self.pcc.get_condition_template()
        self.assertEquals(condTemplate.condition_data, 
            '{"allow_abstain": false, "require_majority": true, "publicize_votes": true, "voting_period": 30}')

    def test_approval_condition_processes_permissions_data(self):

        # Create condition template
        ApprovalForm = conditionFormDict["approvalcondition"]
        self.response_dict['self_approval_allowed'] = True
        self.response_dict['0~individuals'] = [self.users.rose.pk]
        approvalForm = ApprovalForm(permission=self.target_permission, request=self.request, 
            data=self.response_dict)

        approvalForm.is_valid()
        approvalForm.save()
        condTemplate = self.pcc.get_condition_template()
        perm_data = json.loads(condTemplate.permission_data)
        self.assertEquals(perm_data[0]["permission_type"], Changes.Conditionals.Approve)
        self.assertEquals(perm_data[0]["permission_actors"], [self.users.rose.pk])
        self.assertFalse(perm_data[0]["permission_roles"])
        self.assertFalse(perm_data[0]["permission_configuration"])

    def test_approval_condition_form_creates_working_condition(self):
        
        # First Pinoe creates a resource & places it in the community
        resource = self.rc.create_resource(name="USWNT Forum")
        self.rc.set_target(target=resource)
        self.rc.change_owner_of_target(self.instance)

        # Then she adds a permission that says that Tobin can add items.
        self.prc.set_target(target=resource)
        action, permission = self.prc.add_permission(permission_type=Changes.Resources.AddItem,
            permission_actors=[self.users.tobin.pk])

        # Pinoe uses the form to place a condition on the permission she just created, such that
        # Tobin's action needs Rose's approval.
        ApprovalForm = conditionFormDict["approvalcondition"]
        self.response_dict['0~individuals'] = [self.users.rose.pk]
        approvalForm = ApprovalForm(permission=permission, request=self.request, 
            data=self.response_dict)
        approvalForm.is_valid()
        approvalForm.save()

        # When Tobin tries to add an item it is stuck waiting
        self.rc.set_actor(actor=self.users.tobin)
        tobin_action, item = self.rc.add_item(item_name="Tobin's item")
        self.assertEquals(resource.get_items(), [])
        self.assertEquals(Action.objects.get(pk=tobin_action.pk).status, "waiting")

        # Get the condition item created by action
        self.cc = ConditionalClient(actor=self.users.pinoe)
        condition = self.cc.get_condition_item_given_action(action_pk=tobin_action.pk)

        # Now Rose approves it
        acc = ApprovalConditionClient(target=condition, actor=self.users.rose)
        action, result = acc.approve()
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

        # And Tobin's item has been added
        self.assertEquals(Action.objects.get(pk=tobin_action.pk).status, "implemented")
        self.assertEquals(resource.get_items(), ["Tobin's item"])

    def test_editing_condition_allows_editing_of_permissions(self):

        # Create condition template with permissions info
        ApprovalForm = conditionFormDict["approvalcondition"]
        self.response_dict['self_approval_allowed'] = True
        self.response_dict['0~individuals'] = [self.users.rose.pk]
        approvalForm = ApprovalForm(permission=self.target_permission, request=self.request, 
            data=self.response_dict)
        approvalForm.is_valid()
        approvalForm.save()
        condTemplate = self.pcc.get_condition_template()
        self.assertEquals(condTemplate.condition_data, '{"self_approval_allowed": true}')
        self.assertEquals(json.loads(condTemplate.permission_data)[0]["permission_actors"], 
            [self.users.rose.pk])

        # Feed into form as instance along with edited data
        self.response_dict['self_approval_allowed'] = False
        self.response_dict['0~individuals'] = [self.users.crystal.pk]
        approvalForm2 = ApprovalForm(instance=condTemplate, permission=self.target_permission, 
            request=self.request, data=self.response_dict)
        approvalForm2.is_valid()
        approvalForm2.save()

        # Now configuration is different
        condTemplate = self.pcc.get_condition_template()
        self.assertEquals(condTemplate.condition_data, '{"self_approval_allowed": false}')
        self.assertEquals(json.loads(condTemplate.permission_data)[0]["permission_actors"], 
            [self.users.crystal.pk])

    def test_can_set_condition_on_metapermission(self):
        ...
        # I'm worried that there might be issues determining ownership.


class BasicCommunityTest(DataTestCase):

    def setUp(self):
        self.commClient = CommunityClient(actor=self.users.pinoe)

    def test_create_community(self):
        community = self.commClient.create_community(name="A New Community")
        self.assertEquals(community.get_unique_id(), "communities_community_1")
        self.assertEquals(community.name, "A New Community")
    
    def test_community_is_itself_collectively_owned(self):
        community = self.commClient.create_community(name="A New Community")
        self.assertEquals(community.get_owner(), community)

    def test_community_collectively_owns_resource(self):
        community = self.commClient.create_community(name="A New Community")
        rc = ResourceClient(actor=self.users.pinoe)
        resource = rc.create_resource(name="A New Resource")
        self.assertEquals(resource.get_owner().name, "meganrapinoe's Default Community")
        rc.set_target(target=resource)
        rc.change_owner_of_target(new_owner=community)
        self.assertEquals(resource.get_owner().name, "A New Community")

    def test_change_name_of_community(self):
        community = self.commClient.create_community(name="A New Community")
        self.commClient.set_target(target=community)
        action, result = self.commClient.change_name(new_name="A Newly Named Community")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(community.name, "A Newly Named Community")

    def test_reject_change_name_of_community_from_nongovernor(self):
        community = self.commClient.create_community(name="A New Community")
        self.commClient.set_target(target=community)
        self.commClient.set_actor(actor=self.users.jj)
        action, result = self.commClient.change_name(new_name="A Newly Named Community")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(community.name, "A New Community")

    def test_change_name_of_community_owned_resource(self):
        # SetUp
        community = self.commClient.create_community(name="A New Community")
        rc = ResourceClient(actor=self.users.pinoe)
        resource = rc.create_resource(name="A New Resource")
        rc.set_target(target=resource)
        action, result = rc.change_owner_of_target(new_owner=community)
        self.assertEquals(resource.get_owner().name, "A New Community")
        # Test
        new_action, result = rc.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=new_action.pk).status, "implemented")
        self.assertEquals(resource.name, "A Changed Resource")

    def test_reject_change_name_of_community_owned_resource_from_nongovernor(self):
        # SetUp
        community = self.commClient.create_community(name="A New Community")
        rc = ResourceClient(actor=self.users.pinoe)
        resource = rc.create_resource(name="A New Resource")
        rc.set_target(target=resource)
        action, result = rc.change_owner_of_target(new_owner=community)
        self.assertEquals(resource.get_owner().name, "A New Community")
        # Test
        rc.set_actor(actor=self.users.jj)
        new_action, result = rc.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=new_action.pk).status, "rejected")
        self.assertEquals(resource.name, "A New Resource")

    def test_add_permission_to_community_owned_resource_allowing_nongovernor_to_change_name(self):
        
        # SetUp
        community = self.commClient.create_community(name="A New Community")
        rc = ResourceClient(actor=self.users.pinoe)
        resource = rc.create_resource(name="A New Resource")
        rc.set_target(target=resource)
        action, result = rc.change_owner_of_target(new_owner=community)
        self.assertEquals(resource.get_owner().name, "A New Community")

        # Add  permission for nongovernor to change name
        prc = PermissionResourceClient(actor=self.users.pinoe)
        prc.set_target(target=resource)
        action, permission = prc.add_permission(permission_type=Changes.Resources.ChangeResourceName,
            permission_actors=[self.users.jj.pk])
        
        # Test - JJ should now be allowed to change name
        rc.set_actor(actor=self.users.jj)
        new_action, result = rc.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=new_action.pk).status, "implemented")
        self.assertEquals(resource.name, "A Changed Resource")    

        # Test - Governors should still be able to do other things still that are not set in PR
        rc.set_actor(actor=self.users.pinoe)
        new_action, result = rc.add_item(item_name="Pinoe's item")
        self.assertEquals(resource.get_items(), ["Pinoe's item"])

    def test_add_governor(self):
        community = self.commClient.create_community(name="A New Community")
        self.commClient.set_target(community)
        action, result = self.commClient.add_governor(governor_pk=self.users.crystal.pk)
        self.assertEquals(community.roles.get_governors(),
            {'actors': [self.users.pinoe.pk, self.users.crystal.pk], 'roles': []})


class GoverningAuthorityTest(DataTestCase):

    def setUp(self):
        self.commClient = CommunityClient(actor=self.users.pinoe)
        self.community = self.commClient.create_community(name="A New Community")
        self.commClient.set_target(target=self.community)
        self.commClient.add_members([self.users.sonny.pk])
        self.commClient.add_governor(governor_pk=self.users.sonny.pk)
        self.condClient = ConditionalClient(actor=self.users.pinoe, target=self.community)

    def test_with_conditional_on_governer_decision_making(self):

        # Set conditional on governor decision making.  Only Sonny can approve condition.
        permission_data = [{ "permission_type": Changes.Conditionals.Approve, "permission_actors": [self.users.sonny.pk]}]
        action, result = self.commClient.add_leadership_condition(
            leadership_type="governor", condition_type="approvalcondition", permission_data=permission_data)
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented") # Action accepted

        # Governor Pinoe does a thing, creates a conditional action to be approved
        action, result = self.commClient.change_name(new_name="A Newly Named Community")
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

        # Create community
        self.commClient = CommunityClient(actor=self.users.pinoe)
        self.community = self.commClient.create_community(name="A New Community")

        # Create a resource and give ownership to community
        self.resourceClient = ResourceClient(actor=self.users.pinoe)
        self.resource = self.resourceClient.create_resource(name="A New Resource")
        self.resourceClient.set_target(target=self.resource)
        self.resourceClient.change_owner_of_target(new_owner=self.community)

    def test_foundational_authority_override_on_individually_owned_object(self):
        # NOTE: this object is technically community owned by the creator's default community

        # Create individually owned resource
        resource = self.resourceClient.create_resource(name="A resource")

        # By default, Aubrey's actions are not successful
        aubrey_rc = ResourceClient(actor=self.users.aubrey, target=resource)
        action, result = aubrey_rc.change_name(new_name="Aubrey's resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(resource.get_name(), "A resource")

        # Owner adds a specific permission for Aubrey, so Aubrey's action is successful
        prc = PermissionResourceClient(actor=self.users.pinoe, target=resource)
        owner_action, result = prc.add_permission(permission_type=Changes.Resources.ChangeResourceName,
            permission_actors=[self.users.aubrey.pk])
        action, result = aubrey_rc.change_name(new_name="Aubrey's resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(resource.get_name(), "Aubrey's resource")

        # Now switch foundational override.
        fp_action, result = prc.enable_foundational_permission()

        # Aunrey's actions are no longer successful
        action, result = aubrey_rc.change_name(new_name="A new name for Aubrey's resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(resource.get_name(), "Aubrey's resource")

    def test_foundational_authority_override_on_community_owned_object(self):
        
        # By default, Aubrey's actions are not successful
        aubrey_rc = ResourceClient(actor=self.users.aubrey, target=self.resource)
        action, result = aubrey_rc.change_name(new_name="Aubrey's resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.get_name(), "A New Resource")

        # Owner Pinoe adds a specific permission for Aubrey, Aubrey's action is successful
        prc = PermissionResourceClient(actor=self.users.pinoe, target=self.resource)
        owner_action, result = prc.add_permission(permission_type=Changes.Resources.ChangeResourceName,
            permission_actors=[self.users.aubrey.pk])
        action, result = aubrey_rc.change_name(new_name="Aubrey's resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(self.resource.get_name(), "Aubrey's resource")

        # Now switch foundational override.
        fp_action, result = prc.enable_foundational_permission()

        # Aubrey's actions are no longer successful
        action, result = aubrey_rc.change_name(new_name="A new name for Aubrey's resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.get_name(), "Aubrey's resource")

    def test_foundational_authority_override_on_community_owned_object_with_conditional(self):
        
        # Pinoe, Tobin, Christen and JMac are members of the community. 
        self.commClient.set_target(self.community)
        action, result = self.commClient.add_members([self.users.tobin.pk, self.users.christen.pk,
            self.users.jmac.pk])
        com_members = self.commClient.get_members()
        self.assertCountEqual(com_members,
            [self.users.pinoe, self.users.tobin, self.users.christen, self.users.jmac])

        # In this community, all members are owners but for the foundational authority to do
        # anything they must agree via majority vote.
        action, result = self.commClient.add_owner_role(owner_role="members") # Add member role
        permission_data = [{ "permission_type": Changes.Conditionals.AddVote, "permission_roles": ["members"]}]
        action, result = self.commClient.add_leadership_condition(
            leadership_type="owner",
            condition_type = "votecondition", 
            condition_data={"voting_period": 1 },
            permission_data=permission_data
        )
        # FIXME: still too much configuration :/

        # Christen tries to change the name of the resource but is not successful because it's not something
        # that triggers foundational authority.
        christen_rc = ResourceClient(actor=self.users.christen, target=self.resource)
        action, result = christen_rc.change_name(new_name="Christen's resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.get_name(), "A New Resource")

        # Christen tries to switch on foundational override.  This is a foundational change and thus it 
        # enter the foundational pipeline, triggers a vote condition, and generates a vote. Everyone votes
        # and it's approved. 
        key_action, result = christen_rc.enable_foundational_permission()
        self.assertEquals(Action.objects.get(pk=key_action.pk).status, "waiting")

        condClient = ConditionalClient(actor=self.users.pinoe, target=self.community)
        conditional_action = condClient.get_condition_item_given_action_and_source(action_pk=key_action.pk,
            source_id="owner_"+str(self.community.pk))

        vcc = VoteConditionClient(target=conditional_action, actor=self.users.pinoe)
        vcc.vote(vote="yea")
        vcc.set_actor(actor=self.users.tobin)
        vcc.vote(vote="yea")
        vcc.set_actor(actor=self.users.jmac)
        vcc.vote(vote="yea")
        vcc.set_actor(actor=self.users.christen)
        vcc.vote(vote="yea")

        # HACK to get around the one hour minimum voting period
        conditional_action.voting_starts = timezone.now() - timedelta(hours=2)
        conditional_action.save(override_check=True)

        self.assertEquals(Action.objects.get(pk=key_action.pk).status, "implemented")
        resource = self.resourceClient.get_resource_given_pk(pk=self.resource.pk)
        self.assertTrue(resource[0].foundational_permission_enabled)

    def test_change_governors_requires_foundational_authority(self):

        # Pinoe is the owner, Sully and Pinoe are governors.
        self.commClient.set_target(self.community)
        self.commClient.add_members([self.users.sully.pk])
        action, result = self.commClient.add_governor(governor_pk=self.users.sully.pk)
        self.assertEquals(self.community.roles.get_governors(),
            {'actors': [self.users.pinoe.pk, self.users.sully.pk], 'roles': []})

        # Sully tries to add Aubrey as a governor.  She cannot, she is not an owner.
        self.commClient.set_actor(actor=self.users.sully)
        action, result = self.commClient.add_governor(governor_pk=self.users.aubrey.pk)
        self.assertEquals(self.community.roles.get_governors(), 
            {'actors': [self.users.pinoe.pk, self.users.sully.pk], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")

        # Rose tries to add Aubrey as a governor.  She cannot, she is not an owner.
        self.commClient.set_actor(actor=self.users.rose)
        action, result = self.commClient.add_governor(governor_pk=self.users.aubrey.pk)
        self.assertEquals(self.community.roles.get_governors(), 
            {'actors': [self.users.pinoe.pk, self.users.sully.pk], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")

        # Pinoe tries to add Aubrey as a governor.  She can, since has foundational authority.
        self.commClient.set_actor(actor=self.users.pinoe)
        action, result = self.commClient.add_governor(governor_pk=self.users.aubrey.pk)
        self.assertEquals(self.community.roles.get_governors(), 
            {'actors': [self.users.pinoe.pk, self.users.sully.pk, self.users.aubrey.pk], 
            'roles': []})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

    def test_change_owners_requires_foundational_authority(self):

        # Pinoe adds Crystal as owner.  There are now two owners with no conditions.
        self.commClient.set_target(self.community)
        self.commClient.add_members([self.users.crystal.pk])
        action, result = self.commClient.add_owner(owner_pk=self.users.crystal.pk)
        self.assertEquals(self.community.roles.get_owners(), 
            {'actors': [self.users.pinoe.pk, self.users.crystal.pk], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

        # Tobin tries to add Christen as owner.  She cannot, she is not an owner.
        self.commClient.set_actor(actor=self.users.tobin)
        action, result = self.commClient.add_owner(owner_pk=self.users.christen.pk)
        self.assertEquals(self.community.roles.get_owners(), 
            {'actors': [self.users.pinoe.pk, self.users.crystal.pk], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")

        # Crystal tries to add Christen as owner.  She can, since has foundational authority.
        self.commClient.set_actor(actor=self.users.crystal)
        action, result = self.commClient.add_owner(owner_pk=self.users.christen.pk)
        self.assertEquals(self.community.roles.get_owners(), 
            {'actors': [self.users.pinoe.pk, self.users.crystal.pk, self.users.christen.pk], 
            'roles': []})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

    def test_change_foundational_override_requires_foundational_authority(self):

        # Pinoe is the owner, Pinoe and Crystal are governors.
        self.commClient.set_target(self.community)
        self.commClient.add_members([self.users.crystal.pk])
        action, result = self.commClient.add_governor(governor_pk=self.users.crystal.pk)
        self.assertEquals(self.community.roles.get_governors(), 
            {'actors': [self.users.pinoe.pk, self.users.crystal.pk], 'roles': []})
        self.resourceClient.set_target(self.resource)

        # JJ tries to enable foundational override on resource. 
        # She cannot, she is not an owner.
        self.resourceClient.set_actor(actor=self.users.jj)
        action, result = self.resourceClient.enable_foundational_permission()
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertFalse(self.resource.foundational_permission_enabled)

        # Crystal tries to enable foundational override on resource.
        # She cannot, she is not an owner.
        self.resourceClient.set_actor(actor=self.users.crystal)
        action, result = self.resourceClient.enable_foundational_permission()
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertFalse(self.resource.foundational_permission_enabled)

        # Pinoe tries to enable foundational override on resource.
        # She can, since she is an owner and has foundational authority.
        self.resourceClient.set_actor(actor=self.users.pinoe)
        action, result = self.resourceClient.enable_foundational_permission()
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertTrue(self.resource.foundational_permission_enabled)


class RolesetTest(DataTestCase):

    def setUp(self):

        self.commClient = CommunityClient(actor=self.users.pinoe)
        self.community = self.commClient.create_community(name="USWNT")
        self.commClient.set_target(self.community)
        self.resourceClient = ResourceClient(actor=self.users.pinoe)
        self.resource = self.resourceClient.create_resource(name="USWNT Resource")
        self.resourceClient.set_target(self.resource)
        self.resourceClient.change_owner_of_target(new_owner=self.community)
        self.permClient = PermissionResourceClient(actor=self.users.pinoe)

    # Test custom roles

    def test_basic_custom_role(self):

        # No custom roles so far
        roles = self.commClient.get_custom_roles()
        self.assertEquals(roles, {})

        # Add a role
        action, result = self.commClient.add_role(role_name="forwards")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        roles = self.commClient.get_custom_roles()
        self.assertEquals(roles, {'forwards': []})

        # Add people to role
        self.commClient.add_members([self.users.christen.pk, self.users.crystal.pk])
        action, result = self.commClient.add_people_to_role(role_name="forwards", 
            people_to_add=[self.users.christen.pk, self.users.crystal.pk, self.users.pinoe.pk])
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        roles = self.commClient.get_roles()
        self.assertCountEqual(roles["forwards"], 
            [self.users.christen.pk, self.users.crystal.pk, self.users.pinoe.pk])

        # Remove person from role
        action, result = self.commClient.remove_people_from_role(role_name="forwards", 
            people_to_remove=[self.users.crystal.pk])
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        roles = self.commClient.get_roles()
        self.assertCountEqual(roles["forwards"], [self.users.christen.pk, self.users.pinoe.pk])

        # Remove role
        action, result = self.commClient.remove_role(role_name="forwards")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        roles = self.commClient.get_custom_roles()
        self.assertEquals(roles, {})

    def test_basic_role_works_with_permission_item(self):

        # Aubrey wants to change the name of the resource, she can't
        self.commClient.add_members([self.users.aubrey.pk])
        self.resourceClient.set_actor(actor=self.users.aubrey)
        action, result = self.resourceClient.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.name, "USWNT Resource")

        # Pinoe adds a 'namers' role to the community which owns the resource
        self.resourceClient.set_actor(actor=self.users.pinoe)
        action, result = self.commClient.add_role(role_name="namers")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.commClient.refresh_target()
        roles = self.commClient.get_custom_roles()
        self.assertEquals(roles, {'namers': []})

        # Pinoe creates a permission item with the 'namers' role in it
        self.permClient.set_target(self.resource)
        action, result = self.permClient.add_permission(permission_type=Changes.Resources.ChangeResourceName,
            permission_roles=["namers"])
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

        # Pinoe adds Aubrey to the 'namers' role in the community
        action, result = self.commClient.add_people_to_role(role_name="namers", 
            people_to_add=[self.users.aubrey.pk])
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        roles = self.commClient.get_roles()
        self.assertCountEqual(roles["namers"], [self.users.aubrey.pk])

        # Aubrey can now change the name of the resource
        self.resourceClient.set_actor(actor=self.users.aubrey)
        action, result = self.resourceClient.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(self.resource.name, "A Changed Resource")

        # Pinoe removes Aubrey from the namers role in the community
        action, result = self.commClient.remove_people_from_role(role_name="namers", 
            people_to_remove=[self.users.aubrey.pk])
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        roles = self.commClient.get_roles()
        self.assertCountEqual(roles["namers"], [])

        # Aubrey can no longer change the name of the resource
        self.resourceClient.set_actor(actor=self.users.aubrey)
        action, result = self.resourceClient.change_name(new_name="A Newly Changed Resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.name, "A Changed Resource")

    def test_basic_role_works_with_governor(self):        

        # Pinoe adds the resource to her community
        self.resourceClient.set_target(target=self.resource)
        self.resourceClient.change_owner_of_target(new_owner=self.community)

        # Aubrey wants to change the name of the resource, she can't
        self.resourceClient.set_actor(actor=self.users.aubrey)
        action, result = self.resourceClient.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.name, "USWNT Resource")

        # Pinoe adds member role to governors
        action, result = self.commClient.add_governor_role(governor_role="members")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.commClient.refresh_target()
        gov_info = self.commClient.get_governorship_info()
        self.assertDictEqual(gov_info, {'actors': [self.users.pinoe.pk], 'roles': ['members']})

        # Aubrey tries to do a thing and can't
        action, result = self.resourceClient.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.name, "USWNT Resource")

        # Pinoe adds Aubrey as a member
        action, result = self.commClient.add_members(member_pk_list=[self.users.aubrey.pk])
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        roles = self.commClient.get_roles()
        self.assertCountEqual(roles["members"], [self.users.pinoe.pk, self.users.aubrey.pk]) 

        # Aubrey tries to do a thing and can
        action, result = self.resourceClient.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(self.resource.name, "A Changed Resource")

    def test_add_member_and_remove_member_from_roleset(self):

        self.assertEquals(self.commClient.get_members(), [self.users.pinoe])

        # Pinoe adds Aubrey to the community
        self.commClient.add_members([self.users.aubrey.pk])
        self.assertCountEqual(self.commClient.get_members(), 
            [self.users.pinoe, self.users.aubrey])

        # Pinoe removes Aubrey from the community
        action, result = self.commClient.remove_members([self.users.aubrey.pk])
        self.assertEquals(self.commClient.get_members(), [self.users.pinoe])


@skip("Not using forms right now - need to rethink/refactor")
class RoleFormTest(DataTestCase):
    """Note that RoleForm only lets you change custom roles."""

    def setUp(self):

        # Create a community
        self.commClient = CommunityClient(actor=self.users.pinoe)
        self.instance = self.commClient.create_community(name="USWNT")
        self.commClient.set_target(self.instance)

        # Add another user
        self.commClient.add_member(self.users.rose.pk)

        # Create request object
        Request = namedtuple('Request', 'user')
        self.request = Request(user=self.users.pinoe)
        self.data = {}

    def test_add_role_via_role_form(self):

        # Before doing anything, assert no custom roles yet
        self.assertEquals(self.commClient.get_custom_roles(), {})

        # Add a new role using the role form
        self.data.update({
            '0~rolename': 'midfielders',
            '0~members': [self.users.pinoe.pk, self.users.rose.pk]})
        self.role_form = RoleForm(instance=self.instance, request=self.request, data=self.data)
        
        # Form is valid and cleaned data is correct
        result = self.role_form.is_valid()
        self.assertEquals(self.role_form.cleaned_data, 
            {'0~rolename': 'midfielders', 
            '0~members': [str(self.users.pinoe.pk), str(self.users.rose.pk)]})

        # After saving, data is updated.
        self.role_form.save()
        self.assertCountEqual(self.commClient.get_custom_roles().keys(), ["midfielders"])
        self.assertEquals(self.commClient.get_custom_roles()["midfielders"],
            [self.users.pinoe.pk, self.users.rose.pk])

    def test_add_user_to_role_via_role_form(self):

        # Before doing anything, add custom role
        self.commClient.add_role(role_name="midfielders")
        self.assertEquals(self.commClient.get_custom_roles(), {"midfielders": []})

        # Add a user using the role form
        self.data.update({
            '0~rolename': 'midfielders', 
            '0~members': [self.users.pinoe.pk, self.users.rose.pk]})
        self.role_form = RoleForm(instance=self.instance, request=self.request, data=self.data)
        
        # Form is valid and cleaned data is correct
        result = self.role_form.is_valid()
        self.assertEquals(self.role_form.cleaned_data, 
            {'0~rolename': 'midfielders', 
            '0~members': [str(self.users.pinoe.pk), str(self.users.rose.pk)],
            '1~members': [],    # empty row, will be discarded
            '1~rolename': ''})  # empty row, will be discarded

        # After saving, data is updated.
        self.role_form.save()
        self.assertCountEqual(self.commClient.get_users_given_role(role_name="midfielders"), 
            [self.users.pinoe.pk, self.users.rose.pk])
   
    def test_remove_user_from_role_via_role_form(self):

        # Quick add via form
        self.data.update({
            '0~rolename': 'midfielders', 
            '0~members': [self.users.pinoe.pk, self.users.rose.pk]})
        self.role_form = RoleForm(instance=self.instance, request=self.request, data=self.data)
        self.role_form.is_valid()
        self.role_form.save()
        self.assertCountEqual(self.commClient.get_users_given_role(role_name="midfielders"), 
            [self.users.pinoe.pk, self.users.rose.pk])

        # Remove role via form
        self.data = {'0~rolename': 'midfielders', '0~members': [self.users.pinoe.pk]}
        self.role_form = RoleForm(instance=self.instance, request=self.request, data=self.data)

         # Form is valid and cleaned data is correct
        result = self.role_form.is_valid()
        self.assertEquals(self.role_form.cleaned_data, 
            {'0~rolename': 'midfielders', '0~members':  [str(self.users.pinoe.pk)], 
            '1~rolename': '', '1~members': []})

        # After saving, data is updated.
        self.role_form.save()
        self.assertCountEqual(self.commClient.get_users_given_role(role_name="midfielders"), 
            [self.users.pinoe.pk])


@skip("Need to rethink forms - not using them on frontend for now")
class PermissionFormTest(DataTestCase):

    def setUp(self):

        # Create a community
        self.commClient = CommunityClient(actor=self.users.pinoe)
        self.instance = self.commClient.create_community(name="USWNT")
        self.commClient.set_target(self.instance)

        # Add members to community
        self.commClient.add_members([self.users.christen.pk, self.users.aubrey.pk, 
            self.users.rose.pk])

        # Create new roles
        action, result = self.commClient.add_role(role_name="spirit players")
        self.commClient.add_people_to_role(role_name="spirit players", 
            people_to_add=[self.users.aubrey.pk, self.users.rose.pk])
        self.commClient.add_role(role_name="midfielders")
        self.commClient.add_people_to_role(role_name="midfielders",
            people_to_add=[self.users.rose.pk, self.users.pinoe.pk])

        # Create request object
        Request = namedtuple('Request', 'user')
        self.request = Request(user=self.users.pinoe)

        # Initial data
        self.data = {}
        self.prClient = PermissionResourceClient(actor=self.users.pinoe, target=self.instance)
        permissions = self.prClient.get_settable_permissions(return_format="list_of_strings")
        for count, permission in enumerate(permissions):
            self.data[str(count) + "~" + "name"] = permission
            self.data[str(count) + "~" + "roles"] = []
            self.data[str(count) + "~" + "individuals"] = []

    def test_instantiate_permission_form(self):
        # NOTE: this only works for community permission form with role_choices set

        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request)

        # Get possible permissions to set on instance
        self.prClient = PermissionResourceClient(actor=self.users.pinoe, target=self.instance)
        permissions = self.prClient.get_settable_permissions(return_format="list_of_strings")

        # Number of fields on permission form should be permissions x 3
        # FIXME: configurable fields throw this off, hack below is kinda ugly
        self.assertEqual(len(permissions)*3, 
            len([p for p in self.permission_form.fields if "configurablefield" not in p]))

    def test_add_role_to_permission(self):

        # Before changes, no permissions associated with role
        permissions_for_role = self.prClient.get_permissions_associated_with_role_for_target(role_name="spirit players")
        self.assertEqual(permissions_for_role, [])

        # add role to permission
        self.data["6~roles"] = ["spirit players"]
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)

        # Check that it's valid
        self.permission_form.is_valid()
        self.assertEquals(self.permission_form.cleaned_data["6~roles"], ["spirit players"])
        
        # Check that it works on save
        self.permission_form.save()
        permissions_for_role = self.prClient.get_permissions_associated_with_role(role_name="spirit players")
        self.assertEqual(permissions_for_role[0].change_type, Changes.Communities.AddPeopleToRole)

    def test_add_roles_to_permission(self):

        # Before changes, no permissions associated with role
        permissions_for_role = self.prClient.get_permissions_associated_with_role(role_name="spirit players")
        self.assertEqual(permissions_for_role, [])

        # add role to permission
        self.data["6~roles"] = ["midfielders", "spirit players"]  # Use this format since it's a multiple choice field
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)

        # Check that it's valid
        self.permission_form.is_valid()
        self.assertEquals(self.permission_form.cleaned_data["6~roles"], ["midfielders", "spirit players"])
        # Check that it works on save
        self.permission_form.save()
        permissions_for_role = self.prClient.get_permissions_associated_with_role(role_name="spirit players")
        self.assertEqual(permissions_for_role[0].change_type, Changes.Communities.AddPeopleToRole)
        permissions_for_role = self.prClient.get_permissions_associated_with_role(role_name="midfielders")
        self.assertEqual(permissions_for_role[0].change_type, Changes.Communities.AddPeopleToRole)

    def test_add_individual_to_permission(self):

        # Before changes, no permissions associated with actor
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor=self.users.aubrey.pk)
        self.assertEqual(permissions_for_actor, [])

        # Add actor to permission
        self.data["6~individuals"] = [self.users.aubrey.pk]  # use this format since it's a character field
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)

        # Check that it's valid
        self.permission_form.is_valid()
        self.assertEquals(self.permission_form.cleaned_data["6~individuals"], 
            [str(self.users.aubrey.pk)])        

        # Check form works on save
        self.permission_form.save()
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor=self.users.aubrey.pk)
        self.assertEqual(permissions_for_actor[0].change_type, Changes.Communities.AddPeopleToRole)

    def test_add_individuals_to_permission(self):

        # Before changes, no permissions associated with actor
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor=self.users.aubrey.pk)
        self.assertEqual(permissions_for_actor, [])

        # Add actor to permission
        self.data["6~individuals"] = [self.users.aubrey.pk, self.users.christen.pk]
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)

        # Check that it's valid
        self.permission_form.is_valid()
        self.assertEquals(self.permission_form.cleaned_data["6~individuals"], 
            [str(self.users.aubrey.pk), str(self.users.christen.pk)])        

        # Check form works on save
        self.permission_form.save()
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor=self.users.aubrey.pk)
        self.assertEqual(permissions_for_actor[0].change_type, Changes.Communities.AddPeopleToRole)
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor=self.users.christen.pk)
        self.assertEqual(permissions_for_actor[0].change_type, Changes.Communities.AddPeopleToRole)

    def test_add_multiple_to_multiple_permissions(self):

        # Before changes, no permissions associated with role
        permissions_for_role = self.prClient.get_permissions_associated_with_role(role_name="spirit players")
        self.assertEqual(permissions_for_role, [])

        # Before changes, no permissions associated with actor
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor=self.users.aubrey.pk)
        self.assertEqual(permissions_for_actor, [])

        # Add roles to multiple permissions & actors to multiple permissions
        self.data["6~individuals"] = [self.users.aubrey.pk]
        self.data["7~individuals"] = [self.users.aubrey.pk, 
            self.users.christen.pk, self.users.pinoe.pk]
        self.data["6~roles"] = ["spirit players", "midfielders"]
        self.data["4~roles"] = ["spirit players", "midfielders"]
        self.data["1~roles"] = ["spirit players"]

        # Create, validate and save form
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()
        
        # Actor checks
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor=self.users.aubrey.pk)
        change_types = [perm.get_change_type() for perm in permissions_for_actor]
        self.assertCountEqual(change_types, ['AddPeopleToRoleStateChange', 'AddRoleStateChange'])
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor=self.users.christen.pk)
        change_types = [perm.get_change_type() for perm in permissions_for_actor]
        self.assertCountEqual(change_types, ['AddRoleStateChange'])
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor=self.users.pinoe.pk)
        change_types = [perm.get_change_type() for perm in permissions_for_actor]
        self.assertCountEqual(change_types, ['AddRoleStateChange'])

        # Role checks
        permissions_for_role = self.prClient.get_permissions_associated_with_role(
            role_name="midfielders")
        change_types = [perm.get_change_type() for perm in permissions_for_role]
        self.assertCountEqual(change_types, ['AddPeopleToRoleStateChange', 'AddOwnerRoleStateChange']) 
        permissions_for_role = self.prClient.get_permissions_associated_with_role(
            role_name="spirit players")
        change_types = [perm.get_change_type() for perm in permissions_for_role]
        self.assertCountEqual(change_types, ['AddOwnerRoleStateChange', 'AddPeopleToRoleStateChange',
            'AddGovernorStateChange']) 

    def test_remove_role_from_permission(self):

        # add role to permission
        self.data["6~roles"] = ["spirit players"]
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()
        permissions_for_role = self.prClient.get_permissions_associated_with_role(
            role_name="spirit players")
        self.assertEqual(permissions_for_role[0].change_type, Changes.Communities.AddPeopleToRole)

        # now remove it
        self.data["6~roles"] = []
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()
        permissions_for_role = self.prClient.get_permissions_associated_with_role(
            role_name="spirit players")
        self.assertFalse(permissions_for_role) # Empty list should be falsy

    def test_remove_roles_from_permission(self):

        # add roles to permission
        self.data["6~roles"] = ["spirit players", "midfielders"]
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()
        permissions_for_role = self.prClient.get_permissions_associated_with_role(
            role_name="spirit players")
        self.assertEqual(permissions_for_role[0].change_type, Changes.Communities.AddPeopleToRole)
        permissions_for_role = self.prClient.get_permissions_associated_with_role(
            role_name="midfielders")
        self.assertEqual(permissions_for_role[0].change_type, Changes.Communities.AddPeopleToRole)

        # now remove them
        self.data["6~roles"] = []
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()
        permissions_for_role = self.prClient.get_permissions_associated_with_role(
            role_name="spirit players")
        self.assertFalse(permissions_for_role) # Empty list should be falsy
        permissions_for_role = self.prClient.get_permissions_associated_with_role(
            role_name="midfielders")
        self.assertFalse(permissions_for_role) # Empty list should

    def test_remove_individual_from_permission(self):
        
        # Add actor to permission
        self.data["6~individuals"] = [self.users.christen.pk]
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor=self.users.christen.pk)
        self.assertEqual(permissions_for_actor[0].change_type, Changes.Communities.AddPeopleToRole)

        # Remove actor from permission
        self.data["6~individuals"] = []
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor=self.users.christen.pk)
        self.assertFalse(permissions_for_actor)  # Empty list should be falsy

    def test_remove_individuals_from_permission(self):
        
        # Add actors to permission
        self.data["6~individuals"] = [self.users.pinoe.pk, self.users.christen.pk]
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor=self.users.pinoe.pk)
        self.assertEqual(permissions_for_actor[0].change_type, Changes.Communities.AddPeopleToRole)
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor=self.users.christen.pk)
        self.assertEqual(permissions_for_actor[0].change_type, Changes.Communities.AddPeopleToRole)

        # Remove actors from permission
        self.data["6~individuals"] = []
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor=self.users.pinoe.pk)
        self.assertFalse(permissions_for_actor) # Empty list should be falsy
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor=self.users.christen.pk)
        self.assertFalse(permissions_for_actor) # Empty list should be falsy
        
    def test_add_and_remove_multiple_from_multiple_permissions(self):

        # Add roles to multiple permissions & actors to multiple permissions
        self.data["6~individuals"] = [self.users.aubrey.pk]
        self.data["7~individuals"] = [self.users.aubrey.pk, self.users.christen.pk,
            self.users.pinoe.pk]
        self.data["6~roles"] = ["spirit players", "midfielders"]
        self.data["4~roles"] = ["spirit players", "midfielders"]
        self.data["1~roles"] = ["spirit players"]

        # Create, validate and save form
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()
        
        # Actor + role checks, not complete for brevity's sake (is tested elsewhere)
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor=self.users.aubrey.pk)
        change_types = [perm.get_change_type() for perm in permissions_for_actor]
        self.assertCountEqual(change_types, ['AddPeopleToRoleStateChange', 'AddRoleStateChange'])
        permissions_for_role = self.prClient.get_permissions_associated_with_role(
            role_name="spirit players")
        change_types = [perm.get_change_type() for perm in permissions_for_role]
        self.assertCountEqual(change_types, ['AddOwnerRoleStateChange', 'AddPeopleToRoleStateChange',
            'AddGovernorStateChange']) 

        # Okay, now remove some of these
        self.data["6~individuals"] = []
        self.data["7~individuals"] = [self.users.christen.pk, self.users.pinoe.pk]
        self.data["6~roles"] = []
        self.data["4~roles"] = ["midfielders"]
        self.data["1~roles"] = ["spirit players"]

        # Create, validate and save form
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()

        # Actor checks
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor=self.users.aubrey.pk)
        self.assertFalse(permissions_for_actor)  # Empty list should be falsy
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor=self.users.christen.pk)
        change_types = [perm.get_change_type() for perm in permissions_for_actor]
        self.assertCountEqual(change_types, ['AddRoleStateChange'])
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor=self.users.pinoe.pk)
        change_types = [perm.get_change_type() for perm in permissions_for_actor]
        self.assertCountEqual(change_types, ['AddRoleStateChange'])

        # Role checks
        permissions_for_role = self.prClient.get_permissions_associated_with_role(
            role_name="midfielders")
        change_types = [perm.get_change_type() for perm in permissions_for_role]
        self.assertCountEqual(change_types, ['AddOwnerRoleStateChange']) 
        permissions_for_role = self.prClient.get_permissions_associated_with_role(
            role_name="spirit players")
        change_types = [perm.get_change_type() for perm in permissions_for_role]
        self.assertCountEqual(change_types, ['AddGovernorStateChange']) 

    def test_adding_permissions_actually_works(self):

        # Add some more members.
        self.commClient.add_members([self.users.tobin.pk, self.users.sully.pk])

        # Before any changes are made, Pinoe as owner can add people to a role,
        # but Aubrey cannot.
        self.commClient.add_people_to_role(role_name="midfielders", 
            people_to_add=[self.users.pinoe.pk, self.users.rose.pk])
        aubrey_cc = CommunityClient(actor=self.users.aubrey, target=self.instance)
        aubrey_cc.add_people_to_role(role_name="midfielders", people_to_add=[self.users.sully.pk])
        roles = self.commClient.get_roles()
        self.assertCountEqual(roles["midfielders"], [self.users.pinoe.pk, self.users.rose.pk])

        # Then Pinoe alters, through the permissions form, who can add people to
        # a role to include Aubrey.
        self.data["6~individuals"] = [self.users.aubrey.pk]
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()

        # Now, Aubrey can add people to roles, but Pinoe cannot.
        # NOTE: Pinoe cannot because she was using the governor permission, and now there's a 
        # specific permission overriding it.
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor=self.users.aubrey.pk)
        change_types = [perm.get_change_type() for perm in permissions_for_actor]
        self.assertCountEqual(change_types, ['AddPeopleToRoleStateChange'])

        aubrey_cc.add_people_to_role(role_name="midfielders", people_to_add=[self.users.sully.pk])
        self.commClient.add_people_to_role(role_name="midfielders", people_to_add=[self.users.jj.pk])

        roles = self.commClient.get_roles()
        self.assertCountEqual(roles["midfielders"], [self.users.pinoe.pk, self.users.rose.pk, 
            self.users.sully.pk])

@skip("Skipping for now - need to rethink forms")
class MetaPermissionsFormTest(DataTestCase):

    def setUp(self):

        # Create a community
        self.commClient = CommunityClient(actor=self.users.pinoe)
        self.instance = self.commClient.create_community(name="USWNT")
        self.commClient.set_target(self.instance)

        # Add members to community
        self.commClient.add_members([self.users.rose.pk, self.users.tobin.pk,
            self.users.christen.pk, self.users.crystal.pk, self.users.jmac.pk,
            self.users.jj.pk, self.users.sonny.pk, self.users.sully.pk])

        # Make separate clients for other actors
        self.roseClient = CommunityClient(actor=self.users.rose, target=self.instance)
        self.jjClient = CommunityClient(actor=self.users.jj, target=self.instance)
        self.tobinClient = CommunityClient(actor=self.users.tobin, target=self.instance)

        # Create request objects
        Request = namedtuple('Request', 'user')
        self.request = Request(user=self.users.pinoe)
        self.roseRequest = Request(user=self.users.rose)
        self.jjRequest = Request(user=self.users.jj)

        # Add a role to community and assign a member
        self.commClient.add_role(role_name="defenders")
        self.commClient.add_people_to_role(role_name="defenders", people_to_add=[self.users.sonny.pk])

        # Initial data for permissions level
        self.permissions_data = {}
        self.prClient = PermissionResourceClient(actor=self.users.pinoe, target=self.instance)
        permissions = self.prClient.get_settable_permissions(return_format="list_of_strings")
        for count, permission in enumerate(permissions):
            self.permissions_data[str(count) + "~" + "name"] = permission
            self.permissions_data[str(count) + "~" + "roles"] = []
            self.permissions_data[str(count) + "~" + "individuals"] = []

        # Give Crystal permission to add people to roles
        self.permissions_data["6~individuals"] = [self.users.crystal.pk]
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.permissions_data)
        self.permission_form.is_valid()
        self.permission_form.save()

        # Initial data for metapermissions level
        self.target_permission = self.prClient.get_specific_permissions(
            change_type=Changes.Communities.AddPeopleToRole)[0]
        self.metapermissions_data = {}
        
        self.metaClient = PermissionResourceClient(actor=self.users.pinoe, target=self.target_permission)
        permissions = self.metaClient.get_settable_permissions(return_format="list_of_strings")
        for count, permission in enumerate(permissions):
            self.metapermissions_data[str(count) + "~" + "name"] = permission
            self.metapermissions_data[str(count) + "~" + "roles"] = []
            self.metapermissions_data[str(count) + "~" + "individuals"] = []        

    def test_adding_metapermission_adds_access_to_permission(self):
        # Currently, only Sonny is in the defenders role, only Crystal has permission to
        # add people to roles, and only Pinoe has the permission to give permission to add 
        # people to roles (because Pinoe, as creator, has ownership/governing power).
        
        # Pinoe wants to give JJ the permission to give permission to add people to
        # roles.  That is, Pinoe desires that JJ should have the metapermission to alter
        # the permission AddPeopleToRoles, so she doesn't have to handle it herself.
        
        # Before Pinoe does anything, JJ tries to give Tobin permission to 
        # add people to roles (in addition to Crystal).  It fails, and we can see that JJ lacks 
        # the relevant metapermission and Tobin the relevant permission.

        self.permissions_data["6~individuals"] = [self.users.tobin.pk, self.users.crystal.pk]
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.jjRequest, data=self.permissions_data)
        self.permission_form.is_valid()
        self.permission_form.save()

        self.tobinClient.add_people_to_role(role_name="defenders", people_to_add=[self.users.sully.pk])
        roles = self.commClient.get_roles()
        self.assertCountEqual(roles["defenders"], [self.users.sonny.pk])

        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor=self.users.tobin.pk)
        self.assertFalse(permissions_for_actor)

        permissions_for_actor = self.metaClient.get_permissions_associated_with_actor(
            actor=self.users.jj.pk)
        self.assertFalse(permissions_for_actor)

        # Then Pinoe alters, through the metapermissions form, who can add alter the
        # AddPeopleToRole permission.  She alters the metapermission on the AddPeopleToRole 
        # permission, adding the individual JJ.

        self.metapermissions_data["0~individuals"] = [self.users.jj.pk]
        self.metapermission_form = MetaPermissionForm(instance=self.target_permission, 
            request=self.request, data=self.metapermissions_data)
        self.metapermission_form.is_valid()
        self.metapermission_form.save()

        permissions_for_actor = self.metaClient.get_permissions_associated_with_actor(
            actor=self.users.jj.pk)
        self.assertEqual(permissions_for_actor[0].get_change_type(), 'AddActorToPermissionStateChange')
        self.assertEqual(permissions_for_actor[0].get_permitted_object(), self.target_permission)

        # Now JJ can give Tobin permission to add people to roles.

        self.permissions_data["6~individuals"] = [self.users.tobin.pk, self.users.crystal.pk]
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.jjRequest, data=self.permissions_data)
        self.permission_form.is_valid()
        self.permission_form.save()

        # Tobin can assign people to roles now.

        self.tobinClient.add_people_to_role(role_name="defenders", people_to_add=[self.users.sully.pk])
        roles = self.commClient.get_roles()
        self.assertCountEqual(roles["defenders"], [self.users.sonny.pk, self.users.sully.pk])

        # Finally, Tobin and Crystal both have permission to add people to roles, while
        # JJ and Pinoe do not.

        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor=self.users.tobin.pk)
        change_types = [perm.get_change_type() for perm in permissions_for_actor]
        self.assertCountEqual(change_types, ['AddPeopleToRoleStateChange'])
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor=self.users.crystal.pk)
        change_types = [perm.get_change_type() for perm in permissions_for_actor]
        self.assertCountEqual(change_types, ['AddPeopleToRoleStateChange'])
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor=self.users.pinoe.pk)
        change_types = [perm.get_change_type() for perm in permissions_for_actor]
        self.assertCountEqual(change_types, [])
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor=self.users.jj.pk)
        change_types = [perm.get_change_type() for perm in permissions_for_actor]
        self.assertCountEqual(change_types, [])

    def test_removing_metapermission_removes_access_to_permission(self):

        # Pinoe gives JJ the ability to add people to permission.
        self.metapermissions_data["0~individuals"] = [self.users.jj.pk]
        self.metapermission_form = MetaPermissionForm(instance=self.target_permission, 
            request=self.request, data=self.metapermissions_data)
        self.metapermission_form.is_valid()
        self.metapermission_form.save()

        # JJ can do so.  When she gives Tobin permission to add people to roles, she can.
        self.permissions_data["6~individuals"] = [self.users.tobin.pk, self.users.crystal.pk]
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.jjRequest, data=self.permissions_data)
        self.permission_form.is_valid()
        self.permission_form.save()
        self.tobinClient.add_people_to_role(role_name="defenders", people_to_add=[self.users.sully.pk])
        roles = self.commClient.get_roles()
        self.assertCountEqual(roles["defenders"], [self.users.sonny.pk, self.users.sully.pk])

        # Now Pinoe removes that ability.
        self.metapermissions_data["0~individuals"] = ""
        self.metapermission_form = MetaPermissionForm(instance=self.target_permission, 
            request=self.request, data=self.metapermissions_data)
        self.metapermission_form.is_valid()
        self.metapermission_form.save()

        # JJ no longer has the metapermission and can no longer add people to permission.
        permissions_for_actor = self.metaClient.get_permissions_associated_with_actor(
            actor=self.users.jj.pk)
        self.assertFalse(permissions_for_actor)

        self.permissions_data["6~individuals"] = [self.users.tobin.pk, self.users.crystal.pk,
            self.users.christen.pk]
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.jjRequest, data=self.permissions_data)
        self.permission_form.is_valid()
        self.permission_form.save()

        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor=self.users.christen.pk)
        change_types = [perm.get_change_type() for perm in permissions_for_actor]
        self.assertCountEqual(change_types, [])

    def test_adding_metapermission_to_nonexistent_permission(self):

        # No one currently has the specific permission "remove people from role".
        remove_permission = self.prClient.get_specific_permissions(change_type=
            Changes.Communities.RemovePeopleFromRole)
        self.assertFalse(remove_permission)

        # Pinoe tries to give JJ the ability to add or remove people from the permission
        # 'remove people from role'.

        # First, we get a mock permission to pass to the metapermission form.
        ct = ContentType.objects.get_for_model(self.instance)
        target_permission = self.prClient.get_permission_or_return_mock(
            permitted_object_id=self.instance.pk,
            permitted_object_content_type=str(ct.pk),
            permission_change_type=Changes.Communities.RemovePeopleFromRole)
        self.assertEqual(target_permission.__class__.__name__, "MockMetaPermission")

        # Then we actually update metapermissions via the form.
        self.metapermissions_data["0~individuals"] = [self.users.jj.pk]
        self.metapermission_form = MetaPermissionForm(instance=target_permission, 
            request=self.request, data=self.metapermissions_data)
        self.metapermission_form.is_valid()
        self.metapermission_form.save()

        # Now that Pinoe has done that, the specific permission exists.  
        remove_permission = self.prClient.get_specific_permissions(change_type=Changes.Communities.RemovePeopleFromRole)
        ah = PermissionsItem.objects.filter(change_type=Changes.Communities.RemovePeopleFromRole)
        self.assertEqual(len(remove_permission), 1)         

        # The metapermission Pinoe created for JJ also exists.
        self.metaClient = PermissionResourceClient(actor=self.users.pinoe, target=remove_permission[0])
        perms = self.metaClient.get_permissions_on_object(object=remove_permission[0])
        self.assertEqual(len(perms), 1)
        self.assertEqual(perms[0].get_change_type(), "AddActorToPermissionStateChange")

        # JJ can add Crystal to the permission "remove people from role".
        self.permissions_data["14~individuals"] = [self.users.crystal.pk]
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.jjRequest, data=self.permissions_data)
        self.permission_form.is_valid()
        self.permission_form.save()

        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor=self.users.crystal.pk)
        change_types = [perm.get_change_type() for perm in permissions_for_actor]
        self.assertCountEqual(change_types, ["RemovePeopleFromRoleStateChange", 
            "AddPeopleToRoleStateChange"])


@skip("Skipping forms for now")
class ResourcePermissionsFormTest(DataTestCase):

    def setUp(self):

        # Create a community
        self.commClient = CommunityClient(actor=self.users.pinoe)
        self.instance = self.commClient.create_community(name="USWNT")
        self.commClient.set_target(self.instance)

        # Add roles to community and assign members
        self.commClient.add_members([self.users.rose.pk, self.users.aubrey.pk,
            self.users.crystal.pk, self.users.jmac.pk])
        self.commClient.add_role(role_name="admin")
        self.commClient.add_people_to_role(role_name="admin", 
            people_to_add=[self.users.jmac.pk, self.users.aubrey.pk])

        # Create a forum owned by the community
        self.resourceClient = ResourceClient(actor=self.users.pinoe)
        self.resource = self.resourceClient.create_resource(name="NWSL Rocks")
        self.resourceClient.set_target(target=self.resource)
        action, result = self.resourceClient.change_owner_of_target(new_owner=self.instance)

        # Create request objects
        Request = namedtuple('Request', 'user')
        self.request = Request(user=self.users.pinoe)
        self.roseRequest = Request(user=self.users.rose)
        self.aubreyRequest = Request(user=self.users.aubrey)

        # Create separate clients
        self.roseClient = ResourceClient(actor=self.users.rose, target=self.resource)
        self.aubreyClient = ResourceClient(actor=self.users.aubrey, target=self.resource)

        # Initial form data
        self.data = {
            '0~name': Changes.Resources.AddItem,
            '0~individuals': [], '0~roles': None,
            '1~name': Changes.Resources.ChangeResourceName,
            '1~individuals': [], '1~roles': None,
            '2~name': Changes.Resources.RemoveItem,
            '2~individuals': [], '2~roles': None}

    def test_add_and_remove_actor_permission_to_resource_via_form(self):

        # Aubrey tries to change the name of the forum and fails
        action, result = self.aubreyClient.change_name(new_name="Spirit is the best NWSL team!")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.name, "NWSL Rocks")

        # Pinoe gives her permission to change the name via the individual 
        # actor field on the permission form.
        self.data['1~individuals'] = [str(self.users.aubrey.pk)]
        form = PermissionForm(instance=self.resource, request=self.request, 
            data=self.data)
        form.is_valid()
        self.assertEquals(form.cleaned_data['1~individuals'], [str(self.users.aubrey.pk)])
        form.save()

        # Now Aubrey succeeds.
        action, result = self.aubreyClient.change_name(new_name="Spirit is the best NWSL team!")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(self.resource.name, "Spirit is the best NWSL team!")

        # Pinoe takes it away again.
        self.data['1~individuals'] = []
        form = PermissionForm(instance=self.resource, request=self.request, 
            data=self.data)
        form.is_valid()
        self.assertEquals(form.cleaned_data['1~individuals'], [])
        form.save()       

        # Aubrey can no longer change the name.
        action, result = self.aubreyClient.change_name(new_name="All Hail the Washington Spirit")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.name, "Spirit is the best NWSL team!")

    def test_add_and_remove_role_permission_to_resource_via_form(self):

        # Aubrey tries to change the name of the forum and fails
        action, result = self.aubreyClient.change_name(new_name="Spirit is the best NWSL team!")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.name, "NWSL Rocks")

        # Pinoe gives her permission to change the name via the admin
        # role field on the permission form.
        self.data['1~roles'] = ["admin"]
        form = PermissionForm(instance=self.resource, request=self.request, 
            data=self.data)
        form.is_valid()
        self.assertEquals(form.cleaned_data['1~roles'], ["admin"])
        form.save()

        # Now Aubrey succeeds, but Rose does not.
        action, result = self.roseClient.change_name(new_name="Spirit is awesome!")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.name, "NWSL Rocks")        
        action, result = self.aubreyClient.change_name(new_name="Spirit is the best NWSL team!")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(self.resource.name, "Spirit is the best NWSL team!")

        # Pinoe takes it away again.
        self.data['1~roles'] = []
        form = PermissionForm(instance=self.resource, request=self.request, 
            data=self.data)
        form.is_valid()
        self.assertEquals(form.cleaned_data['1~roles'], [])
        form.save()

        # Aubrey can no longer change the name.
        action, result = self.aubreyClient.change_name(new_name="#SpiritSquad")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.name, "Spirit is the best NWSL team!")


class ResolutionFieldTest(DataTestCase):

    def setUp(self):

        # Create users
        self.nonmember_user = self.users.hao  # she's retired! we still love her!
        self.member_user = self.users.rose
        self.governing_user = self.users.jj
        self.roletest_user = self.users.crystal

        # Create a community
        self.commClient = CommunityClient(actor=self.users.pinoe)
        self.instance = self.commClient.create_community(name="USWNT")
        self.commClient.set_target(self.instance)

        # Make community self-owned
        self.commClient.change_owner_of_target(new_owner=self.instance)

        # Make separate clients for Hao, Crystal, JJ
        self.haoClient = CommunityClient(actor=self.users.hao, target=self.instance)
        self.roseClient = CommunityClient(actor=self.users.rose, target=self.instance)
        self.jjClient = CommunityClient(actor=self.users.jj, target=self.instance)
        self.crystalClient = CommunityClient(actor=self.users.crystal, target=self.instance)

        # Create request objects
        Request = namedtuple('Request', 'user')
        self.request = Request(user=self.users.pinoe)
        self.haoRequest = Request(user=self.users.hao)
        self.roseRequest = Request(user=self.users.rose)
        self.jjRequest = Request(user=self.users.jj)
        self.crystalRequest = Request(user=self.users.crystal)

        # Add members to community
        self.commClient.add_members([self.users.jj.pk, self.users.crystal.pk, 
            self.users.rose.pk])

        # Add a role to community and assign relevant members
        action, result = self.commClient.add_role(role_name="midfielders")
        self.commClient.add_people_to_role(role_name="midfielders", 
            people_to_add=[self.users.pinoe.pk, self.users.rose.pk])

        # Create permissions client
        self.prc = PermissionResourceClient(actor=self.users.pinoe, target=self.instance)

        # Create a conditions client
        self.cc = ConditionalClient(actor=self.users.pinoe)

    def test_resolution_field_correct_for_approved_action(self):

        # Add permission so any member can change the name of the group
        self.prc.add_permission(permission_roles=["members"],
            permission_type=Changes.Communities.ChangeName)

        # User changes name
        self.commClient.set_actor(actor=self.member_user)
        action, result = self.commClient.change_name(new_name="Miscellaneous Badasses")
        self.assertEquals(action.status, "implemented")

        # Inspect action's resolution field
        self.assertTrue(action.resolution.is_resolved)
        self.assertTrue(action.resolution.is_approved)
        self.assertEquals(action.resolution.approved_through, "specific")
        self.assertFalse(action.resolution.conditions)

    def test_resolution_field_correct_for_rejected_action(self):

        # Add permission so any member can change the name of the group
        self.prc.add_permission(permission_roles=["members"],
            permission_type=Changes.Communities.ChangeName)

        # Non-member user changes name
        self.commClient.set_actor(actor=self.nonmember_user)
        action, result = self.commClient.change_name(new_name="Miscellaneous Badasses")
        self.assertEquals(action.status, "rejected")

        # Inspect action's resolution field
        self.assertTrue(action.resolution.is_resolved)
        self.assertFalse(action.resolution.is_approved)
        self.assertFalse(action.resolution.conditions)

    def test_resolution_field_approved_through(self):
        
        # Pinoe can make JJ a governor because she has a foundational permission
        action, result = self.commClient.add_governor(governor_pk=self.users.jj.pk)
        self.assertEquals(action.status, "implemented")
        self.assertTrue(action.resolution.is_resolved)
        self.assertTrue(action.resolution.is_approved)
        self.assertEquals(action.resolution.approved_through, "foundational")

        # JJ can change the name of the group because she has a governing permission.        
        action, result = self.jjClient.change_name(new_name="Julie Ertz and Her Sidekicks")
        self.assertEquals(action.status, "implemented")
        self.assertTrue(action.resolution.is_resolved)
        self.assertTrue(action.resolution.is_approved)
        self.assertEquals(action.resolution.approved_through, "governing")

        # Crystal can change the name of the group because she has a specific permission.
        self.prc.add_permission(permission_actors=[self.users.crystal.pk],
            permission_type=Changes.Communities.ChangeName)
        action, result = self.crystalClient.change_name(new_name="Crystal Dunn and Her Sidekicks")
        self.assertEquals(action.status, "implemented")
        self.assertTrue(action.resolution.is_resolved)
        self.assertTrue(action.resolution.is_approved)
        self.assertEquals(action.resolution.approved_through, "specific")

    def test_resolution_field_for_role_for_specific_permission(self):

        # Add permission so any member can change the name of the group
        self.prc.add_permission(permission_roles=["members"],
            permission_type=Changes.Communities.ChangeName)

        # When they change the name, the resolution role field shows the role
        action, result = self.roseClient.change_name(new_name="Best Team")
        self.assertTrue(action.resolution.is_approved)
        self.assertEquals(action.resolution.specific_status, "approved")
        self.assertEquals(action.resolution.approved_through, "specific")
        self.assertEquals(action.resolution.approved_role, "members")

    def test_resolution_field_for_role_for_governing_permission(self):

        # Pinoe makes a governing role
        action, result = self.commClient.add_governor_role(governor_role="midfielders")
        action, result = self.roseClient.change_name(new_name="Best Team")
        self.assertEquals(action.resolution.approved_through, "governing")
        self.assertEquals(action.resolution.governing_status, "approved")
        self.assertEquals(action.resolution.approved_role, "midfielders")

    def test_resolution_field_for_individual_with_specific_permission(self):

        # Add permission so a specific person can change the name of the group
        self.prc.add_permission(permission_actors=[self.users.rose.pk],
            permission_type=Changes.Communities.ChangeName)

        # When they change the name, the resolution role field shows no role
        action, result = self.roseClient.change_name(new_name="Best Team")
        self.assertTrue(action.resolution.is_approved)
        self.assertEquals(action.resolution.approved_through, "specific")
        self.assertFalse(action.resolution.approved_role)

    def test_resolution_field_captures_conditional_info(self):

        # Pinoe sets a permission on the community that any 'member' can change the name.
        action, permission = self.prc.add_permission(permission_roles=["members"],
            permission_type=Changes.Communities.ChangeName)

        # But then she adds a condition that someone needs to approve a name change 
        # before it can go through. 
        self.prc.add_condition_to_permission(permission_pk=permission.pk, condition_type="approvalcondition")

        # (Since no specific permission is set on the condition, "approving" it 
        # requirest foundational or governing authority to change.  So only Pinoe 
        # can approve.)

        # HAO tries to change the name and fails because she is not a member.  The
        # condition never gets triggered.
        action, result = self.haoClient.change_name(new_name="Let's go North Carolina!")
        self.assertEquals(action.status, "rejected")
        self.assertTrue(action.resolution.is_resolved)
        self.assertFalse(action.resolution.is_approved)
        self.assertFalse(action.resolution.conditions)

        # Rose tries to change the name and has to wait for approval.
        rose_action, result = self.roseClient.change_name(new_name="Friends <3")
        self.assertEquals(rose_action.status, "waiting")
        self.assertEquals(rose_action.resolution.specific_status, "waiting")
        self.assertFalse(rose_action.resolution.is_resolved)
        self.assertFalse(rose_action.resolution.is_approved)
        self.assertTrue(rose_action.resolution.conditions)

        # Pinoe approves Rose's name change.
        condition_item = self.cc.get_condition_item_given_action_and_source(
            action_pk=rose_action.pk, source_id="perm_"+str(permission.pk))
        acc = ApprovalConditionClient(target=condition_item, actor=self.users.pinoe)
        action, result = acc.approve()
        self.assertEquals(action.status, "implemented")

        # Rose's action is implemented
        rose_action.refresh_from_db()
        self.assertEquals(rose_action.status, "implemented")
        self.assertTrue(rose_action.resolution.is_resolved)
        self.assertTrue(rose_action.resolution.is_approved)
        self.assertEquals(rose_action.resolution.approved_condition, "approvalcondition")
        self.instance = self.commClient.get_community(community_pk=str(self.instance.pk))
        self.assertEquals(self.instance.name, "Friends <3")

        # Rose tries to change the name again.  This time Pinoe rejects it, for Pinoe is fickle. 
        rose_action, result = self.roseClient.change_name(new_name="BEST Friends <3")
        condition_item = self.cc.get_condition_item_given_action_and_source(
            action_pk=rose_action.pk, source_id="perm_"+str(permission.pk))
        acc = ApprovalConditionClient(target=condition_item, actor=self.users.pinoe)
        action, result = acc.reject()
        rose_action.refresh_from_db()
        self.assertEquals(rose_action.status, "rejected")
        self.assertEquals(self.instance.name, "Friends <3")
        self.assertTrue(rose_action.resolution.is_resolved)
        self.assertFalse(rose_action.resolution.is_approved)

        
class ConfigurablePermissionTest(DataTestCase):

    def setUp(self):

        # Create a community & client
        self.commClient = CommunityClient(actor=self.users.pinoe)
        self.instance = self.commClient.create_community(name="USWNT")
        self.commClient.set_target(self.instance)

        # Add roles to community and assign members
        self.commClient.add_members([self.users.rose.pk, self.users.tobin.pk,
            self.users.christen.pk, self.users.crystal.pk, self.users.jmac.pk,
            self.users.aubrey.pk, self.users.sonny.pk, self.users.sully.pk,
            self.users.jj.pk])
        self.commClient.add_role(role_name="forwards")
        self.commClient.add_role(role_name="spirit players")

        # Make separate clients for other users.
        self.tobinClient = CommunityClient(actor=self.users.tobin, target=self.instance)
        self.roseClient = CommunityClient(actor=self.users.rose, target=self.instance)
        self.sonnyClient = CommunityClient(actor=self.users.sonny, target=self.instance)

        # Create permission client for Pinoe
        self.permClient = PermissionResourceClient(actor=self.users.pinoe, target=self.instance)

        # Create request objects
        Request = namedtuple('Request', 'user')
        self.request = Request(user=self.users.pinoe)

    def test_configurable_permission(self):

        # Pinoe configures a position so that only Rose can add people to the Spirit Players role
        # and not the Forwards role
        self.permClient.add_permission(
            permission_type=Changes.Communities.AddPeopleToRole,
            permission_actors=[self.users.rose.pk],
            permission_configuration={"role_name": "spirit players"})

        # Rose can add Aubrey to to the Spirit Players role
        action, result = self.roseClient.add_people_to_role(role_name="spirit players", 
            people_to_add=[self.users.aubrey.pk])
        roles = self.commClient.get_roles()
        self.assertEquals(roles["spirit players"], [self.users.aubrey.pk])
        
        # Rose cannot add Christen to the forwards role
        self.roseClient.add_people_to_role(role_name="forwards", people_to_add=[self.users.christen.pk])
        roles = self.commClient.get_roles()
        self.assertEquals(roles["forwards"], [])

    @skip("Skipping forms for now")
    def test_configurable_permission_via_form(self):

        # Create initial data to mess with
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request)
        self.data = {}
        for field_name, field in self.permission_form.fields.items():
            self.data[field_name] = field.initial

        # Update form to add configurable permission
        self.data["6~individuals"] = [self.users.rose.pk]
        self.data["6~configurablefield~role_name"] = 'spirit players'

        # Now re-create and save form
        self.permission_form = PermissionForm(instance=self.instance, request=self.request,
            data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()

        # Rose can add Aubrey to to the Spirit Players role
        action, result = self.roseClient.add_people_to_role(role_name="spirit players", 
            people_to_add=[self.users.aubrey.pk])
        roles = self.commClient.get_roles()
        self.assertEquals(roles["spirit players"], [self.users.aubrey.pk])
        
        # Rose cannot add Christen to the forwards role
        self.roseClient.add_people_to_role(role_name="forwards", people_to_add=[self.users.christen.pk])
        roles = self.commClient.get_roles()
        self.assertEquals(roles["forwards"], [])

        # Update permission to allow the reverse
        self.data["6~configurablefield~role_name"] = 'forwards'
        self.permission_form = PermissionForm(instance=self.instance, request=self.request,
            data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()

        # Rose cannot add Sully to the Spirit Players role
        action, result = self.roseClient.add_people_to_role(role_name="spirit players", 
            people_to_add=[self.users.sully.pk])
        roles = self.commClient.get_roles()
        self.assertEquals(roles["spirit players"], [self.users.aubrey.pk])
        
        # But she can add Tobin to the forwards role
        self.roseClient.add_people_to_role(role_name="forwards", people_to_add=[self.users.tobin.pk])
        roles = self.commClient.get_roles()
        self.assertEquals(roles["forwards"], [self.users.tobin.pk])

    def test_configurable_metapermission(self):

        # NOTE: This broke my brain a little.  See platform to dos doc for a brief disquisition on 
        # the four types of potential configurable metapermissions.

        # Pinoe creates a role called 'admins' in community USWNT and adds Tobin to the role. She also
        # adds Rose to the 'spirit players' role.
        self.commClient.add_role(role_name="admins")
        self.commClient.add_people_to_role(role_name="admins", people_to_add=[self.users.tobin.pk])
        self.commClient.add_people_to_role(role_name="spirit players", people_to_add=[self.users.rose.pk])

        # Pinoe creates a configured permission where people with role 'admins', as well as the role 
        # 'spirit players', can add people to the role 'forwards'.
        action, permission = self.permClient.add_permission(
            permission_type=Changes.Communities.AddPeopleToRole,
            permission_roles=["admins", "spirit players"],
            permission_configuration={"role_name": "forwards"})
        self.assertCountEqual(permission.roles.role_list, ["admins", "spirit players"]) 

        # We test that Rose, in the role Spirit Players, can add JMac to forwards, and that 
        # Tobin, in the role admins, can add Christen to forwards.
        self.roseClient.add_people_to_role(role_name="forwards", people_to_add=[self.users.jmac.pk])
        self.tobinClient.add_people_to_role(role_name="forwards", people_to_add=[self.users.christen.pk])
        roles = self.commClient.get_roles()
        self.assertCountEqual(roles["forwards"], [self.users.jmac.pk, self.users.christen.pk])

        # Pinoe then creates a configured metapermission on that configured permission that allows
        # JJ to remove the role 'spirit players' but not admins.
        self.metaPermClient = PermissionResourceClient(actor=self.users.pinoe, target=permission)
        self.metaPermClient.add_permission(
            permission_type=Changes.Permissions.RemoveRoleFromPermission,
            permission_actors=[self.users.jj.pk],
            permission_configuration={"role_name": "spirit players"})

        # JJ tries to remove both.  She is successful in removing spirit players but not admins.
        self.jjPermClient = PermissionResourceClient(actor=self.users.jj, target=permission)
        self.jjPermClient.remove_role_from_permission(role_name="admins", permission_pk=permission.pk)
        self.jjPermClient.remove_role_from_permission(role_name="spirit players", permission_pk=permission.pk)
        permission.refresh_from_db()
        self.assertCountEqual(permission.roles.role_list, ["admins"])        

        # We check again: Tobin, in the admin role, can add people to forwards, but 
        # Rose, in the spirit players, can no longer add anyone to forwards.
        self.tobinClient.add_people_to_role(role_name="forwards", people_to_add=[self.users.tobin.pk])
        self.roseClient.add_people_to_role(role_name="forwards", people_to_add=[self.users.pinoe.pk])
        roles = self.commClient.get_roles()
        self.assertCountEqual(roles["forwards"], [self.users.jmac.pk, self.users.christen.pk, self.users.tobin.pk])

    @skip("Skipping forms for now")
    def test_configurable_metapermission_via_form(self):
        '''Duplicates above test but does the configurable metapermission part via form.'''

        # Setup (copied from above)
        self.commClient.add_role(role_name="admins")
        self.commClient.add_people_to_role(role_name="admins", people_to_add=[self.users.tobin.pk])
        self.commClient.add_people_to_role(role_name="spirit players", people_to_add=[self.users.rose.pk])
        action, target_permission = self.permClient.add_permission(
            permission_type=Changes.Communities.AddPeopleToRole,
            permission_roles=["admins", "spirit players"],
            permission_configuration={"role_name": "forwards"}) 
        self.roseClient.add_people_to_role(role_name="forwards", people_to_add=[self.users.jmac.pk])
        self.tobinClient.add_people_to_role(role_name="forwards", people_to_add=[self.users.christen.pk])

        # Pinoe creates configured metapermission on permission that allows JJ to remove the 
        # role 'spirit players' but not the role 'admins'
        self.metaPermClient = PermissionResourceClient(actor=self.users.pinoe, target=target_permission)
        self.metapermissions_data = {}
        permissions = self.metaPermClient.get_settable_permissions(return_format="permission_object")
        for count, permission in enumerate(permissions):
            self.metapermissions_data[str(count) + "~" + "name"] = permission.get_change_type()
            self.metapermissions_data[str(count) + "~" + "roles"] = []
            self.metapermissions_data[str(count) + "~" + "individuals"] = []
            for field in permission.get_configurable_fields():
                self.metapermissions_data['%s~configurablefield~%s' % (count, field)] = ""
        self.metapermissions_data["5~configurablefield~role_name"] = "spirit players"
        self.metapermissions_data["5~individuals"] = [self.users.jj.pk]

        self.metapermission_form = MetaPermissionForm(request=self.request, instance=target_permission,
            data=self.metapermissions_data)
        self.metapermission_form.is_valid()
        self.metapermission_form.save()

        # Test that it worked (again, copied from above)
        self.jjPermClient = PermissionResourceClient(actor=self.users.jj, target=target_permission)
        action, result = self.jjPermClient.remove_role_from_permission(role_name="admins", 
            permission_pk=target_permission.pk)
        action, result = self.jjPermClient.remove_role_from_permission(role_name="spirit players", 
            permission_pk=target_permission.pk) 
        self.tobinClient.add_people_to_role(role_name="forwards", people_to_add=[self.users.tobin.pk])
        self.roseClient.add_people_to_role(role_name="forwards", people_to_add=[self.users.pinoe.pk])
        roles = self.commClient.get_roles()
        self.assertCountEqual(roles["forwards"], [self.users.jmac.pk, self.users.christen.pk, self.users.tobin.pk])


class MockActionTest(DataTestCase):

    def setUp(self):

        # Create a Community and Client and some members
        self.commClient = CommunityClient(actor=self.users.pinoe)
        self.instance = self.commClient.create_community(name="USWNT")
        self.commClient.set_target(self.instance)
        self.commClient.add_members([self.users.rose.pk, self.users.tobin.pk,
            self.users.christen.pk, self.users.aubrey.pk])

    def test_single_mock_action(self):
        
        self.commClient.mode = "mock"
        action = self.commClient.add_role(role_name="forwards")
        self.assertTrue(action.is_mock)

    def test_check_permissions_for_action_group_when_user_has_unconditional_permission(self):

        from concord.actions.utils import check_permissions_for_action_group
        self.commClient.mode = "mock"

        add_forwards_action = self.commClient.add_role(role_name="forwards")
        add_mids_action = self.commClient.add_role(role_name="midfielders")

        summary_status, log = check_permissions_for_action_group([add_forwards_action, add_mids_action])

        self.assertEquals(summary_status, "approved")
        self.assertEquals(log[0]["status"], "approved")
        self.assertEquals(log[0]["log"], "approved through governing with role None and condition None")
        self.assertEquals(log[1]["status"], "approved")
        self.assertEquals(log[1]["log"], "approved through governing with role None and condition None")

    def test_check_permissions_for_action_group_when_user_does_not_have_permission(self):

        # Pinoe sets specific permission that Tobin does not have
        self.permClient = PermissionResourceClient(actor=self.users.pinoe, target=self.instance)
        action, permission = self.permClient.add_permission(
            permission_type=Changes.Communities.AddRole,
            permission_actors=[self.users.christen.pk])

        from concord.actions.utils import check_permissions_for_action_group
        self.commClient.mode = "mock"
        self.commClient.set_actor(actor=self.users.tobin)

        add_forwards_action = self.commClient.add_role(role_name="forwards")
        add_mids_action = self.commClient.add_role(role_name="midfielders")

        summary_status, log = check_permissions_for_action_group([add_forwards_action, add_mids_action])

        self.assertEquals(summary_status, "rejected")
        self.assertEquals(log[0]["status"], "rejected")
        self.assertEquals(log[0]["log"], 'action did not meet any permission criteria')
        self.assertEquals(log[1]["status"], "rejected")
        self.assertEquals(log[1]["log"], 'action did not meet any permission criteria')

    def test_check_permissions_for_action_group_when_user_has_conditional_permission(self):

         # Pinoe sets specific permission & condition on that permission
        self.permClient = PermissionResourceClient(actor=self.users.pinoe, target=self.instance)
        action, permission = self.permClient.add_permission(
            permission_type=Changes.Communities.AddRole,
            permission_actors=[self.users.tobin.pk])
        perm_data = [ { "permission_type": Changes.Conditionals.Approve, "permission_actors": [self.users.christen.pk] } ]
        self.permClient.add_condition_to_permission(permission_pk=permission.pk, condition_type="approvalcondition", 
            permission_data=perm_data)

        from concord.actions.utils import check_permissions_for_action_group
        self.commClient.mode = "mock"
        self.commClient.set_actor(actor=self.users.tobin)

        add_forwards_action = self.commClient.add_role(role_name="forwards")
        add_mids_action = self.commClient.add_role(role_name="midfielders")

        summary_status, log = check_permissions_for_action_group([add_forwards_action, add_mids_action])

        self.assertEquals(summary_status, "waiting")
        self.assertEquals(log[0]["status"], "waiting")
        self.assertTrue("waiting on condition(s) for governing, specific" in log[0]["log"])
        self.assertEquals(log[1]["status"], "waiting")
        self.assertTrue("waiting on condition(s) for governing, specific" in log[1]["log"])


class ActionContainerTest(DataTestCase):

    def setUp(self):

        # Create a Community and Clients
        self.commClient = CommunityClient(actor=self.users.pinoe)
        self.instance = self.commClient.create_community(name="USWNT")
        self.commClient.set_target(self.instance)
        self.permClient = PermissionResourceClient(actor=self.users.pinoe, target=self.instance)
        self.actionClient = ActionClient(actor=self.users.pinoe)

        self.mock_action_list = []

        self.commClient.mode = "mock"

        # Action 1: Add some members
        self.mock_action_list.append(self.commClient.add_members([self.users.rose.pk, self.users.tobin.pk,
            self.users.christen.pk, self.users.aubrey.pk]))

        # Action 2: Add a role
        self.mock_action_list.append(self.commClient.add_role(role_name="forwards"))

        # Action 3: Add another role
        self.mock_action_list.append(self.commClient.add_role(role_name="spirit players"))

        # Action 4: Add people to first role
        self.mock_action_list.append(self.commClient.add_people_to_role(role_name="forwards", 
            people_to_add=[self.users.christen.pk, self.users.tobin.pk]))

        # Action 5: Add people to second role
        self.mock_action_list.append(self.commClient.add_people_to_role(role_name="spirit players", 
            people_to_add=[self.users.rose.pk, self.users.aubrey.pk]))

        self.commClient.mode = "default"

        # create a fake trigger action
        action, result = self.commClient.change_name(new_name="USWNT")
        self.mock_trigger_action = action

    def test_create_and_apply_container(self):

        actions = Action.objects.all()   # before container is created, only one aciton in DB (the fake trigger action)
        self.assertEquals(len(actions), 1)
        
        container, log = self.actionClient.create_action_container(action_list=self.mock_action_list,
            trigger_action=self.mock_trigger_action)

        actions = Action.objects.all()   # refresh
        self.assertEquals(len(actions), 6)
        self.assertEquals(container.status, "implemented")
        self.assertEquals(actions[1].container, container.pk)

        self.instance.refresh_from_db()
        self.assertCountEqual(self.instance.roles.get_custom_roles(), {'forwards': [self.users.christen.pk, self.users.tobin.pk], 
            'spirit players': [self.users.rose.pk, self.users.aubrey.pk]})

    def test_container_rejects_when_an_action_is_rejected(self):
        
        # remove pinoe as governor so she no longer has permission to take the mock actions
        action, result = self.commClient.remove_governor(governor_pk=self.users.pinoe.pk)

        # container is rejected
        container, log = self.actionClient.create_action_container(action_list=self.mock_action_list,
            trigger_action=self.mock_trigger_action)
        self.assertEquals(container.status, "rejected")

        # changes are not made
        self.assertEquals(self.instance.roles.get_custom_roles(), {})

    def test_container_creates_conditions_for_actions(self):

        # swap governors so Pinoe doesn't just automatically pass everything
        self.commClient.add_members([self.users.crystal.pk])
        self.commClient.add_governor(governor_pk=self.users.crystal.pk)
        action, result = self.commClient.remove_governor(governor_pk=self.users.pinoe.pk)
        self.permClient.set_actor(actor=self.users.crystal)

        # new governor, Crystal, adds specific permissions for Pinoe to take the five actions
        action, permission = self.permClient.add_permission(permission_type=Changes.Communities.AddMembers,
            permission_actors=[self.users.pinoe.pk])
        action, permission = self.permClient.add_permission(permission_type=Changes.Communities.AddRole,
            permission_actors=[self.users.pinoe.pk])
        action, permission = self.permClient.add_permission(permission_type=Changes.Communities.AddPeopleToRole,
            permission_actors=[self.users.pinoe.pk])
        # add condition to one of the permissions
        permission_data = [{ "permission_type": Changes.Conditionals.Approve, "permission_actors": [self.users.pinoe.pk] }]
        action, result = self.permClient.add_condition_to_permission(permission_pk=permission.pk, 
            condition_type="approvalcondition", condition_data={"self_approval_allowed": True}, 
            permission_data=permission_data)
        
        # now apply container/template containing Pinoe's actions
        container, log = self.actionClient.create_action_container(action_list=self.mock_action_list,
            trigger_action=self.mock_trigger_action)
        self.assertEquals(container.status, "waiting")

        # crystal gets conditions from container and approves them
        for condition in container.context.get_conditions():
            approvalClient = ApprovalConditionClient(actor=self.users.crystal, target=condition)
            approvalClient.approve()

        # retry Pinoe's actions
        container, log = self.actionClient.retry_action_container(container_pk=container.pk)
        self.assertEquals(container.status, "implemented")
        self.instance.refresh_from_db()
        self.assertCountEqual(self.instance.roles.get_custom_roles(), {'forwards': [self.users.christen.pk, self.users.tobin.pk], 
            'spirit players': [self.users.rose.pk, self.users.aubrey.pk]})        


@skip("Rethinking how membership settings are done")
class MembershipSettingsTest(DataTestCase):

    def setUp(self):

        # Create a Community and Client
        self.commClient = CommunityClient(actor=self.users.pinoe)
        self.instance = self.commClient.create_community(name="USWNT")
        self.commClient.set_target(self.instance)
        self.permClient = PermissionResourceClient(actor=self.users.pinoe, target=self.instance)
        self.templateClient = TemplateClient(actor=self.users.pinoe)

    def test_get_membership_settings(self):
        setting = self.commClient.get_membership_setting()
        self.assertEquals(setting, "no new members can join")

    def test_change_membership_setting_to_anyone_can_join(self):
        container = self.commClient.change_membership_setting(new_setting="anyone can join")
        self.commClient.refresh_target()
        setting = self.commClient.get_membership_setting()
        self.assertEquals(setting, "anyone can join")

    def test_change_membership_setting_to_anyone_can_ask(self):
        extra_data = {
            "condition_type": "approvalcondition",
            "permission_data": json.dumps({ "approve_actors" : [self.users.pinoe.pk] }) ,
            "condition_data": '{"self_approval_allowed": false}'
        }
        container = self.commClient.change_membership_setting(new_setting="anyone can ask", extra_data=extra_data)
        self.commClient.refresh_target()
        setting = self.commClient.get_membership_setting()
        self.assertEquals(setting, "anyone can ask")

    def test_change_membership_setting_to_invite_only(self):
        extra_data = {
            "permission_actors" : [self.users.pinoe.pk]
        }
        container = self.commClient.change_membership_setting(new_setting="invite only", extra_data=extra_data)
        self.commClient.refresh_target()
        setting = self.commClient.get_membership_setting()
        self.assertEquals(setting, "invite only")

    def test_change_from_anyone_can_join_to_anyone_can_ask(self):

        # start with anyone can join
        container = self.commClient.change_membership_setting(new_setting="anyone can join")

        # switch to anyone can ask
        extra_data = {
            "condition_type": "approvalcondition",
            "permission_data": json.dumps({ "approve_actors" : [self.users.pinoe.pk] }) ,
            "condition_data": '{"self_approval_allowed": false}'
        }
        container = self.commClient.change_membership_setting(new_setting="anyone can ask", extra_data=extra_data)
        self.commClient.refresh_target()
        setting = self.commClient.get_membership_setting()
        self.assertEquals(setting, "anyone can ask")

    def test_change_from_anyone_can_join_to_invite_only(self):

        # start with anyone can join
        container = self.commClient.change_membership_setting(new_setting="anyone can join")

        # switch to invite only
        extra_data = {
            "permission_actors" : [self.users.pinoe.pk]
        }
        container = self.commClient.change_membership_setting(new_setting="invite only", extra_data=extra_data)
        self.commClient.refresh_target()
        setting = self.commClient.get_membership_setting()
        self.assertEquals(setting, "invite only")

    def test_change_from_anyone_can_join_to_no_member_can_join(self):

        # start with anyone can join
        container = self.commClient.change_membership_setting(new_setting="anyone can join")

        # switch to no member can join
        container = self.commClient.change_membership_setting(new_setting="no new members can join")
        self.commClient.refresh_target()
        setting = self.commClient.get_membership_setting()
        self.assertEquals(setting, "no new members can join")

    def test_change_from_anyone_can_ask_to_invite_only(self):

        # start with anyone can ask
        extra_data = {
            "condition_type": "approvalcondition",
            "permission_data": json.dumps({ "approve_actors" : [self.users.pinoe.pk] }) ,
            "condition_data": '{"self_approval_allowed": false}'
        }
        container = self.commClient.change_membership_setting(new_setting="anyone can ask", extra_data=extra_data)

        # switch to invite only
        extra_data = {
            "permission_actors" : [self.users.pinoe.pk]
        }
        container = self.commClient.change_membership_setting(new_setting="invite only", extra_data=extra_data)
        self.commClient.refresh_target()
        setting = self.commClient.get_membership_setting()
        self.assertEquals(setting, "invite only")

    def test_change_from_anyone_can_ask_to_anyone_can_join(self):

        # start with anyone can ask
        extra_data = {
            "condition_type": "approvalcondition",
            "permission_data": json.dumps({ "approve_actors" : [self.users.pinoe.pk] }) ,
            "condition_data": '{"self_approval_allowed": false}'
        }
        container = self.commClient.change_membership_setting(new_setting="anyone can ask", extra_data=extra_data)

        # switch to anyone can join
        container = self.commClient.change_membership_setting(new_setting="anyone can join")
        self.commClient.refresh_target()
        setting = self.commClient.get_membership_setting()
        self.assertEquals(setting, "anyone can join")

    def test_change_from_anyone_can_ask_to_no_member_can_join(self):

        # start with anyone can ask
        extra_data = {
            "condition_type": "approvalcondition",
            "permission_data": json.dumps({ "approve_actors" : [self.users.pinoe.pk] }) ,
            "condition_data": '{"self_approval_allowed": false}'
        }
        container = self.commClient.change_membership_setting(new_setting="anyone can ask", extra_data=extra_data)

        # switch to no member can join
        container = self.commClient.change_membership_setting(new_setting="no new members can join")
        self.commClient.refresh_target()
        setting = self.commClient.get_membership_setting()
        self.assertEquals(setting, "no new members can join")

    def test_change_from_invite_only_to_anyone_can_ask(self):

        # start with invite only
        extra_data = {
            "permission_actors" : [self.users.pinoe.pk]
        }
        container = self.commClient.change_membership_setting(new_setting="invite only", extra_data=extra_data)

        # switch to anyone can ask
        extra_data = {
            "condition_type": "approvalcondition",
            "permission_data": json.dumps({ "approve_actors" : [self.users.pinoe.pk] }) ,
            "condition_data": '{"self_approval_allowed": false}'
        }
        container = self.commClient.change_membership_setting(new_setting="anyone can ask", extra_data=extra_data)
        self.commClient.refresh_target()
        setting = self.commClient.get_membership_setting()
        self.assertEquals(setting, "anyone can ask")

    def test_change_from_invite_only_to_anyone_can_join(self):

        # start with invite only
        extra_data = {
            "permission_actors" : [self.users.pinoe.pk]
        }
        container = self.commClient.change_membership_setting(new_setting="invite only", extra_data=extra_data)

        # switch to anyone can join
        container = self.commClient.change_membership_setting(new_setting="anyone can join")
        self.commClient.refresh_target()
        setting = self.commClient.get_membership_setting()
        self.assertEquals(setting, "anyone can join")

    def test_change_from_invite_only_to_no_member_can_join(self):

        # start with invite only
        extra_data = {
            "permission_actors" : [self.users.pinoe.pk]
        }
        container = self.commClient.change_membership_setting(new_setting="invite only", extra_data=extra_data)

        # switch to no member can join
        container = self.commClient.change_membership_setting(new_setting="no new members can join")
        self.commClient.refresh_target()
        setting = self.commClient.get_membership_setting()
        self.assertEquals(setting, "no new members can join")

    def test_update_anyone_can_ask(self):

        # start with anyone can ask
        extra_data = {
            "condition_type": "approvalcondition",
            "permission_data": json.dumps({ "approve_actors" : [self.users.pinoe.pk] }) ,
            "condition_data": '{"self_approval_allowed": false}'
        }
        container = self.commClient.change_membership_setting(new_setting="anyone can ask", extra_data=extra_data)

        # Get current permission & condition on it
        self.permissionClient = PermissionResourceClient(actor=self.users.pinoe, target=self.instance)
        permission = self.permissionClient.get_specific_permissions(change_type="concord.communities.state_changes.AddMembersStateChange")[0]
        self.assertEquals(permission.anyone, True)
        self.conditionalClient = ConditionalClient(actor=self.users.pinoe, target=permission)
        condition = self.conditionalClient.get_conditions_given_targets(target_pks=[permission.pk])[0]
        self.assertEquals(condition.condition_data.permission_data, {'approve_actors': [1]})

        # update it
        extra_data = {
            "condition_type": "approvalcondition",
            "permission_data": json.dumps({ "approve_roles" : ["forwards"] }) ,
            "condition_data": '{"self_approval_allowed": false}'
        }
        container = self.commClient.change_membership_setting(new_setting="anyone can ask", extra_data=extra_data)
        self.commClient.refresh_target()
        setting = self.commClient.get_membership_setting()
        self.assertEquals(setting, "anyone can ask")

        # Get current permission & condition on it
        self.permissionClient = PermissionResourceClient(actor=self.users.pinoe, target=self.instance)
        permission = self.permissionClient.get_specific_permissions(change_type="concord.communities.state_changes.AddMembersStateChange")[0]
        self.assertEquals(permission.anyone, True)
        self.conditionalClient = ConditionalClient(actor=self.users.pinoe, target=permission)
        condition = self.conditionalClient.get_conditions_given_targets(target_pks=[permission.pk])[0]
        self.assertEquals(condition.condition_data.permission_data, {'approve_roles': ['forwards']})

    def test_update_invite_only(self):

        # start with invite only
        extra_data = {
            "permission_actors" : [self.users.pinoe.pk]
        }
        container = self.commClient.change_membership_setting(new_setting="invite only", extra_data=extra_data)
        self.permissionClient = PermissionResourceClient(actor=self.users.pinoe, target=self.instance)
        permission = self.permissionClient.get_specific_permissions(change_type="concord.communities.state_changes.AddMembersStateChange")[0]
        self.assertEquals(permission.anyone, False)
        self.assertEquals(permission.actors.pk_list, [self.users.pinoe.pk])
        self.assertEquals(permission.roles.role_list, [])

        # update invite only
        extra_data = {
            "permission_actors" : [self.users.tobin.pk],
            "permission_roles": ["forwards"]
        }
        container = self.commClient.change_membership_setting(new_setting="invite only", extra_data=extra_data)

    def test_no_members_can_join_setting_works(self):

        setting = self.commClient.get_membership_setting()
        self.assertEquals(setting, "no new members can join")

        # people cannot add themselves
        self.commClient.set_actor(actor=self.users.crystal)
        action, result = self.commClient.add_members(member_pk_list=[self.users.crystal.pk])
        self.assertEquals(self.commClient.get_members(), [self.users.pinoe])
        
    def test_anyone_can_join_setting_works(self):

        container = self.commClient.change_membership_setting(new_setting="anyone can join")

        self.commClient.refresh_target()
        self.commClient.set_actor(actor=self.users.crystal)
        
        action, result = self.commClient.add_members(member_pk_list=[self.users.crystal.pk])
        self.permissionClient = PermissionResourceClient(actor=self.users.pinoe, target=self.instance)
        permission = self.permissionClient.get_specific_permissions(change_type="concord.communities.state_changes.AddMembersStateChange")[0]
        self.assertEquals(self.commClient.get_members(), [self.users.pinoe, self.users.crystal])

    def test_anyone_can_ask_setting_works(self):

        # use someone besides Pinoe, because her governing permission will override everything
        action, result = self.commClient.add_members(member_pk_list=[self.users.christen.pk])

        # change setting
        extra_data = {
            "condition_type": "approvalcondition",
            "permission_data": json.dumps({ "approve_actors" : [self.users.christen.pk] }) ,
            "condition_data": '{"self_approval_allowed": false}'
        }
        container = self.commClient.change_membership_setting(new_setting="anyone can ask", extra_data=extra_data)
        self.commClient.refresh_target()
        setting = self.commClient.get_membership_setting()
        self.assertEquals(setting, "anyone can ask")

        # setting works:

        self.commClient.refresh_target()
        self.commClient.set_actor(actor=self.users.crystal)
        action, result = self.commClient.add_members(member_pk_list=[self.users.crystal.pk])
        self.assertEquals(action.status, "waiting")
        self.assertEquals(self.commClient.get_members(), [self.users.pinoe, self.users.christen])

        self.commClient.set_actor(actor=self.users.christen)
        self.cc = ConditionalClient(actor=self.users.christen)
        condition = self.cc.get_condition_item_given_action(action_pk=action.pk)
        acc = ApprovalConditionClient(target=condition, actor=self.users.christen)
        acc.approve()

        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")   
        self.commClient.refresh_target() 
        self.assertEquals(self.commClient.get_members(), [self.users.pinoe, self.users.christen, self.users.crystal])

    def test_invite_only_setting_works(self):

        # use someone besides Pinoe, because her governing permission will override everything
        action, result = self.commClient.add_members(member_pk_list=[self.users.christen.pk])

        # start with invite only
        extra_data = {
            "permission_actors" : [self.users.christen.pk]
        }
        container = self.commClient.change_membership_setting(new_setting="invite only", extra_data=extra_data)

        # crystal can't initiate
        self.commClient.set_actor(actor=self.users.crystal)
        action, result = self.commClient.add_members(member_pk_list=[self.users.crystal.pk])
        self.assertEquals(action.status, "rejected")
        self.assertEquals(self.commClient.get_members(), [self.users.pinoe, self.users.christen])

        # but christen can invite her
        self.commClient.set_actor(actor=self.users.christen)
        action, result = self.commClient.add_members(member_pk_list=[self.users.crystal.pk])
        self.assertEquals(action.status, "waiting")

        # christen can't approve
        self.cc = ConditionalClient(actor=self.users.christen)
        condition = self.cc.get_condition_item_given_action(action_pk=action.pk)
        acc = ApprovalConditionClient(target=condition, actor=self.users.christen)
        acc.approve()
        self.assertEquals(action.status, "waiting")

        # but crystal can
        self.cc = ConditionalClient(actor=self.users.crystal)
        condition = self.cc.get_condition_item_given_action(action_pk=action.pk)
        acc = ApprovalConditionClient(target=condition, actor=self.users.crystal)
        acc.approve()
        action = Action.objects.get(pk=action.pk)
        self.assertEquals(action.status, "implemented")
        self.commClient.refresh_target()
        self.assertEquals(self.commClient.get_members(), [self.users.pinoe, self.users.christen, self.users.crystal])

    def test_anyone_can_ask_setting_works_after_switching_a_bunch(self):

        # use someone besides Pinoe, because her governing permission will override everything
        action, result = self.commClient.add_members(member_pk_list=[self.users.christen.pk])
        
        # switch through three other settings first, then settle on ask
        container = self.commClient.change_membership_setting(new_setting="anyone can join")
        self.commClient.refresh_target()
        extra_data = {
            "permission_actors" : [self.users.christen.pk]
        }
        container = self.commClient.change_membership_setting(new_setting="invite only", extra_data=extra_data)
        self.commClient.refresh_target()
        extra_data = {
            "condition_type": "approvalcondition",
            "permission_data": json.dumps({ "approve_actors" : [self.users.christen.pk] }) ,
            "condition_data": '{"self_approval_allowed": false}'
        }
        container = self.commClient.change_membership_setting(new_setting="anyone can ask", extra_data=extra_data)
        self.commClient.refresh_target()
        setting = self.commClient.get_membership_setting()
        self.assertEquals(setting, "anyone can ask")

        # now test the anyone can ask test (copied from above)

        self.commClient.refresh_target()
        self.commClient.set_actor(actor=self.users.crystal)
        action, result = self.commClient.add_members(member_pk_list=[self.users.crystal.pk])
        self.assertEquals(action.status, "waiting")
        self.assertEquals(self.commClient.get_members(), [self.users.pinoe, self.users.christen])

        self.commClient.set_actor(actor=self.users.christen)
        self.cc = ConditionalClient(actor=self.users.christen)
        condition = self.cc.get_condition_item_given_action(action_pk=action.pk)
        acc = ApprovalConditionClient(target=condition, actor=self.users.christen)
        acc.approve()

        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")   
        self.commClient.refresh_target() 
        self.assertEquals(self.commClient.get_members(), [self.users.pinoe, self.users.christen, self.users.crystal])


class TemplateTest(DataTestCase):

    def setUp(self):

        # Create a Community and Client
        self.commClient = CommunityClient(actor=self.users.pinoe)
        self.instance = self.commClient.create_community(name="USWNT")
        self.commClient.set_target(self.instance)
        self.permClient = PermissionResourceClient(actor=self.users.pinoe, target=self.instance)
        self.commClient.add_role(role_name="forwards")
        self.commClient.add_members([self.users.tobin.pk])
        self.commClient.add_people_to_role(role_name="forwards", people_to_add=[self.users.tobin.pk])

        self.templateClient = TemplateClient(actor=self.users.pinoe, target=self.instance)

    def test_create_invite_only_template_creates_template(self):
        template_model = template_library.create_invite_only_template()
        self.assertEquals(template_model.name, "Invite Only")

    def test_apply_invite_only_template_to_community(self):
        
        # Before applying template, Tobin (with role Forward) cannot add members
        self.commClient.set_actor(actor=self.users.tobin)
        action, result = self.commClient.add_members([self.users.christen.pk])
        self.assertEquals(action.status, "rejected")
        self.assertEquals(self.commClient.get_members(), [self.users.pinoe, self.users.tobin])

        # Pinoe applies template model to community
        supplied_fields = { "addmembers_permission_roles": ["forwards"], 
            "addmembers_permission_actors": [] }
        template_model = template_library.create_invite_only_template()
        action, container = self.templateClient.apply_template(template_model_pk=template_model.pk,
            supplied_fields=supplied_fields)
        self.assertEquals(container.status, "implemented")

        # now Tobin can add members
        action, result = self.commClient.add_members([self.users.christen.pk])
        self.assertEquals(action.status, "implemented")

        # FIXME: there's a problem with action-dependent conditions right now
        # # now Tobin can add members AND it triggers a condition & permissions set on it
        # action, result = self.commClient.add_members([self.users.christen.pk])
        # self.assertEquals(action.status, "waiting")
        # self.assertEquals(ApprovalCondition.objects.count(), 1)

        # # Tobin can't approve invite, only Christen can
        # approval_client = ApprovalConditionClient(actor=self.users.tobin, target=ApprovalCondition.objects.first())
        # action, result = approval_client.approve()
        # self.assertEquals(action.status, "rejected")
        # approval_client.set_actor(actor=self.users.christen)
        # action, result = approval_client.approve()
        # self.assertEquals(action.status, "implemented")
        # self.commClient.refresh_target()
        # self.assertEquals(self.commClient.get_members(), 
        #     [self.users.pinoe, self.users.tobin, self.users.christen])
        

class PermissionedReadTest(DataTestCase):

    def setUp(self):

        # Create a community with roles
        self.commClient = CommunityClient(actor=self.users.pinoe)
        self.instance = self.commClient.create_community(name="USWNT")
        self.commClient.set_target(self.instance)
        self.commClient.add_role(role_name="forwards")
        self.commClient.add_members([self.users.tobin.pk, self.users.rose.pk])
        self.commClient.add_people_to_role(role_name="forwards", people_to_add=[self.users.tobin.pk])

        # Create a resource and put it in the community
        self.rc = ResourceClient(actor=self.users.pinoe)
        self.resource = self.rc.create_resource(name="Go USWNT!")
        self.rc.set_target(target=self.resource)
        self.rc.change_owner_of_target(new_owner=self.instance)

        # Set the target of the permission resource client
        self.permClient = PermissionResourceClient(actor=self.users.pinoe, target=self.resource)

        # create clients for users
        self.tobinResourceClient = ResourceClient(actor=self.users.tobin, target=self.resource)
        self.roseResourceClient = ResourceClient(actor=self.users.rose, target=self.resource)

    def test_unconfigured_permission_read(self):
        # Only people with role "forwards" can view the resource
        action, result = self.permClient.add_permission(permission_type=Changes.Actions.ViewPermission, 
            permission_roles=["forwards"])

        # User Rose without role 'forwards' can't see object
        action, result = self.roseResourceClient.get_target_data()
        self.assertEquals(action.status, "rejected")

        # User Tobin with role 'forwards' can see object
        action, result = self.tobinResourceClient.get_target_data()
        self.assertEquals(action.status, "implemented")
        self.assertEquals(result, 
            { 'id': 1,
            "item": [],
            'foundational_permission_enabled': False, 
            'governing_permission_enabled': True, 
            'name': 'Go USWNT!', 
            'owner': "USWNT"})

    def test_can_configure_readable_fields(self):
        # Only people with role "forwards" can view the resource field "name" and resource "id"
        action, result = self.permClient.add_permission(permission_type=Changes.Actions.ViewPermission, 
            permission_roles=["forwards"], permission_configuration={"fields_to_include": ["name", "id"]})

        # They try to get other fields, get error
        action, result = self.tobinResourceClient.get_target_data(fields_to_include=["owner"])
        self.assertEquals(action.status, "rejected")
        self.assertTrue("Cannot view fields owner" in action.resolution.log)
        
        # They try to get the right field, success
        action, result = self.tobinResourceClient.get_target_data(fields_to_include=["name"])
        self.assertEquals(action.status, "implemented")
        self.assertEquals(result, {'name': 'Go USWNT!'})

        # They try to get two fields at once, success
        action, result = self.tobinResourceClient.get_target_data(fields_to_include=["name", "id"])
        self.assertEquals(action.status, "implemented")
        self.assertEquals(result, {'name': 'Go USWNT!', "id": 1})

        # They try to get one allowed field and one unallowed field, error
        action, result = self.tobinResourceClient.get_target_data(fields_to_include=["name", "owner"])
        self.assertEquals(action.status, "rejected")
        self.assertTrue("Cannot view fields owner" in action.resolution.log)

        # They try to get a nonexistent field, error
        result = self.tobinResourceClient.get_target_data(fields_to_include=["potato"])
        self.assertTrue(result, "Attempting to view field(s) potato that are not on target Resource object (1)")

    def test_multiple_readpermissions(self):

        # Permission 1: user Tobin can only see field "name"
        action, result = self.permClient.add_permission(permission_type=Changes.Actions.ViewPermission, 
            permission_actors=[self.users.tobin.pk], 
            permission_configuration={"fields_to_include": ["name"]})

        # Permission 2: user Rose can only see field "owner"
        action, result = self.permClient.add_permission(permission_type=Changes.Actions.ViewPermission, 
            permission_actors=[self.users.rose.pk], 
            permission_configuration={"fields_to_include": ["owner"]})

        # Tobin can see name but not owner
        action, result = self.tobinResourceClient.get_target_data(fields_to_include=["name"])
        self.assertEquals(action.status, "implemented")
        self.assertEquals(result, {'name': 'Go USWNT!'})
        action, result = self.tobinResourceClient.get_target_data(fields_to_include=["owner"])
        self.assertEquals(action.status, "rejected")
        self.assertTrue("Cannot view fields owner" in action.resolution.log)

        # Rose can see owner but not name
        action, result = self.roseResourceClient.get_target_data(fields_to_include=["owner"])
        self.assertEquals(action.status, "implemented")
        self.assertEquals(result, {'owner': 'USWNT'})
        action, result = self.roseResourceClient.get_target_data(fields_to_include=["name"])
        self.assertEquals(action.status, "rejected")
        self.assertTrue("Cannot view fields name" in action.resolution.log)


class CommentTest(DataTestCase):

    def setUp(self):

        # Create a community with roles
        self.commClient = CommunityClient(actor=self.users.pinoe)
        self.instance = self.commClient.create_community(name="USWNT")
        self.commClient.set_target(self.instance)
        self.commClient.add_role(role_name="forwards")
        self.commClient.add_members([self.users.tobin.pk, self.users.rose.pk])
        self.commClient.add_people_to_role(role_name="forwards", people_to_add=[self.users.tobin.pk])

        # Create a resource and put it in the community
        self.rc = ResourceClient(actor=self.users.pinoe)
        self.resource = self.rc.create_resource(name="Go USWNT!")
        self.rc.set_target(target=self.resource)
        self.rc.change_owner_of_target(new_owner=self.instance)

        # Create comment client
        self.commentClient = CommentClient(actor=self.users.pinoe, target=self.resource)

    def test_add_comment(self):

        # we start off with no comments
        comments = list(self.commentClient.get_all_comments_on_target())
        self.assertEquals(comments, [])

        # we add a comment and now we have one on the target
        self.commentClient.add_comment(text="This is a new comment")
        comments = self.commentClient.get_all_comments_on_target()
        self.assertEquals(comments.first().text, "This is a new comment")

    def test_edit_comment(self):

        # we start off by adding a comment
        self.commentClient.add_comment(text="This is a new comment")
        comments = self.commentClient.get_all_comments_on_target()
        self.assertEquals(comments.first().text, "This is a new comment")

        # when we edit it, the text changes
        self.commentClient.edit_comment(pk=comments.first().pk, text="This is an edited comment")
        comments = self.commentClient.get_all_comments_on_target()  # refresh
        self.assertEquals(comments.first().text, "This is an edited comment")

    def test_delete_comment(self):

        # we start off by adding a comment
        self.commentClient.add_comment(text="This is a new comment")
        comments = self.commentClient.get_all_comments_on_target()
        self.assertEquals(comments.first().text, "This is a new comment")

        # when we delete it, it disappears
        self.commentClient.delete_comment(pk=comments.first().pk)
        comments = self.commentClient.get_all_comments_on_target()  # refresh
        self.assertEquals(list(comments), [])


