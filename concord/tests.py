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

from concord.resources.client import ResourceClient
from concord.permission_resources.client import PermissionResourceClient, TemplateClient
from concord.conditionals.client import (ApprovalConditionClient, VoteConditionClient, 
    PermissionConditionalClient, CommunityConditionalClient)
from concord.communities.client import CommunityClient

from concord.communities.forms import RoleForm
from concord.permission_resources.forms import PermissionForm, MetaPermissionForm
from concord.conditionals.forms import ConditionSelectionForm, conditionFormDict
from concord.actions.models import Action  # NOTE: For testing action status later, do we want a client?
from concord.actions.state_changes import Changes
from concord.permission_resources import templates
from concord.permission_resources.models import PermissionsItem, Template
from concord.conditionals.models import ApprovalCondition, ConditionTemplate
from concord.resources.models import Resource, Item


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
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")
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
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "rejected")

        # Pinoe adds a permission on the permission which Tobin does have.
        self.prc.set_target(target=permission)
        action, rec_permission = self.prc.add_permission(permission_type=Changes.Permissions.AddPermission,
            permission_actors=[self.users.tobin.pk])
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")

        # Tobin still cannot make the original change because she does not have *that* permission.
        action, item = tobin_rc.add_item(item_name="Tobin's item")
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "rejected")
        
        # But Tobin CAN make the second-level change.
        tobin_prc = PermissionResourceClient(actor=self.users.tobin, target=permission)
        action, permission = tobin_prc.add_permission(permission_type=Changes.Permissions.AddPermission,
            permission_actors=[self.users.rose.pk])        
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")

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
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")
        self.assertEquals(item.name, "Christen Test")  

        tobin_rc = ResourceClient(actor=self.users.tobin, target=resource)
        action, item = tobin_rc.add_item(item_name="Tobin Test")
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")
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
        self.cc = PermissionConditionalClient(actor=self.users.pinoe)
        self.cc.set_target(target=permission)
        self.cc.add_condition(condition_type="approvalcondition")

        # The first (Christen) is accepted while the second (Tobin) has to wait

        christen_rc = ResourceClient(actor=self.users.christen, target=resource)
        action, item = christen_rc.add_item(item_name="Christen Test")
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")
        self.assertEquals(item.name, "Christen Test")  

        tobin_rc = ResourceClient(actor=self.users.tobin, target=resource)
        action, item = tobin_rc.add_item(item_name="Tobin Test")
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "waiting")
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
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")
        self.assertEquals(item.name, "JJ Ertz's Test")  

        # Pinoe toggles the permission
        action, result = self.prc.change_inverse_field_of_permission(change_to=True, 
            permission_pk=permission.pk)
        permission.refresh_from_db()
        self.assertEquals(permission.inverse, True)

        # JJ can no longer use the permission, but anyone who is not JJ can

        action, item = jj_rc.add_item(item_name="JJ Test #2")
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "rejected")
        self.assertEquals(item, None) 

        tobin_rc = ResourceClient(actor=self.users.tobin, target=resource)
        action, item = tobin_rc.add_item(item_name="Tobin Test")
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")
        self.assertEquals(item.name, "Tobin Test")


class ConditionalsTest(DataTestCase):

    def setUp(self):
        self.cc = PermissionConditionalClient(actor=self.users.pinoe)
        self.rc = ResourceClient(actor=self.users.pinoe)
        self.prc = PermissionResourceClient(actor=self.users.pinoe)
        self.target = self.rc.create_resource(name="Go USWNT!")
        from concord.resources.state_changes import ChangeResourceNameStateChange
        self.action = Action.objects.create(actor=self.users.sully, target=self.target,
            change=ChangeResourceNameStateChange(new_name="Go Spirit!"))

    def test_create_vote_conditional(self):
        default_vote = self.cc.create_vote_condition(action=self.action)
        self.assertEquals(default_vote.publicize_votes(), False)
        public_vote = self.cc.create_vote_condition(publicize_votes=True, action=self.action)
        self.assertEquals(public_vote.publicize_votes(), True)

    def test_add_vote_to_vote_conditional(self):
        default_vote = self.cc.create_vote_condition(action=self.action)
        self.assertEquals(default_vote.get_current_results(), 
            { "yeas": 0, "nays": 0, "abstains": 0 })
        default_vote.vote(vote="yea")
        self.assertEquals(default_vote.get_current_results(), 
            { "yeas": 1, "nays": 0, "abstains": 0 })
        # Can't vote twice!
        default_vote.vote(vote="nay")
        self.assertEquals(default_vote.get_current_results(), 
            { "yeas": 1, "nays": 0, "abstains": 0 })
    
    def test_add_permission_to_vote_conditional(self):

        # Pinoe creates a vote condition and sets permissions on it

        default_vote = self.cc.create_vote_condition(action=self.action)
        self.prc.set_target(target=default_vote.target)  # FIXME: this is hacky
        action, vote_permission = self.prc.add_permission(permission_type=Changes.Conditionals.AddVote,
            permission_actors=[self.users.crystal.pk])
        action2, vote_permission2 = self.prc.add_permission(permission_type=Changes.Conditionals.AddVote,
            permission_actors=[self.users.jmac.pk])   

        # Now Crystal and JMac can vote but Rose can't
        self.cc = PermissionConditionalClient(actor=self.users.crystal)
        default_vote = self.cc.get_vote_condition_as_client(pk=default_vote.target.pk)
        action,result = default_vote.vote(vote="yea")
        self.assertDictEqual(default_vote.get_current_results(), 
            { "yeas": 1, "nays": 0, "abstains": 0 })
        self.cc = PermissionConditionalClient(actor=self.users.jmac)
        default_vote = self.cc.get_vote_condition_as_client(pk=default_vote.target.pk)
        default_vote.vote(vote="abstain")
        self.assertDictEqual(default_vote.get_current_results(), 
            { "yeas": 1, "nays": 0, "abstains": 1})
        self.cc = PermissionConditionalClient(actor=self.users.rose)
        default_vote = self.cc.get_vote_condition_as_client(pk=default_vote.target.pk)
        default_vote.vote(vote="abstain")
        self.assertDictEqual(default_vote.get_current_results(), 
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
        # approval (without specifying permissions, so it uses the default).
        self.cc.set_target(target=permission)
        self.cc.add_condition(condition_type="approvalcondition")

        # Now when Sonny tries to add an item she is flat out rejected
        self.rc.set_actor(actor=self.users.sonny)
        self.rc.set_target(target=resource)
        action, item = self.rc.add_item(item_name="Saucy Sonny's item")
        self.assertEquals(resource.get_items(), [])
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "rejected")

        # When Rose tries to add an item it is stuck waiting
        self.rc.set_actor(actor=self.users.rose)
        rose_action, item = self.rc.add_item(item_name="Rose's item")
        self.assertEquals(resource.get_items(), [])
        self.assertEquals(Action.objects.get(pk=rose_action.pk).resolution.status, "waiting")

        # Get the conditional action
        conditional_action = self.cc.get_condition_item_given_action(action_pk=rose_action.pk)

        # Sonny tries to approve it and fails.  Sonny you goof.
        acc = ApprovalConditionClient(target=conditional_action, actor=self.users.sonny)
        action, result = acc.approve()
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "rejected")
        self.assertEquals(resource.get_items(), [])

        # Now Pinoe approves it
        acc.set_actor(actor=self.users.pinoe)
        action, result = acc.approve()
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")
    
        # And Rose's item has been added
        self.assertEquals(Action.objects.get(pk=rose_action.pk).resolution.status, "implemented")
        self.assertEquals(resource.get_items(), ["Rose's item"])

        
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
        self.cc.set_target(target=permission)
        self.cc.add_condition(condition_type="approvalcondition",
            permission_data=json.dumps([{ "approve_actors": [self.users.crystal.pk] }]))

        # When Rose tries to add an item it is stuck waiting
        self.rc.set_actor(actor=self.users.rose)
        self.rc.set_target(target=resource)
        rose_action, item = self.rc.add_item(item_name="Rose's item")
        self.assertEquals(resource.get_items(), [])
        self.assertEquals(Action.objects.get(pk=rose_action.pk).resolution.status, "waiting")

        # Get the conditional action
        conditional_action = self.cc.get_condition_item_given_action(action_pk=rose_action.pk)

       # Now Crystal approves it
        acc = ApprovalConditionClient(target=conditional_action, actor=self.users.crystal)
        action, result = acc.approve()
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")
    
        # And Rose's item has been added
        self.assertEquals(Action.objects.get(pk=rose_action.pk).resolution.status, "implemented")
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
        self.cc.set_target(target=permission)
        self.cc.add_condition(condition_type="approvalcondition",
            permission_data=json.dumps([{ "approve_actors": [self.users.crystal.pk] }, 
            {"reject_actors": [self.users.sully.pk] }]))


                # {'permission_type': Changes.Conditionals.Approve, 
                # 'permission_actors': ,
                # 'permission_roles': [],
                # 'permission_configuration': '{}'},
                # {'permission_type': Changes.Conditionals.Reject, 
                # 'permission_actors': ,
                # 'permission_roles': [],
                # 'permission_configuration': '{}'}
                # ]))

        # When Rose tries to add an item, Crystal can approve it
        self.rc.set_actor(actor=self.users.rose)
        self.rc.set_target(target=resource)
        rose_action_one, item = self.rc.add_item(item_name="Rose's first item")
        conditional_action = self.cc.get_condition_item_given_action(action_pk=rose_action_one.pk)
        acc = ApprovalConditionClient(target=conditional_action, actor=self.users.crystal)
        action, result = acc.approve()
    
        # When Rose tries to add an item, Andi Sullivan can reject it
        rose_action_two, item = self.rc.add_item(item_name="Rose's second item")
        conditional_action = self.cc.get_condition_item_given_action(action_pk=rose_action_two.pk)
        acc = ApprovalConditionClient(target=conditional_action, actor=self.users.sully)
        action, result = acc.reject()

        # We see Rose's first item but not her second has been added
        self.assertEquals(Action.objects.get(pk=rose_action_one.pk).resolution.status, "implemented")
        self.assertEquals(Action.objects.get(pk=rose_action_two.pk).resolution.status, "rejected")
        self.assertEquals(resource.get_items(), ["Rose's first item"])

        # Rose tries one more time - Andi can't approve and Crystal can't reject, so the action is waiting
        rose_action_three, item = self.rc.add_item(item_name="Rose's third item")        
        conditional_action = self.cc.get_condition_item_given_action(action_pk=rose_action_three.pk)
        acc = ApprovalConditionClient(target=conditional_action, actor=self.users.crystal)
        action, result = acc.reject()
        acc = ApprovalConditionClient(target=conditional_action, actor=self.users.sully)
        action, result = acc.approve()
        self.assertEquals(Action.objects.get(pk=rose_action_three.pk).resolution.status, "waiting")

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

        # Create PermissionConditionalClient
        self.pcc = PermissionConditionalClient(actor=self.users.pinoe, target=self.target_permission)

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
        self.assertEquals(Action.objects.get(pk=tobin_action.pk).resolution.status, "waiting")

        # Get the condition item created by action
        self.cc = PermissionConditionalClient(actor=self.users.pinoe)
        condition = self.cc.get_condition_item_given_action(action_pk=tobin_action.pk)

        # Now Rose approves it
        acc = ApprovalConditionClient(target=condition, actor=self.users.rose)
        action, result = acc.approve()
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")

        # And Tobin's item has been added
        self.assertEquals(Action.objects.get(pk=tobin_action.pk).resolution.status, "implemented")
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
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")
        self.assertEquals(community.name, "A Newly Named Community")

    def test_reject_change_name_of_community_from_nongovernor(self):
        community = self.commClient.create_community(name="A New Community")
        self.commClient.set_target(target=community)
        self.commClient.set_actor(actor=self.users.jj)
        action, result = self.commClient.change_name(new_name="A Newly Named Community")
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "rejected")
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
        self.assertEquals(Action.objects.get(pk=new_action.pk).resolution.status, "implemented")
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
        self.assertEquals(Action.objects.get(pk=new_action.pk).resolution.status, "rejected")
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
        self.assertEquals(Action.objects.get(pk=new_action.pk).resolution.status, "implemented")
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
        self.condClient = CommunityConditionalClient(actor=self.users.pinoe, target=self.community)

    def test_with_conditional_on_governer_decision_making(self):

        # Set conditional on governor decision making.  Only Sonny can approve condition.
        action, result = self.condClient.add_condition_to_governors(
            condition_type="approvalcondition",
            permission_data=json.dumps([{"approve_actors": [self.users.sonny.pk]}]))
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented") # Action accepted

        # Check that the condition template's owner is correct
        ct = self.condClient.get_condition_template_for_governor()
        self.assertEquals(ct.get_owner().name, "A New Community")

        # Governor Pinoe does a thing, creates a conditional action to be approved
        action, result = self.commClient.change_name(new_name="A Newly Named Community")
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "waiting")
        self.assertEquals(self.community.name, "A New Community")
        conditional_action = self.condClient.get_condition_item_given_action(action_pk=action.pk)

        # Governer Sonny reviews
        acc = ApprovalConditionClient(target=conditional_action, actor=self.users.sonny)
        review_action, result = acc.approve()
        self.assertEquals(Action.objects.get(pk=review_action.pk).resolution.status, "implemented")

        # Now Governor Pinoe's thing passes.
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")
        self.community.refresh_from_db()
        self.assertEquals(self.community.name, "A Newly Named Community")


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
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "rejected")
        self.assertEquals(resource.get_name(), "A resource")

        # Owner adds a specific permission for Aubrey, so Aubrey's action is successful
        prc = PermissionResourceClient(actor=self.users.pinoe, target=resource)
        owner_action, result = prc.add_permission(permission_type=Changes.Resources.ChangeResourceName,
            permission_actors=[self.users.aubrey.pk])
        action, result = aubrey_rc.change_name(new_name="Aubrey's resource")
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")
        self.assertEquals(resource.get_name(), "Aubrey's resource")

        # Now switch foundational override.
        fp_action, result = prc.enable_foundational_permission()

        # Aunrey's actions are no longer successful
        action, result = aubrey_rc.change_name(new_name="A new name for Aubrey's resource")
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "rejected")
        self.assertEquals(resource.get_name(), "Aubrey's resource")

    def test_foundational_authority_override_on_community_owned_object(self):
        
        # By default, Aubrey's actions are not successful
        aubrey_rc = ResourceClient(actor=self.users.aubrey, target=self.resource)
        action, result = aubrey_rc.change_name(new_name="Aubrey's resource")
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "rejected")
        self.assertEquals(self.resource.get_name(), "A New Resource")

        # Owner Pinoe adds a specific permission for Aubrey, Aubrey's action is successful
        prc = PermissionResourceClient(actor=self.users.pinoe, target=self.resource)
        owner_action, result = prc.add_permission(permission_type=Changes.Resources.ChangeResourceName,
            permission_actors=[self.users.aubrey.pk])
        action, result = aubrey_rc.change_name(new_name="Aubrey's resource")
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")
        self.assertEquals(self.resource.get_name(), "Aubrey's resource")

        # Now switch foundational override.
        fp_action, result = prc.enable_foundational_permission()

        # Aubrey's actions are no longer successful
        action, result = aubrey_rc.change_name(new_name="A new name for Aubrey's resource")
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "rejected")
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
        self.condClient = CommunityConditionalClient(actor=self.users.pinoe, target=self.community)

        # FIXME: still too much configuration :/
        action, result = self.condClient.add_condition_to_owners(
            condition_type = "votecondition",
            permission_data = json.dumps([ { "vote_roles": ['members'] } ]),
            condition_data=json.dumps({"voting_period": 1 }))

        # Christen tries to change the name of the resource but is not successful.
        christen_rc = ResourceClient(actor=self.users.christen, target=self.resource)
        action, result = christen_rc.change_name(new_name="Christen's resource")
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "rejected")
        self.assertEquals(self.resource.get_name(), "A New Resource")

        # Christen tries to switch on foundational override.  This goes to foundational authority
        # and it generates a vote.  Everyone votes and it's approved. 
        key_action, result = christen_rc.enable_foundational_permission()
        self.assertEquals(Action.objects.get(pk=key_action.pk).resolution.status, "waiting")
        conditional_action = self.condClient.get_condition_item_given_action(action_pk=key_action.pk)

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

        self.assertEquals(Action.objects.get(pk=key_action.pk).resolution.status, "implemented")
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
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "rejected")

        # Rose tries to add Aubrey as a governor.  She cannot, she is not an owner.
        self.commClient.set_actor(actor=self.users.rose)
        action, result = self.commClient.add_governor(governor_pk=self.users.aubrey.pk)
        self.assertEquals(self.community.roles.get_governors(), 
            {'actors': [self.users.pinoe.pk, self.users.sully.pk], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "rejected")

        # Pinoe tries to add Aubrey as a governor.  She can, since has foundational authority.
        self.commClient.set_actor(actor=self.users.pinoe)
        action, result = self.commClient.add_governor(governor_pk=self.users.aubrey.pk)
        self.assertEquals(self.community.roles.get_governors(), 
            {'actors': [self.users.pinoe.pk, self.users.sully.pk, self.users.aubrey.pk], 
            'roles': []})
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")

    def test_change_owners_requires_foundational_authority(self):

        # Pinoe adds Crystal as owner.  There are now two owners with no conditions.
        self.commClient.set_target(self.community)
        self.commClient.add_members([self.users.crystal.pk])
        action, result = self.commClient.add_owner(owner_pk=self.users.crystal.pk)
        self.assertEquals(self.community.roles.get_owners(), 
            {'actors': [self.users.pinoe.pk, self.users.crystal.pk], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")

        # Tobin tries to add Christen as owner.  She cannot, she is not an owner.
        self.commClient.set_actor(actor=self.users.tobin)
        action, result = self.commClient.add_owner(owner_pk=self.users.christen.pk)
        self.assertEquals(self.community.roles.get_owners(), 
            {'actors': [self.users.pinoe.pk, self.users.crystal.pk], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "rejected")

        # Crystal tries to add Christen as owner.  She can, since has foundational authority.
        self.commClient.set_actor(actor=self.users.crystal)
        action, result = self.commClient.add_owner(owner_pk=self.users.christen.pk)
        self.assertEquals(self.community.roles.get_owners(), 
            {'actors': [self.users.pinoe.pk, self.users.crystal.pk, self.users.christen.pk], 
            'roles': []})
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")

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
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "rejected")
        self.assertFalse(self.resource.foundational_permission_enabled)

        # Crystal tries to enable foundational override on resource.
        # She cannot, she is not an owner.
        self.resourceClient.set_actor(actor=self.users.crystal)
        action, result = self.resourceClient.enable_foundational_permission()
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "rejected")
        self.assertFalse(self.resource.foundational_permission_enabled)

        # Pinoe tries to enable foundational override on resource.
        # She can, since she is an owner and has foundational authority.
        self.resourceClient.set_actor(actor=self.users.pinoe)
        action, result = self.resourceClient.enable_foundational_permission()
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")
        self.assertTrue(self.resource.foundational_permission_enabled)


class RolesetTest(DataTestCase):

    def setUp(self):

        self.commClient = CommunityClient(actor=self.users.pinoe)
        self.community = self.commClient.create_community(name="USWNT")
        self.commClient.set_target(self.community)
        self.resourceClient = ResourceClient(actor=self.users.pinoe)
        self.resource = self.resourceClient.create_resource(name="USWNT Resource")
        self.resourceClient.set_target(self.resource)
        self.permClient = PermissionResourceClient(actor=self.users.pinoe)

    # Test custom roles

    def test_basic_custom_role(self):

        # No custom roles so far
        roles = self.commClient.get_custom_roles()
        self.assertEquals(roles, {})

        # Add a role
        action, result = self.commClient.add_role(role_name="forwards")
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")
        roles = self.commClient.get_custom_roles()
        self.assertEquals(roles, {'forwards': []})

        # Add people to role
        self.commClient.add_members([self.users.christen.pk, self.users.crystal.pk])
        action, result = self.commClient.add_people_to_role(role_name="forwards", 
            people_to_add=[self.users.christen.pk, self.users.crystal.pk, self.users.pinoe.pk])
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")
        roles = self.commClient.get_roles()
        self.assertCountEqual(roles["forwards"], 
            [self.users.christen.pk, self.users.crystal.pk, self.users.pinoe.pk])

        # Remove person from role
        action, result = self.commClient.remove_people_from_role(role_name="forwards", 
            people_to_remove=[self.users.crystal.pk])
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")
        roles = self.commClient.get_roles()
        self.assertCountEqual(roles["forwards"], [self.users.christen.pk, self.users.pinoe.pk])

        # Remove role
        action, result = self.commClient.remove_role(role_name="forwards")
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")
        roles = self.commClient.get_custom_roles()
        self.assertEquals(roles, {})

    def test_basic_role_works_with_permission_item(self):

        # Aubrey wants to change the name of the resource, she can't
        self.commClient.add_members([self.users.aubrey.pk])
        self.resourceClient.set_actor(actor=self.users.aubrey)
        action, result = self.resourceClient.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "rejected")
        self.assertEquals(self.resource.name, "USWNT Resource")

        # Pinoe adds a 'namers' role to the community which owns the resource
        self.resourceClient.set_actor(actor=self.users.pinoe)
        action, result = self.commClient.add_role(role_name="namers")
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")
        roles = self.commClient.get_custom_roles()
        self.assertEquals(roles, {'namers': []})

        # Pinoe creates a permission item with the 'namers' role in it
        self.permClient.set_target(self.resource)
        action, result = self.permClient.add_permission(permission_type=Changes.Resources.ChangeResourceName,
            permission_roles=["namers"])
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")

        # Pinoe adds Aubrey to the 'namers' role in the community
        action, result = self.commClient.add_people_to_role(role_name="namers", 
            people_to_add=[self.users.aubrey.pk])
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")
        roles = self.commClient.get_roles()
        self.assertCountEqual(roles["namers"], [self.users.aubrey.pk])

        # Aubrey can now change the name of the resource
        self.resourceClient.set_actor(actor=self.users.aubrey)
        action, result = self.resourceClient.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")
        self.assertEquals(self.resource.name, "A Changed Resource")

        # Pinoe removes Aubrey from the namers role in the community
        action, result = self.commClient.remove_people_from_role(role_name="namers", 
            people_to_remove=[self.users.aubrey.pk])
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")
        roles = self.commClient.get_roles()
        self.assertCountEqual(roles["namers"], [])

        # Aubrey can no longer change the name of the resource
        self.resourceClient.set_actor(actor=self.users.aubrey)
        action, result = self.resourceClient.change_name(new_name="A Newly Changed Resource")
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "rejected")
        self.assertEquals(self.resource.name, "A Changed Resource")

    def test_basic_role_works_with_governor(self):        

        # Pinoe adds the resource to her community
        self.resourceClient.set_target(target=self.resource)
        self.resourceClient.change_owner_of_target(new_owner=self.community)

        # Aubrey wants to change the name of the resource, she can't
        self.resourceClient.set_actor(actor=self.users.aubrey)
        action, result = self.resourceClient.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "rejected")
        self.assertEquals(self.resource.name, "USWNT Resource")

        # Pinoe adds member role to governors
        action, result = self.commClient.add_governor_role(governor_role="members")
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")
        self.commClient.refresh_target()
        gov_info = self.commClient.get_governorship_info()
        self.assertDictEqual(gov_info, {'actors': [self.users.pinoe.pk], 'roles': ['members']})

        # Aubrey tries to do a thing and can't
        action, result = self.resourceClient.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "rejected")
        self.assertEquals(self.resource.name, "USWNT Resource")

        # Pinoe adds Aubrey as a member
        action, result = self.commClient.add_members(member_pk_list=[self.users.aubrey.pk])
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")
        roles = self.commClient.get_roles()
        self.assertCountEqual(roles["members"], [self.users.pinoe.pk, self.users.aubrey.pk]) 

        # Aubrey tries to do a thing and can
        action, result = self.resourceClient.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")
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
        permissions_for_role = self.prClient.get_permissions_associated_with_role(role_name="spirit players")
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
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "rejected")
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
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")
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
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "rejected")
        self.assertEquals(self.resource.name, "Spirit is the best NWSL team!")

    def test_add_and_remove_role_permission_to_resource_via_form(self):

        # Aubrey tries to change the name of the forum and fails
        action, result = self.aubreyClient.change_name(new_name="Spirit is the best NWSL team!")
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "rejected")
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
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "rejected")
        self.assertEquals(self.resource.name, "NWSL Rocks")        
        action, result = self.aubreyClient.change_name(new_name="Spirit is the best NWSL team!")
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "implemented")
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
        self.assertEquals(Action.objects.get(pk=action.pk).resolution.status, "rejected")
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

    def test_resolution_field_correct_for_approved_action(self):

        # Add permission so any member can change the name of the group
        self.prc.add_permission(permission_roles=["members"],
            permission_type=Changes.Communities.ChangeName)

        # User changes name
        self.commClient.set_actor(actor=self.member_user)
        action, result = self.commClient.change_name(new_name="Miscellaneous Badasses")
        self.assertEquals(action.resolution.status, "implemented")

        # Inspect action's resolution field
        self.assertTrue(action.resolution.is_resolved)
        self.assertTrue(action.resolution.is_approved)
        self.assertEquals(action.resolution.resolved_through, "specific")
        self.assertFalse(action.resolution.condition)

    def test_resolution_field_correct_for_rejected_action(self):

        # Add permission so any member can change the name of the group
        self.prc.add_permission(permission_roles=["members"],
            permission_type=Changes.Communities.ChangeName)

        # Non-member user changes name
        self.commClient.set_actor(actor=self.nonmember_user)
        action, result = self.commClient.change_name(new_name="Miscellaneous Badasses")
        self.assertEquals(action.resolution.status, "rejected")

        # Inspect action's resolution field
        self.assertTrue(action.resolution.is_resolved)
        self.assertFalse(action.resolution.is_approved)
        self.assertEquals(action.resolution.resolved_through, "specific")
        self.assertFalse(action.resolution.condition)

    def test_resolution_field_resolved_through(self):
        
        # Pinoe can make JJ a governor because she has a foundational permission
        action, result = self.commClient.add_governor(governor_pk=self.users.jj.pk)
        self.assertEquals(action.resolution.status, "implemented")
        self.assertTrue(action.resolution.is_resolved)
        self.assertTrue(action.resolution.is_approved)
        self.assertEquals(action.resolution.resolved_through, "foundational")

        # JJ can change the name of the group because he has a governing permission.        
        action, result = self.jjClient.change_name(new_name="Julie Ertz and Her Sidekicks")
        self.assertEquals(action.resolution.status, "implemented")
        self.assertTrue(action.resolution.is_resolved)
        self.assertTrue(action.resolution.is_approved)
        self.assertEquals(action.resolution.resolved_through, "governing")

        # Crystal can change the name of the group because she has a specific permission.
        self.prc.add_permission(permission_actors=[self.users.crystal.pk],
            permission_type=Changes.Communities.ChangeName)
        action, result = self.crystalClient.change_name(new_name="Crystal Dunn and Her Sidekicks")
        self.assertEquals(action.resolution.status, "implemented")
        self.assertTrue(action.resolution.is_resolved)
        self.assertTrue(action.resolution.is_approved)
        self.assertEquals(action.resolution.resolved_through, "specific")

    def test_resolution_field_for_role_for_specific_permission(self):

        # Add permission so any member can change the name of the group
        self.prc.add_permission(permission_roles=["members"],
            permission_type=Changes.Communities.ChangeName)

        # When they change the name, the resolution role field shows the role
        action, result = self.roseClient.change_name(new_name="Best Team")
        self.assertTrue(action.resolution.is_approved)
        self.assertEquals(action.resolution.resolved_through, "specific")
        self.assertEquals(action.resolution.role, "members")

    def test_resolution_field_for_role_for_governing_permission(self):

        # Pinoe makes a governing role
        action, result = self.commClient.add_governor_role(governor_role="midfielders")
        action, result = self.roseClient.change_name(new_name="Best Team")
        self.assertEquals(action.resolution.resolved_through, "governing")
        self.assertEquals(action.resolution.role, "midfielders")

    def test_resolution_field_for_individual(self):

        # Add permission so a specific person can change the name of the group
        self.prc.add_permission(permission_actors=[self.users.rose.pk],
            permission_type=Changes.Communities.ChangeName)

        # When they change the name, the resolution role field shows no role
        action, result = self.roseClient.change_name(new_name="Best Team")
        self.assertTrue(action.resolution.is_approved)
        self.assertEquals(action.resolution.resolved_through, "specific")
        self.assertFalse(action.resolution.role)

    def test_resolution_field_captures_conditional_info(self):

        # Pinoe sets a permission on the community that any 'member' can change the name.
        action, permission = self.prc.add_permission(permission_roles=["members"],
            permission_type=Changes.Communities.ChangeName)

        # But then she adds a condition that someone needs to approve a name change 
        # before it can go through. 
        conditionalClient = PermissionConditionalClient(actor=self.users.pinoe, 
            target=permission)
        conditionalClient.add_condition(condition_type="approvalcondition")

        # (Since no specific permission is set on the condition, "approving" it 
        # requirest foundational or governing authority to change.  So only Pinoe 
        # can approve.)

        # HAO tries to change the name and fails because she is not a member.  The
        # condition never gets triggered.
        action, result = self.haoClient.change_name(new_name="Let's go North Carolina!")
        self.assertEquals(action.resolution.status, "rejected")
        self.assertTrue(action.resolution.is_resolved)
        self.assertFalse(action.resolution.is_approved)
        self.assertEquals(action.resolution.resolved_through, "specific")
        self.assertFalse(action.resolution.condition)

        # Rose tries to change the name and has to wait for approval.
        rose_action, result = self.roseClient.change_name(new_name="Friends <3")
        self.assertEquals(rose_action.resolution.status, "waiting")
        self.assertFalse(rose_action.resolution.is_resolved)
        self.assertFalse(rose_action.resolution.is_approved)
        self.assertFalse(rose_action.resolution.condition)

        # Pinoe approves Rose's name change.
        condition_item = conditionalClient.get_condition_item_given_action(
            action_pk=rose_action.pk)
        acc = ApprovalConditionClient(target=condition_item, actor=self.users.pinoe)
        action, result = acc.approve()
        self.assertEquals(action.resolution.status, "implemented")

        # Rose's action is implemented
        rose_action.refresh_from_db()
        self.assertEquals(rose_action.resolution.status, "implemented")
        self.assertTrue(rose_action.resolution.is_resolved)
        self.assertTrue(rose_action.resolution.is_approved)
        self.assertEquals(rose_action.resolution.condition, "approvalcondition")
        self.instance = self.commClient.get_community(community_pk=str(self.instance.pk))
        self.assertEquals(self.instance.name, "Friends <3")

        # Rose tries to change the name again.  This time Pinoe rejects it, for Pinoe is fickle. 
        rose_action, result = self.roseClient.change_name(new_name="BEST Friends <3")
        condition_item = conditionalClient.get_condition_item_given_action(
            action_pk=rose_action.pk)
        acc = ApprovalConditionClient(target=condition_item, actor=self.users.pinoe)
        action, result = acc.reject()
        rose_action.refresh_from_db()
        self.assertEquals(rose_action.resolution.status, "rejected")
        self.assertEquals(self.instance.name, "Friends <3")
        self.assertTrue(rose_action.resolution.is_resolved)
        self.assertFalse(rose_action.resolution.is_approved)
        self.assertEquals(rose_action.resolution.condition, "approvalcondition")


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

@skip("Need to rethink action containers - see models.py")
class ActionContainerTest(DataTestCase):

    def setUp(self):

        # Create a Community and Client
        self.commClient = CommunityClient(actor=self.users.pinoe)
        self.instance = self.commClient.create_community(name="USWNT")
        self.commClient.set_target(self.instance)
        self.permClient = PermissionResourceClient(actor=self.users.pinoe, target=self.instance)

        self.container = self.commClient.begin_provisional()

        # Action 1: Add some members
        self.commClient.add_members([self.users.rose.pk, self.users.tobin.pk,
            self.users.christen.pk, self.users.aubrey.pk])

        # Action 2: Add a role
        self.commClient.add_role(role_name="forwards")

        # Action 3: Add another role
        self.commClient.add_role(role_name="spirit players")

        # Action 4: Add people to first role
        self.commClient.add_people_to_role(role_name="forwards", 
            people_to_add=[self.users.christen.pk, self.users.tobin.pk])

        # Action 5: Add people to second role
        self.commClient.add_people_to_role(role_name="spirit players", 
            people_to_add=[self.users.rose.pk, self.users.aubrey.pk])

        self.commClient.end_provisional()
        self.assertEquals(len(self.container.actions.all()), 5)

    def test_process_actions_provisionally(self):

        # Before processing, actions have not been implemented
        roles = self.commClient.get_custom_roles()
        self.assertEquals(roles, {})
        members = self.commClient.get_members()
        self.assertEquals(members, [self.users.pinoe])

        # Process provisionally
        self.commClient.process_container(container=self.container)

        # After *provisional* processing, actions have still not been implemented 
        roles = self.commClient.get_custom_roles()
        self.assertEquals(roles, {})
        members = self.commClient.get_members()
        self.assertEquals(members, [self.users.pinoe])

        # Check action info & container status
        action_info_dict = self.container.get_action_info()
        self.assertNotEquals(action_info_dict['action_log'], {})
        self.assertNotEquals(action_info_dict['action_status'], {})
        status_summary = self.container.get_status_summary()
        self.assertEquals(status_summary, {'total_count': 5, 'approved': ['1', '2', '3', '4', '5'], 
            'rejected': [], 'waiting': [], 'implemented': []})
        overall_status = self.container.determine_overall_status()
        self.assertEquals(overall_status, "approved")
        self.assertEquals(self.container.status, "provisional")

    def test_process_actions_permanently(self):

        # Process permanently
        self.commClient.process_container(container=self.container, provisionally=False)
        self.commClient.refresh_target()

        # After *permanent* processing, actions have been implemented 
        roles = self.commClient.get_custom_roles()
        self.assertEquals(roles, {'forwards': [self.users.tobin.pk, self.users.christen.pk], 
            'spirit players': [self.users.rose.pk, self.users.aubrey.pk]})
        members = self.commClient.get_members()
        self.assertEquals(members, [self.users.pinoe, self.users.rose, self.users.tobin,
            self.users.christen, self.users.aubrey])

        # Check action info & container status
        action_info_dict = self.container.get_action_info()
        self.assertNotEquals(action_info_dict['action_log'], {})
        self.assertNotEquals(action_info_dict['action_status'], {})
        status_summary = self.container.get_status_summary()
        self.assertEquals(status_summary, {'total_count': 5, 'approved': [], 'rejected': [], 
            'waiting': [], 'implemented': ['1', '2', '3', '4', '5']})
        overall_status = self.container.determine_overall_status()
        self.assertEquals(overall_status, "implemented")
        self.assertEquals(self.container.get_final_status(), "implemented")
        self.assertEquals(self.container.status, "permanent")

    def test_process_actions_provisionally_with_rejections(self):

        # Add permission on "add people to role" so actions 3 & 4 are rejected
        action, permission = self.permClient.add_permission(
            permission_type=Changes.Communities.AddPeopleToRole,
            permission_actors=[self.users.crystal.pk])

        # Process provisionally
        self.commClient.process_container(container=self.container)

        # Check action info & container status
        action_info_dict = self.container.get_action_info()
        self.assertNotEquals(action_info_dict['action_log'], {})
        self.assertNotEquals(action_info_dict['action_status'], {})
        status_summary = self.container.get_status_summary()
        self.assertEquals(status_summary, {'total_count': 5, 'approved': ['1', '2', '3'], 
            'rejected': ['4', '5'], 'waiting': [], 'implemented': []})
        overall_status = self.container.determine_overall_status()
        self.assertEquals(overall_status, "rejected")
        self.assertEquals(self.container.status, "provisional")

    def test_process_actions_permanently_with_rejections(self):

        # Add permission on "add people to role" so actions 3 & 4 are rejected
        action, permission = self.permClient.add_permission(
            permission_type=Changes.Communities.AddPeopleToRole,
            permission_actors=[self.users.crystal.pk])

        # Process permanently
        self.commClient.process_container(container=self.container, provisionally=False)

        # Check action info & container status
        action_info_dict = self.container.get_action_info()
        self.assertNotEquals(action_info_dict['action_log'], {})
        self.assertNotEquals(action_info_dict['action_status'], {})
        status_summary = self.container.get_status_summary()
        self.assertEquals(status_summary, {'total_count': 5, 'approved': ['1', '2', '3'], 'rejected': ['4', '5'], 
            'waiting': [], 'implemented': []})
        overall_status = self.container.determine_overall_status()
        self.assertEquals(overall_status, "rejected")
        self.assertEquals(self.container.get_final_status(), "rejected")
        self.assertEquals(self.container.status, "permanent")

    def test_process_actions_provisionally_with_conditions(self):

        # Set permission with condition
        action, permission = self.permClient.add_permission(
            permission_type=Changes.Communities.AddPeopleToRole,
            permission_actors=[self.users.pinoe.pk])
        self.pcc = PermissionConditionalClient(actor=self.users.pinoe)
        self.pcc.set_target(target=permission)
        self.pcc.add_condition(condition_type="approvalcondition",
            permission_data=json.dumps([{
                'permission_type': Changes.Conditionals.Approve, 
                'permission_actors': [self.users.crystal.pk],
                'permission_roles': [],
                'permission_configuration': '{}'}]))

        # Process provisionally
        self.commClient.process_container(container=self.container)

        # Check action info & container status
        action_info_dict = self.container.get_action_info()
        self.assertNotEquals(action_info_dict['action_log'], {})
        self.assertNotEquals(action_info_dict['action_status'], {})
        status_summary = self.container.get_status_summary()
        self.assertEquals(status_summary, {'total_count': 5, 'approved': ['1', '2', '3'], 
            'rejected': [], 'waiting': ['4', '5'], 'implemented': []})
        overall_status = self.container.determine_overall_status()
        self.assertEquals(overall_status, "waiting")
        self.assertEquals(self.container.status, "provisional")

    def test_process_actions_permanently_with_conditions(self):

        # Set permission with condition
        action, permission = self.permClient.add_permission(
            permission_type=Changes.Communities.AddPeopleToRole,
            permission_actors=[self.users.pinoe.pk])
        self.pcc = PermissionConditionalClient(actor=self.users.pinoe)
        self.pcc.set_target(target=permission)
        self.pcc.add_condition(condition_type="approvalcondition",
            permission_data=json.dumps([{
                'permission_type': Changes.Conditionals.Approve, 
                'permission_actors': [self.users.crystal.pk],
                'permission_roles': [],
                'permission_configuration': '{}'}]))

        # Can't process permanently if there's an unresolved condition (status == "waiting")
        self.commClient.process_container(container=self.container, provisionally=False)

        # Check action info & container status
        action_info_dict = self.container.get_action_info()
        self.assertNotEquals(action_info_dict['action_log'], {})
        self.assertNotEquals(action_info_dict['action_status'], {})
        status_summary = self.container.get_status_summary()
        self.assertEquals(status_summary, {'total_count': 5, 'approved': ['1', '2', '3'], 
            'rejected': [], 'waiting': ['4', '5'], 'implemented': []})
        overall_status = self.container.determine_overall_status()
        self.assertEquals(overall_status, "waiting")
        self.assertEquals(self.container.status, "provisional")

        # Crystal approves the two actions
        # FIXME: these conditional clients are cumbersome, need to fix the whole client concept
        first_item = self.pcc.get_condition_item_given_action(action_pk=4)
        second_item = self.pcc.get_condition_item_given_action(action_pk=5)
        acc = ApprovalConditionClient(target=first_item, actor=self.users.crystal)
        acc.approve()
        acc.set_target(target=second_item)
        acc.approve()

        # now the container can be run
        self.commClient.process_container(container=self.container, provisionally=False)
        status_summary = self.container.get_status_summary()
        self.assertEquals(status_summary, {'total_count': 5, 'approved': [], 
            'rejected': [], 'waiting': [], 'implemented': ['1', '2', '3','4', '5']})
        overall_status = self.container.determine_overall_status()
        self.assertEquals(overall_status, "implemented")
        self.assertEquals(self.container.status, "permanent")


class TemplateTest(DataTestCase):

    def setUp(self):

        # Create a Community and Client
        self.commClient = CommunityClient(actor=self.users.pinoe)
        self.instance = self.commClient.create_community(name="USWNT")
        self.commClient.set_target(self.instance)
        self.permClient = PermissionResourceClient(actor=self.users.pinoe, target=self.instance)
        self.templateClient = TemplateClient(actor=self.users.pinoe)

    def set_up_simple_community(self):

        # Set up community
        self.commClient.add_role(role_name="forwards")
        self.commClient.add_members([self.users.tobin.pk, self.users.christen.pk])
        self.commClient.add_people_to_role(role_name="forwards", people_to_add=[self.users.tobin.pk,
            self.users.christen.pk])
        # Add permission
        self.permClient.add_permission(permission_type=Changes.Communities.ChangeName, 
            permission_actors=[self.users.aubrey.pk], permission_roles=["forwards"])
        permission = self.permClient.get_permissions_on_object(object=self.instance)[0]
        # Add condition on permission
        self.permCondClient = PermissionConditionalClient(actor=self.users.pinoe, target=permission)
        action, result = self.permCondClient.add_condition(
            condition_type="approvalcondition",
            permission_data=json.dumps([{
                'permission_type': Changes.Conditionals.Approve,
                'permission_actors': [self.users.christen.pk],
                'permission_roles': '',
                'permission_configuration': '{}'}]))        
        # Add condition on community
        self.condClient = CommunityConditionalClient(actor=self.users.pinoe, target=self.instance)
        action, result = self.condClient.add_condition_to_owners(
            condition_type="approvalcondition",
            permission_data=json.dumps([{
                'permission_type': Changes.Conditionals.Approve,
                'permission_actors': [self.users.pinoe.pk],
                'permission_roles': '',
                'permission_configuration': '{}'}]))

    def set_up_complex_community(self):
        
        # Set up community
        self.commClient.add_role(role_name="forwards")
        self.commClient.add_members([self.users.tobin.pk, self.users.christen.pk])
        self.commClient.add_people_to_role(role_name="forwards", people_to_add=[self.users.tobin.pk,
            self.users.christen.pk])

        # Add some owned objects
        self.resourceClient = ResourceClient(actor=self.users.pinoe)
        self.resource = self.resourceClient.create_resource(name="WoSo Forum")
        self.resourceClient.set_target(target=self.resource)
        self.resource2 = self.resourceClient.create_resource(name="Ticker Tape Parade Pictures")

        # Change owners so resources so community it self-contained
        self.resourceClient.change_owner_of_target(new_owner=self.instance)
        self.resourceClient.set_target(target=self.resource2)
        self.resourceClient.change_owner_of_target(new_owner=self.instance)

        # Add permission
        self.permClient.add_permission(permission_type=Changes.Communities.ChangeName, 
            permission_actors=[self.users.aubrey.pk], permission_roles=["forwards"])
        permission = self.permClient.get_permissions_on_object(object=self.instance)[0]
 
        # Add condition on permission
        self.permCondClient = PermissionConditionalClient(actor=self.users.pinoe, target=permission)
        action, result = self.permCondClient.add_condition(
            condition_type="approvalcondition",
            permission_data=json.dumps([{
                'permission_type': Changes.Conditionals.Approve,
                'permission_actors': [self.users.christen.pk],
                'permission_roles': '',
                'permission_configuration': '{}'}]))        
 
        # Add permission on resource
        self.permClient.set_target(self.resource2)
        result, perm = self.permClient.add_permission(permission_type=Changes.Resources.AddItem, 
            permission_roles=["members"])
        self.permission_level_one = self.permClient.get_permissions_on_object(object=self.resource2)[0]

        # Add nested permission
        self.permClient.set_target(self.permission_level_one)
        self.permClient.add_permission(permission_type=Changes.Permissions.RemoveRoleFromPermission,
            permission_actors=[self.users.aubrey.pk])
        self.permission_level_two = self.permClient.get_permissions_on_object(object=self.permission_level_one)[0]

       # Add condition on community
        self.condClient = CommunityConditionalClient(actor=self.users.pinoe, target=self.instance)
        action, result = self.condClient.add_condition_to_owners(
            condition_type="approvalcondition",
            permission_data=json.dumps([{
                'permission_type': Changes.Conditionals.Approve,
                'permission_actors': [self.users.pinoe.pk],
                'permission_roles': '',
                'permission_configuration': '{}'}]))

    def test_make_template_from_community(self):

        # create template from community
        template_model = self.templateClient.make_template(community=self.instance, 
            description="My new template")
        self.assertEqual(template_model.description, "My new template")
        self.assertEqual(template_model.data.get_community().name, "USWNT")
        self.assertEqual(template_model.data.get_community().pk, None)
        self.assertEqual(template_model.data.get_community().roles.members, [1])
        self.assertEqual(template_model.data.get_community().roles.owners["actors"], [1])

        # try again with more things in community
        self.commClient.add_role(role_name="forwards")
        self.commClient.add_members([self.users.tobin.pk, self.users.christen.pk])
        self.commClient.add_people_to_role(role_name="forwards", people_to_add=[self.users.tobin.pk,
            self.users.christen.pk])

        template_model = self.templateClient.make_template(community=self.instance, 
            description="An even better template")
        self.assertEqual(template_model.description, "An even better template")
        self.assertEqual(template_model.data.get_community().roles.custom_roles["forwards"], [3,4])
        self.assertEqual(template_model.data.get_community().roles.members, [1,3,4])

    def test_make_template_from_condition(self):
        
        # Set condition on an action so we can templatize it
        self.condClient = CommunityConditionalClient(actor=self.users.pinoe, target=self.instance)
        action, result = self.condClient.add_condition_to_governors(
            condition_type="approvalcondition",
            permission_data=json.dumps([{
                'permission_type': Changes.Conditionals.Approve,
                'permission_actors': [self.users.pinoe.pk],
                'permission_roles': '',
                'permission_configuration': '{}'}]))
        ct = self.condClient.get_condition_template_for_governor()

        # convert instance to template model using client
        template_model = self.templateClient.make_template(community=self.instance, conditions=[ct], 
            description="Pinoe must approve condition template")
        self.assertEquals(template_model.description, "Pinoe must approve condition template")
        template_of_condition = template_model.data.get_conditions()[0]
        self.assertEquals(template_of_condition.condition_type, "approvalcondition")
        loaded_dict = json.loads(template_of_condition.permission_data)
        self.assertEquals(loaded_dict[0]["permission_actors"], [1])

    def test_make_template_from_permission(self):
        """Template model version of test_templatize_permissions"""

        # Set up permission
        self.commClient.add_members([self.users.tobin.pk, self.users.christen.pk, self.users.aubrey.pk])
        self.commClient.add_role(role_name="forwards")
        self.permClient.add_permission(permission_type=Changes.Communities.ChangeName, 
            permission_actors=[self.users.aubrey.pk], permission_roles=["forwards"])
        permission = self.permClient.get_permissions_on_object(object=self.instance)[0]

        # Test template
        template_model = self.templateClient.make_template(community=self.instance, permissions=[permission],
            description="Forwards and Aubrey can change name permission template")
        self.assertEquals(template_model.description, "Forwards and Aubrey can change name permission template")
        permission_template = template_model.data.get_permissions()[0]
        self.assertEquals(permission_template.inverse, False)
        self.assertEquals(permission_template.roles.get_roles()[0], "forwards")

    def test_make_template_from_resource_and_item(self):

        # Create
        self.rc = ResourceClient(actor=self.users.pinoe)
        resource = self.rc.create_resource(name="Go USWNT!")
        self.rc.set_target(target=resource)
        self.rc.change_owner_of_target(new_owner=self.instance)
        action, item = self.rc.add_item(item_name="Equal Pay")
        self.rc.set_target(target=item)
        self.rc.change_owner_of_target(new_owner=self.instance)

        # Templatize resource & item
        template_model = self.templateClient.make_template(community=self.instance, 
            owned_objects=[resource, item], description="USWNT Resource & Item")
        self.assertEquals(template_model.description, "USWNT Resource & Item")
        template_resource = template_model.data.get_owned_objects()[0]
        self.assertEquals(template_resource.name, "Go USWNT!")
        template_item = template_model.data.get_owned_objects()[1]
        self.assertEquals(template_item.name, "Equal Pay")

    def test_create_new_community_instances_from_templates(self):

        # make template from community
        template_model = self.templateClient.make_template(community=self.instance, 
            description="My new template")
        self.templateClient.set_target(target=template_model)

        # make community from template
        created_objects = self.templateClient.create_from_template()
        self.assertEqual(len(created_objects), 1)
        self.assertEqual(created_objects[0].__class__.__name__, "Community")
        self.assertEqual(created_objects[0].name, "USWNT")
        self.assertNotEqual(created_objects[0].pk, self.instance.pk)

        # try again with more things in community
        self.commClient.add_role(role_name="forwards")
        self.commClient.add_members([self.users.tobin.pk, self.users.christen.pk])
        self.commClient.add_people_to_role(role_name="forwards", people_to_add=[self.users.tobin.pk,
            self.users.christen.pk])
        template_model = self.templateClient.make_template(community=self.instance, 
            description="An even better template")
        self.templateClient.set_target(target=template_model)
        
        # make new community from new template
        created_objects = self.templateClient.create_from_template()
        self.assertEqual(len(created_objects), 1)
        self.assertEqual(created_objects[0].__class__.__name__, "Community")
        self.assertEqual(created_objects[0].roles.custom_roles["forwards"], [3,4])
        self.assertEqual(created_objects[0].roles.members, [1,3,4])

    def test_create_new_conditional_instances_from_templates(self):

        # Set condition and make template of it
        self.condClient = CommunityConditionalClient(actor=self.users.pinoe, target=self.instance)
        action, result = self.condClient.add_condition_to_governors(
            condition_type="approvalcondition",
            permission_data=json.dumps([{
                'permission_type': Changes.Conditionals.Approve,
                'permission_actors': [self.users.pinoe.pk],
                'permission_roles': '',
                'permission_configuration': '{}'}]))
        ct = self.condClient.get_condition_template_for_governor()
        template_model = self.templateClient.make_template(community=self.instance, conditions=[ct], 
            description="Pinoe must approve condition template")
        self.templateClient.set_target(target=template_model)

        # Create condition from template
        created_objects = self.templateClient.create_from_template()
        self.assertEquals(len(created_objects), 2)
        self.assertEquals(created_objects[1].condition_type, "approvalcondition")
        permission_data = json.loads(created_objects[1].permission_data)
        self.assertEquals(permission_data[0]["permission_actors"], [1])

        # Original condition is set on original community, new condition set on new community
        self.assertNotEqual(ct.pk, created_objects[1].pk)
        self.assertNotEquals(self.instance.pk, created_objects[0].pk)
        self.assertEquals(ct.conditioned_object, self.instance)
        self.assertEquals(created_objects[1].conditioned_object, created_objects[0])

    def test_create_new_permission_instances_from_templates(self):

        # Create new permission & template of permission
        self.commClient.add_members([self.users.tobin.pk, self.users.christen.pk, self.users.aubrey.pk])
        self.commClient.add_role(role_name="forwards")
        self.permClient.add_permission(permission_type=Changes.Communities.ChangeName, 
            permission_actors=[self.users.aubrey.pk], permission_roles=["forwards"])
        permission = self.permClient.get_permissions_on_object(object=self.instance)[0]
        template_model = self.templateClient.make_template(community=self.instance, permissions=[permission], 
            description="Forwards and Aubrey can change name permission template")
        self.templateClient.set_target(target=template_model)

        # Create new permission from template
        created_objects = self.templateClient.create_from_template()
        self.assertEquals(created_objects[1].permitted_object, created_objects[0])
        self.assertTrue("ChangeName" in created_objects[1].change_type)
        self.assertEquals(created_objects[1].roles.get_roles()[0], "forwards")
        self.assertEquals(created_objects[1].actors.as_pks(), [self.users.aubrey.pk])

    def test_create_new_resource_and_item_instances_from_templates(self):
        # Note - we need to pass in both resource and item since our templating system does
        # not recursively map related fields that are not conditions/permissions.  Also note
        # that we need to change owners for the templates to actually be created.

        # Create & templatize resource and item
        self.rc = ResourceClient(actor=self.users.pinoe)
        resource = self.rc.create_resource(name="Go USWNT!")
        self.rc.set_target(target=resource)
        self.rc.change_owner_of_target(new_owner=self.instance)
        action, item = self.rc.add_item(item_name="Equal Pay")
        self.rc.set_target(target=item)
        self.rc.change_owner_of_target(new_owner=self.instance)
        template_model = self.templateClient.make_template(community=self.instance, 
            owned_objects=[resource, item], description="Resource & item")
        self.templateClient.set_target(target=template_model)

        # Create resource & item from template
        created_objects = self.templateClient.create_from_template()
        self.assertEquals(created_objects[0].__class__.__name__, "Community")
        self.assertEquals(created_objects[1].name, "Go USWNT!")
        self.assertEquals(created_objects[2].name, "Equal Pay")
        self.assertEquals(created_objects[1].owner, created_objects[0])
        self.assertEquals(created_objects[2].owner, created_objects[0])
        self.assertEquals(created_objects[2].resource, created_objects[1])

    def test_create_from_template_of_simple_community(self):

        # Create simple community, generate template, and then generate new set of instances
        self.set_up_simple_community()
        permissions = PermissionsItem.objects.all()
        conditions = ConditionTemplate.objects.all()
        template_model = self.templateClient.make_template(community=self.instance, permissions=permissions,
            conditions=conditions, description="Simple Community Template")
        self.templateClient.set_target(target=template_model)
        created_objects = self.templateClient.create_from_template()
        self.assertEquals(len(created_objects), 4)
        community, permission, permission_condition, community_condition = created_objects

        self.assertEquals(permission.permitted_object, community)
        self.assertEquals(permission.roles.get_roles()[0], "forwards")
        self.assertEquals(permission_condition.conditioned_object, permission)
        self.assertEquals(community_condition.conditioned_object, community)

    def test_create_from_template_of_complex_community(self):

        # Create complex community, generate template, and then generate new set of instances
        self.set_up_complex_community()
        permissions = PermissionsItem.objects.all()
        conditions = ConditionTemplate.objects.all()
        owned_objects = list(Resource.objects.all()) + list(Item.objects.all())
        template_model = self.templateClient.make_template(community=self.instance, permissions=permissions,
            conditions=conditions, owned_objects=owned_objects, description="Complex Community Template")
        created_objects = self.templateClient.create_from_template(template_model=template_model)
        self.assertEquals(len(created_objects), 8)
        community, perm1, perm_condition, com_condition, resource1, resource2, perm2, perm3 = created_objects
        
        # test community
        self.assertEquals(list(community.roles.get_custom_role_names()), ["forwards"])
        self.assertEquals(community.roles.members, 
            [self.users.pinoe.pk, self.users.tobin.pk, self.users.christen.pk])
        self.assertEquals(community.roles.get_users_given_role("forwards"), 
            [self.users.tobin.pk, self.users.christen.pk])

        # test conditions
        self.assertEquals(perm_condition.conditioned_object, perm1)
        self.assertEquals(perm_condition.condition_type, "approvalcondition")
        permission_data = json.loads(perm_condition.permission_data)
        self.assertEquals(permission_data[0]["permission_actors"], [self.users.christen.pk])
        self.assertEquals(permission_data[0]["permission_type"], Changes.Conditionals.Approve)
        self.assertEquals(com_condition.conditioned_object, community)
        self.assertEquals(com_condition.condition_type, "approvalcondition")
        self.assertEquals(com_condition.target_type, "own")
        permission_data = json.loads(com_condition.permission_data)
        self.assertEquals(permission_data[0]["permission_actors"], [self.users.pinoe.pk])
        self.assertEquals(permission_data[0]["permission_type"], Changes.Conditionals.Approve)

        # test permissions
        self.assertEquals(perm1.permitted_object, community)
        self.assertEquals(perm1.change_type, Changes.Communities.ChangeName)
        self.assertEquals(perm1.actors.as_pks(), [self.users.aubrey.pk])
        self.assertEquals(perm1.roles.role_list, ["forwards"])
        self.assertEquals(perm2.permitted_object, resource2)
        self.assertEquals(perm2.change_type, Changes.Resources.AddItem)
        self.assertEquals(perm2.roles.role_list, ["members"])
        self.assertEquals(perm3.permitted_object, perm2)
        self.assertEquals(perm3.change_type, Changes.Permissions.RemoveRoleFromPermission)
        self.assertEquals(perm3.actors.as_pks(), [self.users.aubrey.pk])

        # test resources
        self.assertEquals(resource1.owner, community)
        self.assertEquals(resource1.name, "WoSo Forum")
        self.assertEquals(resource2.owner, community)
        self.assertEquals(resource2.name, "Ticker Tape Parade Pictures")
      
    def test_generate_text_from_template_of_simple_community(self):

        self.set_up_simple_community()
        
        permissions = PermissionsItem.objects.all()
        conditions = ConditionTemplate.objects.all()
        template_model = self.templateClient.make_template(community=self.instance, permissions=permissions,
            conditions=conditions, description="Simple Community Template")
        text = template_model.data.generate_text()

        self.assertEquals(len(text), 6)
        self.assertEquals(text["community_basic_info"], "Community USWNT is owned by individual 1 and governed by individual 1. ")
        self.assertEquals(text["community_governance_info"], 
            "By default, the owners do not need to approve actions in the community, on the condition that individual 1 approve. Unless otherwise specified, the governors of the community can take any action. ")
        self.assertEquals(text["community_members_info"], 'The members of this community are 13 and 4. ')
        self.assertEquals(text["community_roles_info"], "There is 1 custom role in the community, forwards. Individuals 3 and 4 are 'forwards'. ")
        self.assertEquals(text["community_permissions_info"], 
            "Everyone with role forwards and individual 10 can change name of community for USWNT, on the condition that individual 4 approve. ")
        self.assertEquals(text["owned_objects_basic_info"], "")
        
    def test_generate_text_from_template_of_complex_community(self):

        self.set_up_complex_community()
        permissions = PermissionsItem.objects.all()
        conditions = ConditionTemplate.objects.all()
        owned_objects = list(Resource.objects.all()) + list(Item.objects.all())
        template_model = self.templateClient.make_template(community=self.instance, permissions=permissions,
            conditions=conditions, owned_objects=owned_objects, description="Complex Community Template")
        text = template_model.data.generate_text()

        self.assertEquals(len(text), 8)
        self.assertEquals(text["community_basic_info"], "Community USWNT is owned by individual 1 and governed by individual 1. ")
        self.assertEquals(text["community_governance_info"], 
            "By default, the owners do not need to approve actions in the community, on the condition that individual 1 approve. Unless otherwise specified, the governors of the community can take any action. ")
        self.assertEquals(text["community_members_info"], 'The members of this community are 13 and 4. ')
        self.assertEquals(text["community_roles_info"], "There is 1 custom role in the community, forwards. Individuals 3 and 4 are 'forwards'. ")
        self.assertEquals(text["community_permissions_info"], 
            "Everyone with role forwards and individual 10 can change name of community for USWNT, on the condition that individual 4 approve. ")
        self.assertEquals(text["owned_objects_basic_info"], "The community owns 2 objects, Resource WoSo Forum and Resource Ticker Tape Parade Pictures. ") 
        self.assertEquals(text["owned_object_8"], "Everyone with role members can add item to resource for Ticker Tape Parade Pictures. Individual 10 can remove role from permission for AddItemResourceStateChange. ")
        self.assertEquals(text["owned_object_7"], "")

    def test_get_text_for_configured_permissions(self):
        """Tests text display for configured permissions."""

        # 'addpeopletorole' is a configured state change, so we create a community
        # where we can assign this permission

        self.commClient.add_role(role_name="forwards")
        self.commClient.add_role(role_name="backs")
        self.commClient.add_members([self.users.tobin.pk, self.users.sonny.pk, self.users.rose.pk])
        self.commClient.add_people_to_role(role_name="forwards", people_to_add=[self.users.tobin.pk])
        self.commClient.add_people_to_role(role_name="backs", people_to_add=[self.users.sonny.pk])

        self.permClient.add_permission(
            permission_type=Changes.Communities.AddPeopleToRole,
            permission_actors=[self.users.sonny.pk],
            permission_configuration={"role_name": "forwards"})

        # test this works - sonny should be able to add people to role "forwards" but not "backs"
        self.commClient.set_actor(actor=self.users.sonny)
        self.commClient.add_people_to_role(role_name="forwards", people_to_add=[self.users.rose.pk])
        self.commClient.add_people_to_role(role_name="backs", people_to_add=[self.users.rose.pk])
        rose_roles = self.instance.roles.get_roles_given_user(pk=self.users.rose.pk)
        self.assertEquals(rose_roles, ["forwards", "members"])

        # okay, now let's test we can make a template, and that this shows up in the template
        permissions = PermissionsItem.objects.all()
        template_model = self.templateClient.make_template(community=self.instance, permissions=permissions,
            description="Testing permission configuration")
        text = template_model.data.generate_text()
        self.assertEquals(text["community_permissions_info"], 
            "Individual 7 can add people to role 'forwards' for USWNT. ")

    def test_get_editable_fields(self):

        self.set_up_simple_community()
        permissions = PermissionsItem.objects.all()
        conditions = ConditionTemplate.objects.all()
        template_model = self.templateClient.make_template(community=self.instance, permissions=permissions,
            conditions=conditions, description="Simple Community Template")
        
        editable_fields = self.templateClient.get_editable_fields_on_template(template_model=template_model)

        # test we have the correct number of fields given the above structure
        self.assertEquals(len(editable_fields), 24)

        # test we have successfully removed relationship fields and autofields
        list_of_field_names = [field_dict["field_name"] for field_dict in editable_fields]
        self.assertNotIn("owner", list_of_field_names)
        self.assertNotIn("owner_object_id", list_of_field_names)
        self.assertNotIn("owner_content_type", list_of_field_names)
        self.assertNotIn("permitted_object_id", list_of_field_names)
        self.assertNotIn("conditioned_object_id", list_of_field_names)
        self.assertNotIn("id", list_of_field_names)

        # test we have correct structure for rolefield, rolelist field, actorlistfield
        editable_role_field = [field_dict for field_dict in editable_fields
            if (field_dict["field_name"] == "roles" and field_dict["object_model"] == "Community")][0]
        editable_role_list_field = [field_dict for field_dict in editable_fields
            if (field_dict["field_name"] == "roles" and field_dict["object_model"] == "PermissionsItem")][0]
        editable_actor_list_field = [field_dict for field_dict in editable_fields
            if (field_dict["field_name"] == "actors" and field_dict["object_model"] == "PermissionsItem")][0]
        self.assertEquals(editable_role_field["field_value"], self.instance.roles.get_roles())
        self.assertEquals(editable_role_list_field["field_value"], permissions[0].roles.role_list)
        self.assertEquals(editable_actor_list_field["field_value"], permissions[0].actors.as_pks())

    def test_update_template_field(self):

        # Generate a template and get editable fields
        self.set_up_simple_community()
        permissions = PermissionsItem.objects.all()
        conditions = ConditionTemplate.objects.all()
        template_model = self.templateClient.make_template(community=self.instance, permissions=permissions,
            conditions=conditions, description="Simple Community Template")
        self.templateClient.set_target(target=template_model)        
        editable_fields = self.templateClient.get_editable_fields_on_template(template_model=template_model)

        # Editing a simple field using valid data successfully updates template
        community_name_field = [field_dict for field_dict in editable_fields
            if (field_dict["field_name"] == "name" and field_dict["object_model"] == "Community")][0]       
        result = self.templateClient.edit_template_field(
            template_object_id=community_name_field["template_object_id"], field_name="name", 
            new_field_data="United States Women's National Team")
        self.templateClient.refresh_target()
        self.assertEquals(self.templateClient.target.data.generate_text()["community_basic_info"],
            "Community United States Women's National Team is owned by individual 1 and governed by individual 1. ")

        # Editing a custom field using valid data successfully updates template
        community_role_field = [field_dict for field_dict in editable_fields
            if (field_dict["field_name"] == "roles" and field_dict["object_model"] == "Community")][0] 
        new_role_value = {'forwards': [3, 4], 'mids': [1, 4], 'governors': {'actors': [1], 'roles': []}, 'owners': {'actors': [1], 'roles': []}, 'members': [1, 3, 4]}    
        result = self.templateClient.edit_template_field(
            template_object_id=community_name_field["template_object_id"], field_name="roles", 
            new_field_data=new_role_value)
        self.templateClient.refresh_target()
        self.assertEquals(self.templateClient.target.data.generate_text()["community_roles_info"],
            "There are 2 custom roles in the community: forwards and mids. Individuals 3 and 4 are 'forwards'. Individuals 1 and 4 are 'mids'. ")

        # Editing a custom field using invalid data does not update data, and returns error
        community_role_field = [field_dict for field_dict in editable_fields
            if (field_dict["field_name"] == "roles" and field_dict["object_model"] == "Community")][0] 
        new_role_value = 4
        action, result = self.templateClient.edit_template_field(
            template_object_id=community_name_field["template_object_id"], field_name="roles", 
            new_field_data=new_role_value)
        self.assertEquals(action.resolution.log,
            "Data supplied (4) is incorrectly formatted for RoleHandler field")

    def test_edit_field_and_get_new_data(self):
        
        # Generate a template and get editable fields
        self.set_up_simple_community()
        permissions = PermissionsItem.objects.all()
        conditions = ConditionTemplate.objects.all()
        template_model = self.templateClient.make_template(community=self.instance, permissions=permissions,
            conditions=conditions, description="Simple Community Template")
        self.templateClient.set_target(target=template_model)        
        editable_fields = self.templateClient.get_editable_fields_on_template(template_model=template_model)

        # Editing a simple field using the helper method "update_field_and_get_new_data"
        community_name_field = [field_dict for field_dict in editable_fields
            if (field_dict["field_name"] == "name" and field_dict["object_model"] == "Community")][0]       
        result = self.templateClient.update_field_and_get_new_data(
            template_object_id=community_name_field["template_object_id"], field_name="name",
            new_field_data="United States Women's National Team")
        self.assertEquals(result["template_text"]["community_basic_info"], 
            "Community United States Women's National Team is owned by individual 1 and governed by individual 1. ")
        community_name_field = [field_dict for field_dict in result["editable_fields"]
            if (field_dict["field_name"] == "name" and field_dict["object_model"] == "Community")][0] 
        self.assertEquals(community_name_field["field_value"], "United States Women's National Team")


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
        self.assertEquals(action.resolution.status, "rejected")

        # User Tobin with role 'forwards' can see object
        action, result = self.tobinResourceClient.get_target_data()
        self.assertEquals(action.resolution.status, "implemented")
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
        self.assertEquals(action.resolution.status, "rejected")
        self.assertTrue("Cannot view fields owner" in action.resolution.log)
        
        # They try to get the right field, success
        action, result = self.tobinResourceClient.get_target_data(fields_to_include=["name"])
        self.assertEquals(action.resolution.status, "implemented")
        self.assertEquals(result, {'name': 'Go USWNT!'})

        # They try to get two fields at once, success
        action, result = self.tobinResourceClient.get_target_data(fields_to_include=["name", "id"])
        self.assertEquals(action.resolution.status, "implemented")
        self.assertEquals(result, {'name': 'Go USWNT!', "id": 1})

        # They try to get one allowed field and one unallowed field, error
        action, result = self.tobinResourceClient.get_target_data(fields_to_include=["name", "owner"])
        self.assertEquals(action.resolution.status, "rejected")
        self.assertTrue("Cannot view fields owner" in action.resolution.log)

        # They try to get a nonexistent field, error
        action, result = self.tobinResourceClient.get_target_data(fields_to_include=["potato"])
        self.assertEquals(action.resolution.status, "rejected")
        self.assertTrue("Attempting to view field(s) potato that are not on target" in action.resolution.log)

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
        self.assertEquals(action.resolution.status, "implemented")
        self.assertEquals(result, {'name': 'Go USWNT!'})
        action, result = self.tobinResourceClient.get_target_data(fields_to_include=["owner"])
        self.assertEquals(action.resolution.status, "rejected")
        self.assertTrue("Cannot view fields owner" in action.resolution.log)

        # Rose can see owner but not name
        action, result = self.roseResourceClient.get_target_data(fields_to_include=["owner"])
        self.assertEquals(action.resolution.status, "implemented")
        self.assertEquals(result, {'owner': 'USWNT'})
        action, result = self.roseResourceClient.get_target_data(fields_to_include=["name"])
        self.assertEquals(action.resolution.status, "rejected")
        self.assertTrue("Cannot view fields name" in action.resolution.log)