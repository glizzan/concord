import json
from decimal import Decimal
import time

from django.test import TestCase
from django.contrib.contenttypes.models import ContentType

from concord.resources.client import ResourceClient
from concord.permission_resources.client import PermissionResourceClient
from concord.conditionals.client import (ApprovalConditionClient, VoteConditionClient, 
    PermissionConditionalClient, CommunityConditionalClient)
from concord.communities.client import CommunityClient

from concord.communities.forms import RoleForm
from concord.permission_resources.forms import PermissionForm, MetaPermissionForm
from concord.conditionals.forms import ConditionSelectionForm, conditionFormDict
from concord.actions.models import Action  # For testing action status later, do we want a client?
from concord.permission_resources.models import PermissionsItem
from concord.conditionals.models import ApprovalCondition


### TODO: 

# 1. Update the clients to return a model wrapped in a client, so that we actually
# enforce the architectural rule of 'only client can be referenced outside the app'
# since tests.py is 100% outside the app.

# 2. Rethink how the client works right now.  It's super tedious switching between the different
# types of clients in the tests here, always setting actor, target, etc.  Possibly make a
# mega-client, so eg PermissionClient can be accessed as client.permissions.add_permission().


class ResourceModelTests(TestCase):

    def setUp(self):
        self.rc = ResourceClient(actor="shauna")

    def test_create_resource(self):
        """
        Test creation of simple resource through client, and its method
        get_unique_id.
        """
        resource = self.rc.create_resource(name="Aha")
        self.assertEquals(resource.get_unique_id(), "resources_resource_1")

    def test_add_item_to_resource(self):
        """
        Test creation of item and addition to resource.
        """
        resource = self.rc.create_resource(name="Aha")
        self.rc.set_target(target=resource)
        action, item = self.rc.add_item(item_name="Aha")
        self.assertEquals(item.get_unique_id(), "resources_item_1")

    def test_remove_item_from_resource(self):
        """
        Test removal of item from resource.
        """
        resource = self.rc.create_resource(name="Aha")
        self.rc.set_target(target=resource)
        action, item = self.rc.add_item(item_name="Aha")
        self.assertEquals(resource.get_items(), ["Aha"])
        self.rc.remove_item(item_pk=item.pk)
        self.assertEquals(resource.get_items(), [])


class PermissionResourceModelTests(TestCase):

    def setUp(self):
        self.rc = ResourceClient(actor="shauna")
        self.prc = PermissionResourceClient(actor="shauna")

    def test_add_permission_to_resource(self):
        """
        Test addition of permisssion to resource.
        """
        # FIXME: these permissions are invalid, replace with real permissions
        resource = self.rc.create_resource(name="Aha")
        self.prc.set_target(target=resource)
        action, permission = self.prc.add_permission(
            permission_type="concord.resources.state_changes.AddItemResourceStateChange",
            permission_actors=["shauna"])
        items = self.prc.get_permissions_on_object(object=resource)
        self.assertEquals(items.first().get_name(), 'Permission 1 (for concord.resources.state_changes.AddItemResourceStateChange on Resource object (1))')

    def test_remove_permission_from_resource(self):
        """
        Test removal of permission from resource.
        """
        # FIXME: these permissions are invalid, replace with real permissions
        resource = self.rc.create_resource(name="Aha")
        self.prc.set_target(target=resource)
        action, permission = self.prc.add_permission(
            permission_type="concord.resources.state_changes.AddItemResourceStateChange",
            permission_actors=["shauna"])
        items = self.prc.get_permissions_on_object(object=resource)
        self.assertEquals(items.first().get_name(), 'Permission 1 (for concord.resources.state_changes.AddItemResourceStateChange on Resource object (1))')
        self.prc.remove_permission(item_pk=permission.pk)
        items = self.prc.get_permissions_on_object(object=resource)
        self.assertEquals(list(items), [])


class PermissionSystemTest(TestCase):
    """
    The previous two sets of tests use the default permissions setting for the items
    they're modifying.  For individually owned objects, this means that the owner can do 
    whatever they want and no one else can do anything.  This set of tests looks at the basic 
    functioning of the permissions system including permissions set on permissions.
    """

    def setUp(self):
        self.rc = ResourceClient(actor="shauna")
        self.prc = PermissionResourceClient(actor="shauna")

    def test_permissions_system(self):
        """
        Create a resource and add a specific permission for a non-owner actor.
        """
        resource = self.rc.create_resource(name="Aha")
        self.prc.set_target(target=resource)
        action, permission = self.prc.add_permission(
            permission_type="concord.resources.state_changes.AddItemResourceStateChange",
            permission_actors=["buffy"])
        items = self.prc.get_permissions_on_object(object=resource)
        self.assertEquals(items.first().get_name(), 
            'Permission 1 (for concord.resources.state_changes.AddItemResourceStateChange on Resource object (1))')

        # Now let's have Buffy do a thing on the resource
        brc = ResourceClient(actor="buffy", target=resource)
        action, item = brc.add_item(item_name="Test New")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(item.name, "Test New")

    def test_recursive_permission(self):
        """
        Tests setting permissions on permission.
        """

        # Shauna creates a resource and adds a permission to the resource.
        resource = self.rc.create_resource(name="Aha")
        self.prc.set_target(target=resource)
        action, permission = self.prc.add_permission(
            permission_type="concord.resources.state_changes.AddItemResourceStateChange",
            permission_actors=["willow"])

        # Buffy can't add an item to this resource because she's not the owner nor specified in
        # the permission.        
        brc = ResourceClient(actor="buffy", target=resource)
        action, item = brc.add_item(item_name="Buffy's item")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")

        # Shauna adds a permission on the permission which Buffy does have.
        self.prc.set_target(target=permission)
        action, rec_permission = self.prc.add_permission(
            permission_type="concord.permission_resources.state_changes.AddPermissionStateChange",
            permission_actors=["buffy"])
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

        # Buffy still cannot make the change because she does not have the permission.
        brc = ResourceClient(actor="buffy", target=resource)
        action, item = brc.add_item(item_name="Buffy's item")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        
        # BUT Buffy CAN make the second-level change.
        bprc = PermissionResourceClient(actor="buffy", target=permission)
        action, permission = bprc.add_permission(permission_type="concord.permission_resources.state_changes.AddPermissionStateChange",
            permission_actors=["willow"])        
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")


class ConditionalsTest(TestCase):

    def setUp(self):
        self.cc = PermissionConditionalClient(actor="shauna")
        self.rc = ResourceClient(actor="shauna")
        self.prc = PermissionResourceClient(actor="shauna")
        self.target = self.rc.create_resource(name="Aha")
        self.action = Action.objects.create(actor="elena", target=self.target,
            change_type="concord.resources.state_changes.ChangeResourceNameStateChange",
            change_data=json.dumps({"new_name": "Hah"}))

    def test_create_vote_conditional(self):
        default_vote = self.cc.createVoteCondition(action=self.action)
        self.assertEquals(default_vote.publicize_votes(), False)
        public_vote = self.cc.createVoteCondition(publicize_votes=True, action=self.action)
        self.assertEquals(public_vote.publicize_votes(), True)

    def test_add_vote_to_vote_conditional(self):
        default_vote = self.cc.createVoteCondition(action=self.action)
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
        # Create vote condition and set permission on it
        default_vote = self.cc.createVoteCondition(action=self.action)

        self.prc.set_target(target=default_vote.target)  # FIXME: this is hacky

        vote_permission = self.prc.add_permission(
            permission_type="concord.conditionals.state_changes.AddVoteStateChange",
            permission_actors=["buffy"])
        vote_permission = self.prc.add_permission(
            permission_type="concord.conditionals.state_changes.AddVoteStateChange",
            permission_actors=["willow"])            

        # Now Buffy and Willow can vote but Xander can't
        self.cc = PermissionConditionalClient(actor="buffy")
        default_vote = self.cc.getVoteConditionAsClient(pk=default_vote.target.pk)
        default_vote.vote(vote="yea")
        self.assertDictEqual(default_vote.get_current_results(), 
            { "yeas": 1, "nays": 0, "abstains": 0 })
        self.cc = PermissionConditionalClient(actor="willow")
        default_vote = self.cc.getVoteConditionAsClient(pk=default_vote.target.pk)
        default_vote.vote(vote="abstain")
        self.assertDictEqual(default_vote.get_current_results(), 
            { "yeas": 1, "nays": 0, "abstains": 1})
        self.cc = PermissionConditionalClient(actor="xander")
        default_vote = self.cc.getVoteConditionAsClient(pk=default_vote.target.pk)
        default_vote.vote(vote="abstain")
        self.assertDictEqual(default_vote.get_current_results(), 
            { "yeas": 1, "nays": 0, "abstains": 1})         

    def test_approval_conditional(self):
        """
        Tests that changes to a resource require approval from a specific person,
        check that that person can approve the change and others can't.
        """

        # First we have Shauna create a resource
        resource = self.rc.create_resource(name="Aha")

        # Then she adds a permission that says that Buffy can add items.
        self.prc.set_target(target=resource)
        action, permission = self.prc.add_permission(permission_type="concord.resources.state_changes.AddItemResourceStateChange",
            permission_actors=["buffy"])
        
        # But she places a condition on the permission that Buffy has to get
        # approval (without specifying permissions, so it uses the default.
        self.cc.set_target(target=permission)
        self.cc.addCondition(condition_type="approvalcondition")

        # Now when Xander tries to add an item he is flat out rejected
        self.rc.set_actor(actor="xander")
        self.rc.set_target(target=resource)
        action, item = self.rc.add_item(item_name="Xander's item")
        self.assertEquals(resource.get_items(), [])
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")

        # When Buffy tries to add an item it is stuck waiting
        self.rc.set_actor(actor="buffy")
        buffy_action, item = self.rc.add_item(item_name="Buffy's item")
        self.assertEquals(resource.get_items(), [])
        self.assertEquals(Action.objects.get(pk=buffy_action.pk).status, "waiting")

        # Get the conditional action
        conditional_action = self.cc.get_condition_item_given_action(action_pk=buffy_action.pk)

        # Xander tries to approve it and fails.  Xander you goof.
        acc = ApprovalConditionClient(target=conditional_action, actor="xander")
        action, result = acc.approve()
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(resource.get_items(), [])

        # Now Shauna approves it
        acc.set_actor(actor="shauna")
        action, result = acc.approve()
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
    
        # And Buffy's item has been added
        self.assertEquals(Action.objects.get(pk=buffy_action.pk).status, "implemented")
        self.assertEquals(resource.get_items(), ["Buffy's item"])

        
    def test_approval_conditional_with_second_order_permission(self):
        """
        Mostly the same as above, but instead of using the default permission on
        the conditional action, we specify that someone specific has to approve
        the action.
        """

        # First we have Shauna create a resource
        resource = self.rc.create_resource(name="Aha")

        # Then she adds a permission that says that Buffy can add items.
        self.prc.set_target(target=resource)
        action, permission = self.prc.add_permission(permission_type="concord.resources.state_changes.AddItemResourceStateChange",
            permission_actors=["buffy"])
        
        # But she places a condition on the permission that Buffy has to get
        # approval.  She specifies that *Willow* has to approve it.
        self.cc.set_target(target=permission)
        self.cc.addCondition(condition_type="approvalcondition",
            permission_data=json.dumps({
                'permission_type': 'concord.conditionals.state_changes.ApproveStateChange', 
                'permission_actors': ['willow'],
                'permission_roles': [],
                'permission_configuration': '{}'}))

        # When Buffy tries to add an item it is stuck waiting
        self.rc.set_actor(actor="buffy")
        self.rc.set_target(target=resource)
        buffy_action, item = self.rc.add_item(item_name="Buffy's item")
        self.assertEquals(resource.get_items(), [])
        self.assertEquals(Action.objects.get(pk=buffy_action.pk).status, "waiting")

        # Get the conditional action
        conditional_action = self.cc.get_condition_item_given_action(action_pk=buffy_action.pk)

       # Now Willow approves it
        acc = ApprovalConditionClient(target=conditional_action, actor="willow")
        action, result = acc.approve()
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
    
        # And Buffy's item has been added
        self.assertEquals(Action.objects.get(pk=buffy_action.pk).status, "implemented")
        self.assertEquals(resource.get_items(), ["Buffy's item"])

    def test_cant_self_approve(self):
        # TODO: add this test!
        ...


class ConditionalsFormTest(TestCase):
    
    def setUp(self):

        # Create users
        self.user = "buffy"
        self.willow = "willow"
        self.faith = "faith"
        self.tara = "tara"

        # Create a community
        self.commClient = CommunityClient(actor=self.user)
        self.instance = self.commClient.create_community(name="Scooby Gang")
        self.commClient.set_target(self.instance)

        # Make separate clients 
        self.willowClient = CommunityClient(actor="willow", target=self.instance)
        self.faithClient = CommunityClient(actor="faith", target=self.instance)
        self.taraClient = CommunityClient(actor="tara", target=self.instance)

        # Create request objects
        import collections
        User = collections.namedtuple('User', 'username')
        Request = collections.namedtuple('Request', 'user')
        self.request = Request(user=User(username=self.user))
        self.willowRequest = Request(user=User(username="willow"))  # Not sure it's necessary
        self.faithRequest = Request(user=User(username="faith"))  # Not sure it's necessary
        self.taraRequest = Request(user=User(username="tara"))

        # Create a permission to set a condition on 
        self.prc = PermissionResourceClient(actor=self.user, target=self.instance)
        action, result = self.prc.add_permission(permission_type="concord.resources.state_changes.ChangeResourceNameStateChange",
            permission_actors=["willow"])
        self.target_permission = result

        # Create PermissionConditionalClient
        self.pcc = PermissionConditionalClient(actor=self.user, target=self.target_permission)

        # Create permissions data for response dict
        self.response_dict = {}
        self.prClient = PermissionResourceClient(actor=self.user, target=ApprovalCondition)
        permissions = self.prClient.get_settable_permissions(return_format="permission_objects")
        for count, permission in enumerate(permissions):
            self.response_dict[str(count) + "~" + "name"] = permission.get_change_type()
            self.response_dict[str(count) + "~" + "roles"] = []
            self.response_dict[str(count) + "~" + "individuals"] = []
            for field in permission.get_configurable_fields():
                self.response_dict['%s~configurablefield~%s' % (count, field)] = ""

        # Create a resource
        self.rc = ResourceClient(actor=self.user)

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
            '{"allow_abstain": false, "require_majority": true, "publicize_votes": false, "voting_period": 5.0}')

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
            '{"allow_abstain": false, "require_majority": true, "publicize_votes": true, "voting_period": 30.0}')

    def test_approval_condition_processes_permissions_data(self):

        # Create condition template
        ApprovalForm = conditionFormDict["approvalcondition"]
        self.response_dict['self_approval_allowed'] = True
        self.response_dict['0~individuals'] = "willow"
        approvalForm = ApprovalForm(permission=self.target_permission, request=self.request, 
            data=self.response_dict)

        approvalForm.is_valid()
        approvalForm.save()
        condTemplate = self.pcc.get_condition_template()
        self.assertEquals(json.loads(condTemplate.permission_data), 
                {"permission_type": "concord.conditionals.state_changes.ApproveStateChange", "permission_actors": "willow", "permission_roles": [], "permission_configuration": {}})

    def test_approval_condition_form_creates_working_condition(self):
        
        # First Buffy creates a resource
        resource = self.rc.create_resource(name="Scooby Gang Forum")

        # Then she adds a permission that says that Tara can add items.
        self.prc.set_target(target=resource)
        action, permission = self.prc.add_permission(permission_type="concord.resources.state_changes.AddItemResourceStateChange",
            permission_actors=["tara"])

        # Buffy uses the form to place a condition on the permission she just created, such that
        # Tara's action needs Willow's approval.
        ApprovalForm = conditionFormDict["approvalcondition"]
        self.response_dict['0~individuals'] = "willow"
        approvalForm = ApprovalForm(permission=permission, request=self.request, 
            data=self.response_dict)
        approvalForm.is_valid()
        approvalForm.save()

        # When Tara tries to add an item it is stuck waiting
        self.rc.set_actor(actor="tara")
        self.rc.set_target(target=resource)
        tara_action, item = self.rc.add_item(item_name="Tara's item")
        self.assertEquals(resource.get_items(), [])
        self.assertEquals(Action.objects.get(pk=tara_action.pk).status, "waiting")

        # Get the condition item created by action
        self.cc = PermissionConditionalClient(actor="buffy")
        condition = self.cc.get_condition_item_given_action(action_pk=tara_action.pk)

        # Now Willow approves it
        acc = ApprovalConditionClient(target=condition, actor="willow")
        action, result = acc.approve()
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

        # And Tara's item has been added
        self.assertEquals(Action.objects.get(pk=tara_action.pk).status, "implemented")
        self.assertEquals(resource.get_items(), ["Tara's item"])

    def test_editing_condition_allows_editing_of_permissions(self):

         # Create condition template with permissions info
         ApprovalForm = conditionFormDict["approvalcondition"]
         self.response_dict['self_approval_allowed'] = True
         self.response_dict['0~individuals'] = "willow"
         approvalForm = ApprovalForm(permission=self.target_permission, request=self.request, 
             data=self.response_dict)
         approvalForm.is_valid()
         approvalForm.save()
         condTemplate = self.pcc.get_condition_template()
         self.assertEquals(condTemplate.condition_data, '{"self_approval_allowed": true}')
         self.assertEquals(json.loads(condTemplate.permission_data)["permission_actors"], "willow")
 
         # Feed into form as instance along with edited data
         self.response_dict['self_approval_allowed'] = False
         self.response_dict['0~individuals'] = "faith"
         approvalForm2 = ApprovalForm(instance=condTemplate, permission=self.target_permission, 
             request=self.request, data=self.response_dict)
         approvalForm2.is_valid()
         approvalForm2.save()
 
         # Now configuration is different
         condTemplate = self.pcc.get_condition_template()
         self.assertEquals(condTemplate.condition_data, '{"self_approval_allowed": false}')
         self.assertEquals(json.loads(condTemplate.permission_data)["permission_actors"], "faith")

    # TODO: Test you can set a condition on metapermission as well as permission, specifically I'm 
    # worried that there might be issues determining ownership.


class BasicCommunityTest(TestCase):

    def setUp(self):
        self.commClient = CommunityClient(actor="shauna")

    def test_create_community(self):
        community = self.commClient.create_community(name="A New Community")
        self.assertEquals(community.get_unique_id(), "communities_community_1")
        self.assertEquals(community.name, "A New Community")
    
    def test_community_is_itself_collectively_owned(self):
        community = self.commClient.create_community(name="A New Community")
        self.assertEquals(community.get_owner(), community.name)

    def test_community_collectively_owns_resource(self):
        community = self.commClient.create_community(name="A New Community")
        rc = ResourceClient(actor="shauna")
        resource = rc.create_resource(name="A New Resource")
        self.assertEquals(resource.get_owner(), "shauna")
        rc.set_target(target=resource)
        rc.change_owner_of_target(new_owner="A New Community", new_owner_type="com")
        self.assertEquals(resource.get_owner(), "A New Community")

    def test_change_name_of_community(self):
        community = self.commClient.create_community(name="A New Community")
        self.commClient.set_target(target=community)
        action, result = self.commClient.change_name(new_name="A Newly Named Community")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(community.name, "A Newly Named Community")

    def test_reject_change_name_of_community_from_nongovernor(self):
        community = self.commClient.create_community(name="A New Community")
        self.commClient.set_target(target=community)
        self.commClient.set_actor(actor="xander")
        action, result = self.commClient.change_name(new_name="A Newly Named Community")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(community.name, "A New Community")

    def test_change_name_of_community_owned_resource(self):
        # SetUp
        community = self.commClient.create_community(name="A New Community")
        rc = ResourceClient(actor="shauna")
        resource = rc.create_resource(name="A New Resource")
        rc.set_target(target=resource)
        action, result = rc.change_owner_of_target(new_owner="A New Community", new_owner_type="com")
        self.assertEquals(resource.get_owner(), "A New Community")
        # Test
        new_action, result = rc.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=new_action.pk).status, "implemented")
        self.assertEquals(resource.name, "A Changed Resource")

    def test_reject_change_name_of_community_owned_resource_from_nongovernor(self):
        # SetUp
        community = self.commClient.create_community(name="A New Community")
        rc = ResourceClient(actor="shauna")
        resource = rc.create_resource(name="A New Resource")
        rc.set_target(target=resource)
        action, result = rc.change_owner_of_target(new_owner="A New Community", new_owner_type="com")
        self.assertEquals(resource.get_owner(), "A New Community")
        # Test
        rc.set_actor(actor="xander")
        new_action, result = rc.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=new_action.pk).status, "rejected")
        self.assertEquals(resource.name, "A New Resource")

    def test_add_permission_to_community_owned_resource_allowing_nongovernor_to_change_name(self):
        
        # SetUp
        community = self.commClient.create_community(name="A New Community")
        rc = ResourceClient(actor="shauna")
        resource = rc.create_resource(name="A New Resource")
        rc.set_target(target=resource)
        action, result = rc.change_owner_of_target(new_owner="A New Community", new_owner_type="com")
        self.assertEquals(resource.get_owner(), "A New Community")

        # Add  permission for nongovernor to change name
        prc = PermissionResourceClient(actor="shauna")
        prc.set_target(target=resource)
        action, permission = prc.add_permission(permission_type="concord.resources.state_changes.ChangeResourceNameStateChange",
            permission_actors=["xander"])
        
        # Test - Xander should now be allowed to change name
        rc.set_actor(actor="xander")
        new_action, result = rc.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=new_action.pk).status, "implemented")
        self.assertEquals(resource.name, "A Changed Resource")    

        # Test - Governors should still be able to do other things still that are not set in PR
        rc.set_actor(actor="shauna")
        new_action, result = rc.add_item(item_name="Shauna's item")
        self.assertEquals(resource.get_items(), ["Shauna's item"])

    def test_add_governor(self):
        community = self.commClient.create_community(name="A New Community")
        self.commClient.set_target(community)
        action, result = self.commClient.add_governor(governor_name="alexandra")
        self.assertEquals(community.authorityhandler.get_governors(),
            {'actors': ['shauna', 'alexandra'], 'roles': []})


class GoverningAuthorityTest(TestCase):

    def setUp(self):
        self.commClient = CommunityClient(actor="shauna")
        self.community = self.commClient.create_community(name="A New Community")
        self.commClient.set_target(target=self.community)
        self.commClient.add_governor(governor_name="alexandra")
        self.condClient = CommunityConditionalClient(actor="shauna", target=self.community)

    def test_with_conditional_on_governer_decision_making(self):

        # Set conditional on governor decision making.  Only Alexandra can approve condition.
        action, result = self.condClient.addConditionToGovernors(
            condition_type="approvalcondition",
            permission_data=json.dumps({
                'permission_type': 'concord.conditionals.state_changes.ApproveStateChange',
                'permission_actors': ['alexandra'],
                'permission_roles': '',
                'permission_configuration': '{}'}))
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented") # Action accepted

        # Check that the condition template's owner is correct
        ct = self.condClient.get_condition_template_for_governor()
        self.assertEquals(ct.get_owner(), "A New Community")

        # Governor A does a thing, creates a conditional action to be approved
        action, result = self.commClient.change_name(new_name="A Newly Named Community")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "waiting")
        self.assertEquals(self.community.name, "A New Community")
        conditional_action = self.condClient.get_condition_item_given_action(action_pk=action.pk)

        # Governer B reviews
        acc = ApprovalConditionClient(target=conditional_action, actor="alexandra")
        review_action, result = acc.approve()
        self.assertEquals(Action.objects.get(pk=review_action.pk).status, "implemented")

        # Now governor A's thing passes.
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        community = self.commClient.get_community(community_pk=self.community.pk) # Refresh
        self.assertEquals(community.name, "A Newly Named Community")


class FoundationalAuthorityTest(TestCase):

    def setUp(self):

        # Create community
        self.commClient = CommunityClient(actor="shauna")
        self.community = self.commClient.create_community(name="A New Community")

        # Create a resource and give ownership to community
        self.resourceClient = ResourceClient(actor="shauna")
        self.resource = self.resourceClient.create_resource(name="A New Resource")
        self.resourceClient.set_target(target=self.resource)
        self.resourceClient.change_owner_of_target(new_owner="A New Community", new_owner_type="com")

    def test_foundational_authority_override_on_individually_owned_object(self):
        # Create individually owned resource
        resource = self.resourceClient.create_resource(name="A resource")

        # By default, Dana's actions are not successful
        danaResourceClient = ResourceClient(actor="dana", target=resource)
        action, result = danaResourceClient.change_name(new_name="Dana's resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(resource.get_name(), "A resource")

        # Owner adds a specific permission for Dana, Dana's action is successful
        prc = PermissionResourceClient(actor="shauna", target=resource)
        owner_action, result = prc.add_permission(permission_type="concord.resources.state_changes.ChangeResourceNameStateChange",
            permission_actors=["dana"])
        action, result = danaResourceClient.change_name(new_name="Dana's resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(resource.get_name(), "Dana's resource")

        # Now switch foundational override.
        fp_action, result = prc.enable_foundational_permission()

        # Dana's actions are no longer successful
        danaResourceClient = ResourceClient(actor="dana", target=resource)
        action, result = danaResourceClient.change_name(new_name="A new name for Dana's resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(resource.get_name(), "Dana's resource")

    def test_foundational_authority_override_on_community_owned_object(self):
        
        # By default, Dana's actions are not successful
        danaResourceClient = ResourceClient(actor="dana", target=self.resource)
        action, result = danaResourceClient.change_name(new_name="Dana's resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.get_name(), "A New Resource")

        # Owner adds a specific permission for Dana, Dana's action is successful
        prc = PermissionResourceClient(actor="shauna", target=self.resource)
        owner_action, result = prc.add_permission(permission_type="concord.resources.state_changes.ChangeResourceNameStateChange",
            permission_actors=["dana"])
        action, result = danaResourceClient.change_name(new_name="Dana's resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(self.resource.get_name(), "Dana's resource")

        # Now switch foundational override.
        # NOTE: it's a little weird that base client stuff is accessible from everywhere, no?
        fp_action, result = prc.enable_foundational_permission()

        # Dana's actions are no longer successful
        danaResourceClient = ResourceClient(actor="dana", target=self.resource)
        action, result = danaResourceClient.change_name(new_name="A new name for Dana's resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.get_name(), "Dana's resource")

    def test_foundational_authority_override_on_community_owned_object_with_conditional(self):
        
        # Shauna, Amal, Dana and Joy are members of community X.  
        self.commClient.set_target(self.community)
        action, result = self.commClient.add_member(name="amal")
        action, result = self.commClient.add_member(name="dana")
        action, result = self.commClient.add_member(name="joy")
        com_members = self.commClient.get_members()
        self.assertCountEqual(com_members, ["shauna", "amal", "dana", "joy"])

        # In this community, all members are owners but for the foundational authority to do
        # anything they must agree via majority vote.
        action, result = self.commClient.add_owner_role(owner_role="members") # Add member role
        self.condClient = CommunityConditionalClient(actor="shauna", target=self.community)

        # FIXME: wow this is too much configuration needed!
        action, result = self.condClient.addConditionToOwners(
            condition_type = "votecondition",
            permission_data = json.dumps({
                'permission_type': 'concord.conditionals.state_changes.AddVoteStateChange',
                'permission_actors': '[]',
                'permission_roles': ['1_members'],
                'permission_configuration': '{}'}),
            condition_data=json.dumps({"voting_period": 0.0001 }))

        # Dana tries to change the name of the resource but is not successful.
        danaResourceClient = ResourceClient(actor="dana", target=self.resource)
        action, result = danaResourceClient.change_name(new_name="Dana's resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.get_name(), "A New Resource")

        # Dana tries to switch on foundational override.  This goes to foundational authority
        # and it generates a vote.  Everyone votes and it's approved. 
        key_action, result = danaResourceClient.enable_foundational_permission()
        self.assertEquals(Action.objects.get(pk=key_action.pk).status, "waiting")
        conditional_action = self.condClient.get_condition_item_given_action(action_pk=key_action.pk)

        vcc = VoteConditionClient(target=conditional_action, actor="shauna")
        vcc.vote(vote="yea")
        vcc.set_actor("amal")
        vcc.vote(vote="yea")
        vcc.set_actor("joy")
        vcc.vote(vote="yea")
        vcc.set_actor("dana")
        vcc.vote(vote="yea")

        time.sleep(.02)

        self.assertEquals(Action.objects.get(pk=key_action.pk).status, "implemented")
        resource = self.resourceClient.get_resource_given_pk(pk=self.resource.pk)
        self.assertTrue(resource[0].foundational_permission_enabled)

    def test_change_governors_requires_foundational_authority(self):
        # Shauna is the owner, Shauna and Alexandra are governors.
        self.commClient.set_target(self.community)
        action, result = self.commClient.add_governor(governor_name="alexandra")
        self.assertEquals(self.community.authorityhandler.get_governors(),
            {'actors': ['shauna', 'alexandra'], 'roles': []})

        # Dana tries to add Joy as a governor.  She cannot, she is not an owner.
        self.commClient.set_actor("dana")
        action, result = self.commClient.add_governor(governor_name="joy")
        self.assertEquals(self.community.authorityhandler.get_governors(), 
            {'actors': ['shauna', 'alexandra'], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")

        # Alexandra tries to add Joy as a governor.  She cannot, she is not a governor.
        self.commClient.set_actor("alexandra")
        action, result = self.commClient.add_governor(governor_name="joy")
        self.assertEquals(self.community.authorityhandler.get_governors(), 
            {'actors': ['shauna', 'alexandra'], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")

        # Shauna tries to add Joy as a governor.  She can, since has foundational authority.
        self.commClient.set_actor("shauna")
        action, result = self.commClient.add_governor(governor_name="joy")
        self.assertEquals(self.community.authorityhandler.get_governors(), 
            {'actors': ['shauna', 'alexandra', 'joy'], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

    def test_change_owners_requires_foundational_authority(self):

        # Shauna adds Alexandra as owner.  There are now two owners with no conditions.
        self.commClient.set_target(self.community)
        action, result = self.commClient.add_owner(owner_name="alexandra")
        self.assertEquals(self.community.authorityhandler.get_owners(), 
            {'actors': ['shauna', 'alexandra'], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

        # Dana tries to add Amal as owner.  She cannot, she is not an owner.
        self.commClient.set_actor("dana")
        action, result = self.commClient.add_owner(owner_name="amal")
        self.assertEquals(self.community.authorityhandler.get_owners(), 
            {'actors': ['shauna', 'alexandra'], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")

        # Alexandra tries to add Amal as owner.  She can, since has foundational authority.
        self.commClient.set_actor("alexandra")
        action, result = self.commClient.add_owner(owner_name="amal")
        # self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

        self.assertEquals(self.community.authorityhandler.get_owners(), 
            {'actors': ['shauna', 'alexandra', 'amal'], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

    def test_change_foundational_override_requires_foundational_authority(self):
        # Shauna is the owner, Shauna and Alexandra are governors.
        self.commClient.set_target(self.community)
        action, result = self.commClient.add_governor(governor_name="alexandra")
        self.assertEquals(self.community.authorityhandler.get_governors(), 
            {'actors': ['shauna', 'alexandra'], 'roles': []})
        self.resourceClient.set_target(self.resource)

        # Dana tries to enable foundational override on resource. 
        # She cannot, she is not an owner.
        self.resourceClient.set_actor("dana")
        action, result = self.resourceClient.enable_foundational_permission()
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertFalse(self.resource.foundational_permission_enabled)

        # Alexandra tries to enable foundational override on resource.
        # She cannot, she is not a governor.
        self.resourceClient.set_actor("alexandra")
        action, result = self.resourceClient.enable_foundational_permission()
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertFalse(self.resource.foundational_permission_enabled)

        # Shauna tries to enable foundational override on resource.
        # She can, since has foundational authority.
        self.resourceClient.set_actor("shauna")
        action, result = self.resourceClient.enable_foundational_permission()
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertTrue(self.resource.foundational_permission_enabled)


class RolesetTest(TestCase):

    def setUp(self):
        self.commClient = CommunityClient(actor="shauna")
        self.community = self.commClient.create_community(name="A New Community")
        self.commClient.set_target(self.community)
        self.resourceClient = ResourceClient(actor="shauna")
        self.resource = self.resourceClient.create_resource(name="A new resource")
        self.resourceClient.set_target(self.resource)
        self.permClient = PermissionResourceClient(actor="shauna")

    # Test assigned roles

    def test_basic_assigned_role(self):
        # No roles so far
        roles = self.commClient.get_assigned_roles()
        self.assertEquals(roles, {'members': ['shauna']})

        # Add a role
        action, result = self.commClient.add_assigned_role(role_name="administrators")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        roles = self.commClient.get_assigned_roles()
        self.assertEquals(roles, {'members': ['shauna'], 'administrators': []})

        # Add people to role
        action, result = self.commClient.add_people_to_role(role_name="administrators", 
            people_to_add=["helga", "jon"])
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        roles = self.commClient.get_assigned_roles()
        self.assertCountEqual(roles["administrators"], ["helga", "jon"])

        # Remove person from role
        action, result = self.commClient.remove_people_from_role(role_name="administrators", 
            people_to_remove=["jon"])
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        roles = self.commClient.get_assigned_roles()
        self.assertCountEqual(roles["administrators"], ["helga"])

        # Remove role
        action, result = self.commClient.remove_assigned_role(role_name="administrators")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        roles = self.commClient.get_assigned_roles()
        self.assertEquals(roles, {'members': ['shauna']})

    def test_basic_assigned_role_works_with_permission_item(self):

        # Dana wants to change the name of the resource, she can't
        self.resourceClient.set_actor("dana")
        action, result = self.resourceClient.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.name, "A new resource")

        # Shauna adds a 'namers' role to the community which owns the resource
        self.resourceClient.set_actor("shauna")
        action, result = self.commClient.add_assigned_role(role_name="namers")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        roles = self.commClient.get_assigned_roles()
        self.assertEquals(roles, {'members': ['shauna'], 'namers': []})

        # Shauna creates a permission item with the 'namers' role in it
        self.permClient.set_target(self.resource)
        role_pair = str(self.community.pk) + "_" + "namers"  # FIXME: needs too much syntax knowledge 
        action, result = self.permClient.add_permission(permission_type="concord.resources.state_changes.ChangeResourceNameStateChange",
            permission_role_pairs=[role_pair])
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")

        # Shauna adds Dana to the 'namers' role in the community
        action, result = self.commClient.add_people_to_role(role_name="namers", 
            people_to_add=["dana"])
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        roles = self.commClient.get_assigned_roles()
        self.assertCountEqual(roles["namers"], ["dana"])

        # Dana can now change the name of the resource
        self.resourceClient.set_actor("dana")
        action, result = self.resourceClient.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(self.resource.name, "A Changed Resource")

        # Shauna removes Dana from the namers role in the community
        action, result = self.commClient.remove_people_from_role(role_name="namers", 
            people_to_remove=["dana"])
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        roles = self.commClient.get_assigned_roles()
        self.assertCountEqual(roles["namers"], [])

        # Dana can no longer change the name of the resource
        self.resourceClient.set_actor("dana")
        action, result = self.resourceClient.change_name(new_name="A Newly Changed Resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.name, "A Changed Resource")

    def test_basic_assigned_role_works_with_authorityhandler_governor(self):        

        # Shauna adds the resource to her community
        self.resourceClient.set_target(target=self.resource)
        self.resourceClient.change_owner_of_target(new_owner="A New Community", new_owner_type="com")

        # Dana wants to change the name of the resource, she can't
        self.resourceClient.set_actor("dana")
        action, result = self.resourceClient.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.name, "A new resource")

        # Shauna adds member role to governors
        action, result = self.commClient.add_governor_role(governor_role="members")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        gov_info = self.commClient.get_governorship_info()
        self.assertAlmostEquals(gov_info, {'actors': ['shauna'], 'roles': ['1_members']})

        # Dana tries to do a thing and can't
        action, result = self.resourceClient.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.name, "A new resource")

        # Shauna adds Dana to members
        action, result = self.commClient.add_member(name="dana")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        roles = self.commClient.get_assigned_roles()
        self.assertCountEqual(roles["members"], ["dana", "shauna"]) 

        # Dana tries to do a thing and can
        action, result = self.resourceClient.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(self.resource.name, "A Changed Resource")

    def test_add_member_and_remove_member_from_roleset(self):
        self.assertEquals(self.commClient.get_members(), ['shauna'])

        # Shauna adds Dana to the community
        self.commClient.add_member(name="dana")
        self.assertCountEqual(self.commClient.get_members(), ['shauna', 'dana'])

        # Shauna removes Dana from the community
        self.commClient.remove_member(name="dana")
        self.assertEquals(self.commClient.get_members(), ['shauna'])

    # TODO: skipping automated roles for now
    

class RoleFormTest(TestCase):

    def setUp(self):
        # Create a user
        self.user = "cap"

        # Create a community
        self.commClient = CommunityClient(actor=self.user)
        self.instance = self.commClient.create_community(name="Team Cap")
        self.commClient.set_target(self.instance)

        # Create request object
        import collections
        User = collections.namedtuple('User', 'username')
        Request = collections.namedtuple('Request', 'user')
        self.request = Request(user=User(username=self.user))

        # Initial data
        self.data = {"0~rolename": "members", "0~members": "cap"}

    def test_add_role_via_role_form(self):

        # Before doing anything, only role is members and only user in members is cap
        self.assertEquals(self.commClient.get_assigned_role_names(), ["members"])
        self.assertEquals(self.commClient.get_members(), ["cap"])

        # Add a new role using the role form
        self.data.update({
            '1~rolename': 'runners',
            '1~members': 'cap falcon'})
        self.role_form = RoleForm(instance=self.instance, request=self.request, data=self.data)
        
        # Form is valid and cleaned data is correct
        result = self.role_form.is_valid()
        self.assertEquals(self.role_form.cleaned_data, 
            {'0~rolename': 'members', 
            '0~members': 'cap', 
            '1~rolename': 'runners', 
            '1~members': 'cap falcon'})

        # After saving, data is updated.
        self.role_form.save()
        self.assertCountEqual(self.commClient.get_assigned_role_names(), ["members", "runners"])
        self.assertEquals(self.commClient.get_members(), ["cap"])

    def test_add_user_to_role_via_role_form(self):

        # Before doing anything, only user in members is cap
        self.assertEquals(self.commClient.get_members(), ["cap"])

        # Add a user using the role form
        self.data.update({
            '0~rolename': 'members', 
            '0~members': 'cap falcon'})
        self.role_form = RoleForm(instance=self.instance, request=self.request, data=self.data)
        
        # Form is valid and cleaned data is correct
        result = self.role_form.is_valid()
        self.assertEquals(self.role_form.cleaned_data, 
            {'0~rolename': 'members', 
            '0~members': 'cap falcon',
            '1~members': '',    # empty row, will be discarded
            '1~rolename': ''})  # empty row, will be discarded

        # After saving, data is updated.
        self.role_form.save()
        self.assertCountEqual(self.commClient.get_members(), ["cap", "falcon"])

    # TODO: can't remove role via form since it may have dependencies, need a different
    # way to test this.
    # def test_remove_role_via_role_form(self):
    
    def test_remove_user_from_role_via_role_form(self):

        # Quick add via form
        self.data.update({
            '1~rolename': 'runners',
            '1~members': 'cap falcon'})
        self.role_form = RoleForm(instance=self.instance, request=self.request, data=self.data)
        self.role_form.is_valid()
        self.role_form.save()
        self.assertCountEqual(self.commClient.get_assigned_role_names(), 
            ["members", "runners"])
        self.assertCountEqual(self.commClient.get_users_given_role(role_name="runners"), 
            ["cap", "falcon"])

        # Remove role via form
        self.data = {"0~rolename": "members", "0~members": "cap", 
            '1~rolename': 'runners', '1~members': 'cap'}
        self.role_form = RoleForm(instance=self.instance, request=self.request, data=self.data)

         # Form is valid and cleaned data is correct
        result = self.role_form.is_valid()
        self.assertEquals(self.role_form.cleaned_data, 
            {'0~rolename': 'members', '0~members': 'cap', 
            '1~rolename': 'runners', '1~members': 'cap',
            '2~rolename': '', '2~members': ''})

        # After saving, data is updated.
        self.role_form.save()
        self.assertCountEqual(self.commClient.get_users_given_role(role_name="runners"), 
            ["cap"])

class PermissionFormTest(TestCase):

    def setUp(self):

        # Create a user
        self.user = "cap"

        # Create a community
        self.commClient = CommunityClient(actor=self.user)
        self.instance = self.commClient.create_community(name="Team Cap")
        self.commClient.set_target(self.instance)

        # Create new roles
        self.commClient.add_assigned_role(role_name="assassins")
        self.commClient.add_people_to_role(role_name="assassins", 
            people_to_add=["whitewolf", "blackwidow"])
        self.commClient.add_assigned_role(role_name="veterans")
        self.commClient.add_people_to_role(role_name="veterans",
            people_to_add=["whitewolf", "cap", "falcon"])

        # Create request object
        import collections
        User = collections.namedtuple('User', 'username')
        Request = collections.namedtuple('Request', 'user')
        self.request = Request(user=User(username=self.user))

        # Initial data
        self.data = {}
        self.prClient = PermissionResourceClient(actor=self.user, target=self.instance)
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
        self.prClient = PermissionResourceClient(actor=self.user, target=self.instance)
        permissions = self.prClient.get_settable_permissions(return_format="list_of_strings")

        # Number of fields on permission form should be permissions x 3
        # FIXME: configurable fields throw this off, hack below is kinda ugly
        self.assertEqual(len(permissions)*3, 
            len([p for p in self.permission_form.fields if "configurablefield" not in p]))

    def test_add_role_to_permission(self):

        # Before changes, no permissions associated with role
        permissions_for_role = self.prClient.get_permissions_associated_with_role(role_name="assassins",
            community=self.instance)
        self.assertEqual(permissions_for_role, [])

        # add role to permission
        self.data["4~roles"] = ["assassins"]
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)

        # Check that it's valid
        self.permission_form.is_valid()
        self.assertEquals(self.permission_form.cleaned_data["4~roles"], ["assassins"])
        
        # Check that it works on save
        self.permission_form.save()
        permissions_for_role = self.prClient.get_permissions_associated_with_role(role_name="assassins",
            community=self.instance)
        self.assertEqual(permissions_for_role[0].change_type,
            'concord.communities.state_changes.AddPeopleToRoleStateChange')

    def test_add_roles_to_permission(self):

        # Before changes, no permissions associated with role
        permissions_for_role = self.prClient.get_permissions_associated_with_role(role_name="assassins",
            community=self.instance)
        self.assertEqual(permissions_for_role, [])

        # add role to permission
        self.data["4~roles"] = ["assassins", "veterans"]  # Use this format since it's a multiple choice field
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)

        # Check that it's valid
        self.permission_form.is_valid()
        self.assertEquals(self.permission_form.cleaned_data["4~roles"], ["assassins", "veterans"])
        
        # Check that it works on save
        self.permission_form.save()
        permissions_for_role = self.prClient.get_permissions_associated_with_role(role_name="assassins",
            community=self.instance)
        self.assertEqual(permissions_for_role[0].change_type,
            'concord.communities.state_changes.AddPeopleToRoleStateChange')
        permissions_for_role = self.prClient.get_permissions_associated_with_role(role_name="veterans",
            community=self.instance)
        self.assertEqual(permissions_for_role[0].change_type,
            'concord.communities.state_changes.AddPeopleToRoleStateChange')

    def test_add_individual_to_permission(self):

        # Before changes, no permissions associated with actor
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="whitewolf")
        self.assertEqual(permissions_for_actor, [])

        # Add actor to permission
        self.data["4~individuals"] = "whitewolf"  # use this format since it's a character field
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)

        # Check that it's valid
        self.permission_form.is_valid()
        self.assertEquals(self.permission_form.cleaned_data["4~individuals"], 
            "whitewolf")        

        # Check form works on save
        self.permission_form.save()
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="whitewolf")
        self.assertEqual(permissions_for_actor[0].change_type,
            'concord.communities.state_changes.AddPeopleToRoleStateChange')

    def test_add_individuals_to_permission(self):

        # Before changes, no permissions associated with actor
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="whitewolf")
        self.assertEqual(permissions_for_actor, [])

        # Add actor to permission
        self.data["4~individuals"] = "whitewolf blackwidow"  # uses this format since it's a charfield
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)

        # Check that it's valid
        self.permission_form.is_valid()
        self.assertEquals(self.permission_form.cleaned_data["4~individuals"], 
            "whitewolf blackwidow")        

        # Check form works on save
        self.permission_form.save()
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="whitewolf")
        self.assertEqual(permissions_for_actor[0].change_type,
            'concord.communities.state_changes.AddPeopleToRoleStateChange')
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="blackwidow")
        self.assertEqual(permissions_for_actor[0].change_type,
            'concord.communities.state_changes.AddPeopleToRoleStateChange')

    def test_add_multiple_to_multiple_permissions(self):

        # Before changes, no permissions associated with role
        permissions_for_role = self.prClient.get_permissions_associated_with_role(role_name="assassins",
            community=self.instance)
        self.assertEqual(permissions_for_role, [])

        # Before changes, no permissions associated with actor
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="whitewolf")
        self.assertEqual(permissions_for_actor, [])

        # Add roles to multiple permissions & actors to multiple permissions
        self.data["4~individuals"] = "whitewolf"
        self.data["5~individuals"] = "whitewolf blackwidow falcon"
        self.data["4~roles"] = ["assassins", "veterans"]
        self.data["2~roles"] = ["assassins", "veterans"]
        self.data["1~roles"] = ["veterans"]

        # Create, validate and save form
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()
        
        # Actor checks
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="whitewolf")
        change_types = [perm.short_change_type() for perm in permissions_for_actor]
        self.assertCountEqual(change_types, ['AddPeopleToRoleStateChange', 'AddRoleStateChange'])
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="falcon")
        change_types = [perm.short_change_type() for perm in permissions_for_actor]
        self.assertCountEqual(change_types, ['AddRoleStateChange'])
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="blackwidow")
        change_types = [perm.short_change_type() for perm in permissions_for_actor]
        self.assertCountEqual(change_types, ['AddRoleStateChange'])

        # Role checks
        permissions_for_role = self.prClient.get_permissions_associated_with_role(
            role_name="assassins", community=self.instance)
        change_types = [perm.short_change_type() for perm in permissions_for_role]
        self.assertCountEqual(change_types, ['AddPeopleToRoleStateChange', 'AddOwnerRoleStateChange']) 
        permissions_for_role = self.prClient.get_permissions_associated_with_role(
            role_name="veterans", community=self.instance)
        change_types = [perm.short_change_type() for perm in permissions_for_role]
        self.assertCountEqual(change_types, ['AddOwnerRoleStateChange', 'AddPeopleToRoleStateChange',
            'AddGovernorStateChange']) 

    def test_remove_role_from_permission(self):

        # add role to permission
        self.data["4~roles"] = ["assassins"]
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()
        permissions_for_role = self.prClient.get_permissions_associated_with_role(role_name="assassins",
            community=self.instance)
        self.assertEqual(permissions_for_role[0].change_type,
            'concord.communities.state_changes.AddPeopleToRoleStateChange')

        # now remove it
        self.data["4~roles"] = []
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()
        permissions_for_role = self.prClient.get_permissions_associated_with_role(role_name="assassins",
            community=self.instance)
        self.assertFalse(permissions_for_role) # Empty list should be falsy

    def test_remove_roles_from_permission(self):

        # add roles to permission
        self.data["4~roles"] = ["assassins", "veterans"]
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()
        permissions_for_role = self.prClient.get_permissions_associated_with_role(role_name="assassins",
            community=self.instance)
        self.assertEqual(permissions_for_role[0].change_type,
            'concord.communities.state_changes.AddPeopleToRoleStateChange')
        permissions_for_role = self.prClient.get_permissions_associated_with_role(role_name="veterans",
            community=self.instance)
        self.assertEqual(permissions_for_role[0].change_type,
            'concord.communities.state_changes.AddPeopleToRoleStateChange')

        # now remove them
        self.data["4~roles"] = []
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()
        permissions_for_role = self.prClient.get_permissions_associated_with_role(role_name="assassins",
            community=self.instance)
        self.assertFalse(permissions_for_role) # Empty list should be falsy
        permissions_for_role = self.prClient.get_permissions_associated_with_role(role_name="veterans",
            community=self.instance)
        self.assertFalse(permissions_for_role) # Empty list should

    def test_remove_individual_from_permission(self):
        
        # Add actor to permission
        self.data["4~individuals"] = "whitewolf"  # use this format since it's a character field
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="whitewolf")
        self.assertEqual(permissions_for_actor[0].change_type,
            'concord.communities.state_changes.AddPeopleToRoleStateChange')

        # Remove actor from permission
        self.data["4~individuals"] = ""  # use this format since it's a character field
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="whitewolf")
        self.assertFalse(permissions_for_actor)  # Empty list should be falsy

    def test_remove_individuals_from_permission(self):
        
        # Add actors to permission
        self.data["4~individuals"] = "blackwidow falcon"  # use this format since it's a character field
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="blackwidow")
        self.assertEqual(permissions_for_actor[0].change_type,
            'concord.communities.state_changes.AddPeopleToRoleStateChange')
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="falcon")
        self.assertEqual(permissions_for_actor[0].change_type,
            'concord.communities.state_changes.AddPeopleToRoleStateChange')

        # Remove actors from permission
        self.data["4~individuals"] = ""  # use this format since it's a character field
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="blackwidow")
        self.assertFalse(permissions_for_actor) # Empty list should be falsy
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="falcon")
        self.assertFalse(permissions_for_actor) # Empty list should be falsy
        
    def test_add_and_remove_multiple_from_multiple_permissions(self):

        # Add roles to multiple permissions & actors to multiple permissions
        self.data["4~individuals"] = "whitewolf"
        self.data["5~individuals"] = "whitewolf blackwidow falcon"
        self.data["4~roles"] = ["assassins", "veterans"]
        self.data["2~roles"] = ["assassins", "veterans"]
        self.data["1~roles"] = ["veterans"]

        # Create, validate and save form
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()
        
        # Actor + role checks, not complete for brevity's sake (should be tested elsewhere)
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="whitewolf")
        change_types = [perm.short_change_type() for perm in permissions_for_actor]
        self.assertCountEqual(change_types, ['AddPeopleToRoleStateChange', 'AddRoleStateChange'])
        permissions_for_role = self.prClient.get_permissions_associated_with_role(
            role_name="veterans", community=self.instance)
        change_types = [perm.short_change_type() for perm in permissions_for_role]
        self.assertCountEqual(change_types, ['AddOwnerRoleStateChange', 'AddPeopleToRoleStateChange',
            'AddGovernorStateChange']) 

        # Okay, now remove some of these
        self.data["4~individuals"] = ""
        self.data["5~individuals"] = "blackwidow falcon"
        self.data["4~roles"] = []
        self.data["2~roles"] = ["assassins"]
        self.data["1~roles"] = ["veterans"]

        # Create, validate and save form
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()

        # Actor checks
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="whitewolf")
        self.assertFalse(permissions_for_actor)  # Empty list should be falsy
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="falcon")
        change_types = [perm.short_change_type() for perm in permissions_for_actor]
        self.assertCountEqual(change_types, ['AddRoleStateChange'])
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="blackwidow")
        change_types = [perm.short_change_type() for perm in permissions_for_actor]
        self.assertCountEqual(change_types, ['AddRoleStateChange'])

        # Role checks
        permissions_for_role = self.prClient.get_permissions_associated_with_role(
            role_name="assassins", community=self.instance)
        change_types = [perm.short_change_type() for perm in permissions_for_role]
        self.assertCountEqual(change_types, ['AddOwnerRoleStateChange']) 
        permissions_for_role = self.prClient.get_permissions_associated_with_role(
            role_name="veterans", community=self.instance)
        change_types = [perm.short_change_type() for perm in permissions_for_role]
        self.assertCountEqual(change_types, ['AddGovernorStateChange']) 

    def test_adding_permissions_actually_works(self):

        # Before any changes are made, Steve as owner can add people to a role,
        # but Natasha cannot.
        self.commClient.add_assigned_role(role_name="avengers")
        self.commClient.add_people_to_role(role_name="avengers", 
            people_to_add=["whitewolf", "falcon"])

        natClient = CommunityClient(actor="blackwidow", target=self.instance)
        natClient.add_people_to_role(role_name="avengers", 
            people_to_add=["agentcarter", "hawkeye"])

        roles = self.commClient.get_assigned_roles()
        self.assertCountEqual(roles["avengers"], ["whitewolf", "falcon"])

        # Then Steve alters, through the permissions form, who can add people to
        # a role to include Natasha.
        self.data["4~individuals"] = "blackwidow"
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()

        # Now, Natasha can add people to roles, but Steve cannot.
        # NOTE: Steve cannot because he was using the owner permission, and now there's a 
        # specific permission.
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="blackwidow")
        change_types = [perm.short_change_type() for perm in permissions_for_actor]
        self.assertCountEqual(change_types, ['AddPeopleToRoleStateChange'])

        natClient.add_people_to_role(role_name="avengers", 
            people_to_add=["hawkeye"])
        self.commClient.add_people_to_role(role_name="avengers", 
            people_to_add=["scarletwitch"])

        roles = self.commClient.get_assigned_roles()
        self.assertCountEqual(roles["avengers"], ["whitewolf", "falcon", "hawkeye"])


class MetaPermissionsFormTest(TestCase):

    def setUp(self):
        
        # Create a user
        self.user = "cap"

        # Create a community
        self.commClient = CommunityClient(actor=self.user)
        self.instance = self.commClient.create_community(name="Team Cap")
        self.commClient.set_target(self.instance)

        # Make separate clients for Sam and Nat.
        self.samClient = CommunityClient(actor="falcon", target=self.instance)
        self.buckyClient = CommunityClient(actor="whitewolf", target=self.instance)

        # Create request objects
        import collections
        User = collections.namedtuple('User', 'username')
        Request = collections.namedtuple('Request', 'user')
        self.request = Request(user=User(username=self.user))
        self.samRequest = Request(user=User(username="falcon"))  # Not sure it's necessary
        self.buckyRequest = Request(user=User(username="whitewolf"))  # Not sure it's necessary

        # Add a role to community and assign a member
        self.commClient.add_assigned_role(role_name="avengers")
        self.commClient.add_people_to_role(role_name="avengers", people_to_add=["ironman"])

        # Initial data for permissions level
        self.permissions_data = {}
        self.prClient = PermissionResourceClient(actor=self.user, target=self.instance)
        permissions = self.prClient.get_settable_permissions(return_format="list_of_strings")
        for count, permission in enumerate(permissions):
            self.permissions_data[str(count) + "~" + "name"] = permission
            self.permissions_data[str(count) + "~" + "roles"] = []
            self.permissions_data[str(count) + "~" + "individuals"] = []

        # Give Natasha permission to add people to roles
        self.permissions_data["4~individuals"] = "blackwidow"
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.permissions_data)
        self.permission_form.is_valid()
        self.permission_form.save()

        # Initial data for metapermissions level
        self.target_permission = self.prClient.get_specific_permissions(
            change_type="concord.communities.state_changes.AddPeopleToRoleStateChange")[0]
        self.metapermissions_data = {}
        
        self.metaClient = PermissionResourceClient(actor=self.user, target=self.target_permission)
        permissions = self.metaClient.get_settable_permissions(return_format="list_of_strings")
        for count, permission in enumerate(permissions):
            self.metapermissions_data[str(count) + "~" + "name"] = permission
            self.metapermissions_data[str(count) + "~" + "roles"] = []
            self.metapermissions_data[str(count) + "~" + "individuals"] = []        

    def test_adding_metapermission_adds_access_to_permission(self):
        # Currently, only Tony is in the Avengers role, only Natasha has permission to 
        # add people to roles, and only Steve has permission to give permission to add
        # people to roles.

        # Steve wants to give Sam the permission to give permission to add people to
        # roles.  That is, Steve desires that Sam should have the metapermission to alter
        # the permission AddPeopleToRoles.
        
        # Before Steve does anything, Sam tries to give Bucky permission to 
        # add people to roles.  It fails, and we can see that Sam lacks the relevant
        # metapermission and Bucky the relevant permission.

        self.permissions_data["4~individuals"] = "blackwidow whitewolf"
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.samRequest, data=self.permissions_data)
        self.permission_form.is_valid()
        self.permission_form.save()

        self.buckyClient.add_people_to_role(role_name="avengers", people_to_add=["scarletwitch"])
        roles = self.commClient.get_assigned_roles()
        self.assertCountEqual(roles["avengers"], ["ironman"])

        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="whitewolf")
        self.assertFalse(permissions_for_actor)

        permissions_for_actor = self.metaClient.get_permissions_associated_with_actor(
            actor="falcon")
        self.assertFalse(permissions_for_actor)

        # Then Steve alters, through the metapermissions form, who can add alter the
        # AddPeopleToRole permission.  He alters the metapermission on the AddPeopleToRole 
        # permission, adding the individual Sam.

        self.metapermissions_data["0~individuals"] = "falcon"
        self.metapermission_form = MetaPermissionForm(instance=self.target_permission, 
            request=self.request, data=self.metapermissions_data)
        self.metapermission_form.is_valid()
        self.metapermission_form.save()

        permissions_for_actor = self.metaClient.get_permissions_associated_with_actor(
            actor="falcon")
        self.assertEqual(permissions_for_actor[0].short_change_type(), 'AddActorToPermissionStateChange')
        self.assertEqual(permissions_for_actor[0].get_permitted_object(), self.target_permission)

        # Now Sam can give Bucky permission to add people to roles.

        self.permissions_data["4~individuals"] = "blackwidow whitewolf"
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.samRequest, data=self.permissions_data)
        self.permission_form.is_valid()
        self.permission_form.save()

        # Bucky can assign people to roles now.

        self.buckyClient.add_people_to_role(role_name="avengers", people_to_add=["scarletwitch"])
        roles = self.commClient.get_assigned_roles()
        self.assertCountEqual(roles["avengers"], ["ironman", "scarletwitch"])

        # Finally, Bucky and Natasha both have permission to add people to roles, while
        # Sam and Steve do not.

        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="whitewolf")
        change_types = [perm.short_change_type() for perm in permissions_for_actor]
        self.assertCountEqual(change_types, ['AddPeopleToRoleStateChange'])
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="blackwidow")
        change_types = [perm.short_change_type() for perm in permissions_for_actor]
        self.assertCountEqual(change_types, ['AddPeopleToRoleStateChange'])
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="cap")
        change_types = [perm.short_change_type() for perm in permissions_for_actor]
        self.assertCountEqual(change_types, [])
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="falcon")
        change_types = [perm.short_change_type() for perm in permissions_for_actor]
        self.assertCountEqual(change_types, [])

    def test_removing_metapermission_removes_access_to_permission(self):
        # Steve gives Sam ability to add people to permission.
        self.metapermissions_data["0~individuals"] = "falcon"
        self.metapermission_form = MetaPermissionForm(instance=self.target_permission, 
            request=self.request, data=self.metapermissions_data)
        self.metapermission_form.is_valid()
        self.metapermission_form.save()

        # Sam can do so.  When he gives Bucky permission to add people to roles, he can.
        self.permissions_data["4~individuals"] = "blackwidow whitewolf"
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.samRequest, data=self.permissions_data)
        self.permission_form.is_valid()
        self.permission_form.save()
        self.buckyClient.add_people_to_role(role_name="avengers", people_to_add=["scarletwitch"])
        roles = self.commClient.get_assigned_roles()
        self.assertCountEqual(roles["avengers"], ["ironman", "scarletwitch"])

        # Now Steve removes that ability.
        self.metapermissions_data["0~individuals"] = ""
        self.metapermission_form = MetaPermissionForm(instance=self.target_permission, 
            request=self.request, data=self.metapermissions_data)
        self.metapermission_form.is_valid()
        self.metapermission_form.save()

        # Sam no longer has the metapermission and can no longer add people to permission.
        permissions_for_actor = self.metaClient.get_permissions_associated_with_actor(
            actor="falcon")
        self.assertFalse(permissions_for_actor)

        self.permissions_data["4~individuals"] = "blackwidow whitewolf agentcarter"
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.samRequest, data=self.permissions_data)
        self.permission_form.is_valid()
        self.permission_form.save()

        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="agentcarter")
        change_types = [perm.short_change_type() for perm in permissions_for_actor]
        self.assertCountEqual(change_types, [])

    def test_adding_metapermission_to_nonexistent_permission(self):

        # No one currently has the specific permission "remove people from role".
        remove_permission = self.prClient.get_specific_permissions(change_type=
            'concord.communities.state_changes.RemovePeopleFromRoleStateChange')
        self.assertFalse(remove_permission)

        # Steve tries to give Sam the ability to add or remove people from the permission
        # 'remove people from role'.

        # First, we get a mock permission to pass to the metapermission form.
        ct = ContentType.objects.get_for_model(self.instance)
        target_permission = self.prClient.get_permission_or_return_mock(
            permitted_object_pk=self.instance.pk,
            permitted_object_ct=str(ct.pk),
            permission_change_type='concord.communities.state_changes.RemovePeopleFromRoleStateChange')
        self.assertEqual(target_permission.__class__.__name__, "MockMetaPermission")

        # Then we actually update metapermissions via the form.
        self.metapermissions_data["0~individuals"] = "falcon"
        self.metapermission_form = MetaPermissionForm(instance=target_permission, 
            request=self.request, data=self.metapermissions_data)
        self.metapermission_form.is_valid()
        self.metapermission_form.save()

        # Now that Steve has done that, the specific permission exists.  
        remove_permission = self.prClient.get_specific_permissions(change_type=
            'concord.communities.state_changes.RemovePeopleFromRoleStateChange')
        ah = PermissionsItem.objects.filter(change_type='concord.communities.state_changes.RemovePeopleFromRoleStateChange')
        self.assertEqual(len(remove_permission), 1)         

        # The metapermission Steve created for Sam also exists.
        self.metaClient = PermissionResourceClient(actor=self.user, target=remove_permission[0])
        perms = self.metaClient.get_permissions_on_object(object=remove_permission[0])
        self.assertEqual(len(perms), 1)
        self.assertEqual(perms[0].short_change_type(), "AddActorToPermissionStateChange")

        # Sam can add Natasha to the permission "remove people from role".
        self.permissions_data["11~individuals"] = "blackwidow"
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.samRequest, data=self.permissions_data)
        self.permission_form.is_valid()
        self.permission_form.save()

        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="blackwidow")
        change_types = [perm.short_change_type() for perm in permissions_for_actor]
        self.assertCountEqual(change_types, ["RemovePeopleFromRoleStateChange", 
            "AddPeopleToRoleStateChange"])


class ResourcePermissionsFormTest(TestCase):

    def setUp(self):

        # Create a user
        self.user = "blackpanther"

        # Create a community
        self.commClient = CommunityClient(actor=self.user)
        self.instance = self.commClient.create_community(name="Wakanda")
        self.commClient.set_target(self.instance)

        # Create request objects
        import collections
        User = collections.namedtuple('User', 'username')
        Request = collections.namedtuple('Request', 'user')
        self.request = Request(user=User(username=self.user))
        self.shuriRequest = Request(user=User(username="shuri"))  # Not sure it's necessary
        self.okoyeRequest = Request(user=User(username="okoye"))  # Not sure it's necessary

        # Add roles to community and assign members
        self.commClient.add_people_to_role(role_name="members", 
            people_to_add=["shuri", "nakia", "okoye", "ramonda"])
        self.commClient.add_assigned_role(role_name="royalfamily")
        self.commClient.add_people_to_role(role_name="royalfamily", 
            people_to_add=["shuri", "ramonda"])

        # Create a forum owned by the community
        self.resourceClient = ResourceClient(actor="blackpanther")
        self.resource = self.resourceClient.create_resource(name="Royal Family Forum")
        self.resourceClient.set_target(target=self.resource)
        self.resourceClient.change_owner_of_target(new_owner="Wakanda",
            new_owner_type="com")

        # Make separate clients for Shuri and Okoye.
        self.shuriClient = ResourceClient(actor="shuri", target=self.resource)
        self.okoyeClient = ResourceClient(actor="okoye", target=self.resource)

        # Initial form data
        self.data = {
            '0~name': 'concord.resources.state_changes.AddItemResourceStateChange',
            '0~individuals': None, '0~roles': None,
            '1~name': 'concord.resources.state_changes.ChangeResourceNameStateChange',
            '1~individuals': None, '1~roles': None,
            '2~name': 'concord.resources.state_changes.RemoveItemResourceStateChange',
            '2~individuals': None, '2~roles': None}

    def test_add_and_remove_actor_permission_to_resource_via_form(self):

        # Shuri tries to change the name of the forum and fails
        action, result = self.shuriClient.change_name(new_name="Shuri Rulez")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.name, "Royal Family Forum")

        # T'Challa gives her permission to change the name via the individual 
        # actor field on the permission form.
        self.data['1~individuals'] = "shuri"
        form = PermissionForm(instance=self.resource, request=self.request, 
            data=self.data)
        form.is_valid()
        self.assertEquals(form.cleaned_data['1~individuals'], "shuri")
        form.save()

        # Now Shuri succeeds.
        action, result = self.shuriClient.change_name(new_name="Shuri Rulez")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(self.resource.name, "Shuri Rulez")

        # T'Challa takes it away again.
        self.data['1~individuals'] = ""
        form = PermissionForm(instance=self.resource, request=self.request, 
            data=self.data)
        form.is_valid()
        self.assertEquals(form.cleaned_data['1~individuals'], "")
        form.save()       

        # Shuri can no longer change the name.
        action, result = self.shuriClient.change_name(new_name="Shuri for Queen")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.name, "Shuri Rulez")

    def test_add_and_remove_role_permission_to_resource_via_form(self):

        # Shuri tries to change the name of the forum and fails
        action, result = self.shuriClient.change_name(new_name="Shuri Rulez")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.name, "Royal Family Forum")

        # T'Challa gives her permission to change the name via the royal family
        # role field on the permission form.
        self.data['1~roles'] = ["royalfamily"]
        form = PermissionForm(instance=self.resource, request=self.request, 
            data=self.data)
        form.is_valid()
        self.assertEquals(form.cleaned_data['1~roles'], ["royalfamily"])
        form.save()

        # Now Shuri succeeds, but Okoye does not.
        action, result = self.okoyeClient.change_name(new_name="Wakandan Royal Family Forum")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.name, "Royal Family Forum")        
        action, result = self.shuriClient.change_name(new_name="Shuri Rulez")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "implemented")
        self.assertEquals(self.resource.name, "Shuri Rulez")

        # T'Challa takes it away again.
        self.data['1~roles'] = []
        form = PermissionForm(instance=self.resource, request=self.request, 
            data=self.data)
        form.is_valid()
        self.assertEquals(form.cleaned_data['1~roles'], [])
        form.save()

        # Shuri can no longer change the name.
        action, result = self.shuriClient.change_name(new_name="Shuri for Queen")
        self.assertEquals(Action.objects.get(pk=action.pk).status, "rejected")
        self.assertEquals(self.resource.name, "Shuri Rulez")


class ResolutionFieldTest(TestCase):

    def setUp(self):

        # Create users
        self.user = "cap"  # Main user
        self.nonmember_user = "ironman"
        self.member_user = "whitewolf"
        self.governing_user = "falcon"
        self.roletest_user = "blackwidow"

        # Create a community
        self.commClient = CommunityClient(actor=self.user)
        self.instance = self.commClient.create_community(name="Team Cap")
        self.commClient.set_target(self.instance)

        # Make separate clients for Tony, Bucky, Sam.
        self.samClient = CommunityClient(actor="falcon", target=self.instance)
        self.buckyClient = CommunityClient(actor="whitewolf", target=self.instance)
        self.tonyClient = CommunityClient(actor="ironman", target=self.instance)

        # Create request objects
        import collections
        User = collections.namedtuple('User', 'username')
        Request = collections.namedtuple('Request', 'user')
        self.request = Request(user=User(username=self.user))
        self.samRequest = Request(user=User(username="falcon"))  # Not sure it's necessary
        self.buckyRequest = Request(user=User(username="whitewolf"))  # Not sure it's necessary
        self.tonyRequest = Request(user=User(username="ironman"))

        # Add members to community
        self.commClient.add_member(name="blackwidow")
        self.commClient.add_member(name="falcon")
        self.commClient.add_member(name="whitewolf")

        # Add a role to community and assign relevant members
        self.commClient.add_assigned_role(role_name="assassins")
        self.commClient.add_people_to_role(role_name="assassins", people_to_add=["whitewolf", "blackwidow"])

        # Get role pairs for use in setting permissions
        self.member_role_pair = str(self.instance.pk) + "_members"
        self.assassin_role_pair = str(self.instance.pk) + "_assassins"

        # Create permissions client
        self.prc = PermissionResourceClient(actor=self.user, target=self.instance)

    def test_resolution_field_correct_for_approved_action(self):

        # Add permission so any member can change the name of the group
        self.prc.add_permission(permission_role_pairs=[self.member_role_pair],
            permission_type="concord.communities.state_changes.ChangeNameStateChange")

        # User changes name
        self.commClient.set_actor(actor=self.member_user)
        action, result = self.commClient.change_name(new_name="Miscellaneous Badasses")
        self.assertEquals(action.status, "implemented")

        # Inspect action's resolution field
        self.assertTrue(action.resolution.is_resolved)
        self.assertTrue(action.resolution.is_approved)
        self.assertEquals(action.resolution.resolved_through, "specific")
        self.assertFalse(action.resolution.condition)

    def test_resolution_field_correct_for_rejected_action(self):

        # Add permission so any member can change the name of the group
        self.prc.add_permission(permission_role_pairs=[self.member_role_pair],
            permission_type="concord.communities.state_changes.ChangeNameStateChange")

        # Non-member user changes name
        self.commClient.set_actor(actor=self.nonmember_user)
        action, result = self.commClient.change_name(new_name="Miscellaneous Badasses")
        self.assertEquals(action.status, "rejected")

        # Inspect action's resolution field
        self.assertTrue(action.resolution.is_resolved)
        self.assertFalse(action.resolution.is_approved)
        self.assertEquals(action.resolution.resolved_through, "specific")
        self.assertFalse(action.resolution.condition)

    def test_resolution_field_resolved_through(self):
        
        # Steve can make Sam a governor because he has a foundational permission
        action, result = self.commClient.add_governor(governor_name="falcon")
        self.assertEquals(action.status, "implemented")
        self.assertTrue(action.resolution.is_resolved)
        self.assertTrue(action.resolution.is_approved)
        self.assertEquals(action.resolution.resolved_through, "foundational")

        # Sam can change the name of the group because he has a governing permission.        
        action, result = self.samClient.change_name(new_name="The Falcon and His Sidekicks")
        self.assertEquals(action.status, "implemented")
        self.assertTrue(action.resolution.is_resolved)
        self.assertTrue(action.resolution.is_approved)
        self.assertEquals(action.resolution.resolved_through, "governing")

        # Bucky can change the name of the group because he has a specific permission.
        self.prc.add_permission(permission_actors=["whitewolf"],
            permission_type="concord.communities.state_changes.ChangeNameStateChange")
        action, result = self.buckyClient.change_name(new_name="The Falcon and His Sidekicks")
        self.assertEquals(action.status, "implemented")
        self.assertTrue(action.resolution.is_resolved)
        self.assertTrue(action.resolution.is_approved)
        self.assertEquals(action.resolution.resolved_through, "specific")

    def test_resolution_field_for_role_for_specific_permission(self):

        # Add permission so any member can change the name of the group
        self.prc.add_permission(permission_role_pairs=[self.member_role_pair],
            permission_type="concord.communities.state_changes.ChangeNameStateChange")

        # When they change the name, the resolution role field shows the role
        action, result = self.buckyClient.change_name(new_name="Reckless Idiots")
        self.assertTrue(action.resolution.is_approved)
        self.assertEquals(action.resolution.resolved_through, "specific")
        self.assertEquals(action.resolution.role, "1_members")

    def test_resolution_field_for_role_for_governing_permission(self):

        # Steve makes a governing role
        action, result = self.commClient.add_governor_role(governor_role="assassins")
        action, result = self.buckyClient.change_name(new_name="Reckless Idiots")
        self.assertEquals(action.resolution.resolved_through, "governing")
        self.assertEquals(action.resolution.role, "1_assassins")

    # TODO: need to also test role in foundational pipeline

    def test_resolution_field_for_individual(self):

        # Add permission so a specific person can change the name of the group
        self.prc.add_permission(permission_actors=["whitewolf"],
            permission_type="concord.communities.state_changes.ChangeNameStateChange")

        # When they change the name, the resolution role field shows no role
        action, result = self.buckyClient.change_name(new_name="Reckless Idiots")
        self.assertTrue(action.resolution.is_approved)
        self.assertEquals(action.resolution.resolved_through, "specific")
        self.assertFalse(action.resolution.role)

    def test_resolution_field_captures_conditional_info(self):

        # Steve sets a permission on the community that any 'member' can change the name.
        action, permission = self.prc.add_permission(
            permission_role_pairs=[self.member_role_pair],
            permission_type="concord.communities.state_changes.ChangeNameStateChange")

        # But then he adds a condition that someone needs to approve a name change 
        # before it can go through. 
        conditionalClient = PermissionConditionalClient(actor=self.user, 
            target=permission)
        conditionalClient.addCondition(condition_type="approvalcondition")

        # (Since no specific permission is set on the condition, "approving" it 
        # requirest foundational or governing authority to change.  So only Steve 
        # can approve.)

        # Tony tries to change the name and fails because he is not a member.  The
        # condition never gets triggered.
        action, result = self.tonyClient.change_name(new_name="Team Iron Man")
        self.assertEquals(action.status, "rejected")
        self.assertTrue(action.resolution.is_resolved)
        self.assertFalse(action.resolution.is_approved)
        self.assertEquals(action.resolution.resolved_through, "specific")
        self.assertFalse(action.resolution.condition)

        # Bucky tries to change the name and has to wait for approval.
        bucky_action, result = self.buckyClient.change_name(new_name="Friends")
        self.assertEquals(bucky_action.status, "waiting")
        self.assertFalse(bucky_action.resolution.is_resolved)
        self.assertFalse(bucky_action.resolution.is_approved)
        self.assertFalse(bucky_action.resolution.condition)

        # Steve approves Bucky's name change.
        condition_item = conditionalClient.get_condition_item_given_action(
            action_pk=bucky_action.pk)
        acc = ApprovalConditionClient(target=condition_item, actor=self.user)
        action, result = acc.approve()
        self.assertEquals(action.status, "implemented")

        # Bucky's action is implemented
        bucky_action = Action.objects.get(pk=bucky_action.pk)  # Refresh action
        self.assertEquals(bucky_action.status, "implemented")
        self.assertTrue(bucky_action.resolution.is_resolved)
        self.assertTrue(bucky_action.resolution.is_approved)
        self.assertEquals(bucky_action.resolution.condition, "approvalcondition")
        self.instance = self.commClient.get_community(community_pk=str(self.instance.pk))
        self.assertEquals(self.instance.name, "Friends")

        # Bucky tries to change the name again.  This time Steve rejects it. 
        bucky_action, result = self.buckyClient.change_name(new_name="Reckless Idiots")
        condition_item = conditionalClient.get_condition_item_given_action(
            action_pk=bucky_action.pk)
        acc = ApprovalConditionClient(target=condition_item, actor=self.user)
        action, result = acc.reject()
        bucky_action = Action.objects.get(pk=bucky_action.pk)  # Refresh action again
        self.assertEquals(bucky_action.status, "rejected")
        self.assertEquals(self.instance.name, "Friends")
        self.assertTrue(bucky_action.resolution.is_resolved)
        self.assertFalse(bucky_action.resolution.is_approved)
        self.assertEquals(bucky_action.resolution.condition, "approvalcondition")


class ConfigurablePermissionTest(TestCase):

    def setUp(self):

        # Create a user
        self.user = "blackpanther"

        # Create a community & client
        self.commClient = CommunityClient(actor=self.user)
        self.instance = self.commClient.create_community(name="Wakanda")
        self.commClient.set_target(self.instance)

        # Add roles to community and assign members
        self.commClient.add_people_to_role(role_name="members", 
            people_to_add=["shuri", "ayo", "okoye", "ramonda"])
        self.commClient.add_assigned_role(role_name="royalfamily")
        self.commClient.add_assigned_role(role_name="doramilaje")

        # Make separate clients for other users.
        self.okoyeClient = CommunityClient(actor="okoye", target=self.instance)
        self.shuriClient = CommunityClient(actor="shuri", target=self.instance)
        self.nakiaClient = CommunityClient(actor="nakia", target=self.instance)

        # Create permission client for T'Challa
        self.permClient = PermissionResourceClient(actor=self.user, target=self.instance)

        # Create request objects
        import collections
        User = collections.namedtuple('User', 'username')
        Request = collections.namedtuple('Request', 'user')
        self.request = Request(user=User(username=self.user))

    def test_configurable_permission(self):

        # T'Challa configures a permission so that Okoye can only add 
        # people to the dora milaje role and not the royal family role.
        self.permClient.add_permission(
            permission_type="concord.communities.state_changes.AddPeopleToRoleStateChange",
            permission_actors=["okoye"],
            permission_configuration={"role_name": "doramilaje"})

        # Okoye can add Ayo to the dora milaje role
        action, result = self.okoyeClient.add_people_to_role(role_name="doramilaje", people_to_add=["ayo"])
        roles = self.commClient.get_assigned_roles()
        self.assertEquals(roles["doramilaje"], ["ayo"])
        
        # Okoye cannot add Ayo to the royal family role
        self.okoyeClient.add_people_to_role(role_name="royalfamily", people_to_add=["ayo"])
        roles = self.commClient.get_assigned_roles()
        self.assertEquals(roles["royalfamily"], [])

    def test_configurable_permission_via_form(self):

        # Create initial data to mess with
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request)
        self.data = {}
        for field_name, field in self.permission_form.fields.items():
            self.data[field_name] = field.initial

        # Update form to add configurable permission
        self.data["4~individuals"] = "okoye"
        self.data["4~configurablefield~role_name"] = 'doramilaje'

        # Now re-create and save form
        self.permission_form = PermissionForm(instance=self.instance, request=self.request,
            data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()

        # Okoye can add Ayo to the dora milaje role
        action, result = self.okoyeClient.add_people_to_role(role_name="doramilaje", people_to_add=["ayo"])
        roles = self.commClient.get_assigned_roles()
        self.assertEquals(roles["doramilaje"], ["ayo"])
        
        # Okoye cannot add Ayo to the royal family role
        self.okoyeClient.add_people_to_role(role_name="royalfamily", people_to_add=["ayo"])
        roles = self.commClient.get_assigned_roles()
        self.assertEquals(roles["royalfamily"], [])

        # Update permission to allow the reverse
        self.data["4~configurablefield~role_name"] = 'royalfamily'
        self.permission_form = PermissionForm(instance=self.instance, request=self.request,
            data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()

        # Okoye cannot add Aneka to the dora milaje role
        action, result = self.okoyeClient.add_people_to_role(role_name="doramilaje", people_to_add=["aneka"])
        roles = self.commClient.get_assigned_roles()
        self.assertEquals(roles["doramilaje"], ["ayo"])
        
        # But she can add Shuri to the royal family role
        self.okoyeClient.add_people_to_role(role_name="royalfamily", people_to_add=["shuri"])
        roles = self.commClient.get_assigned_roles()
        self.assertEquals(roles["royalfamily"], ["shuri"])

    def test_configurable_metapermission(self):
        # NOTE: This broke my brain a little.  See platform to dos doc for a brief disquisition on 
        # the four types of potential configurable metapermissions.

        # T'Challa creates a role called 'admins' in community Wakanda and adds Nakia to the role. He
        # adds Shuri to the royalfamily role.
        self.commClient.add_assigned_role(role_name="admins")
        self.commClient.add_people_to_role(role_name="admins", people_to_add=["nakia"])
        self.commClient.add_people_to_role(role_name="royalfamily", people_to_add=["shuri"])

        # T'Challa creates a configured permission on community Wakanda where people with role
        # 'admins', as well as the role 'royalfamily', can add people to the role 'doramilaje'.
        action, permission = self.permClient.add_permission(
            permission_type="concord.communities.state_changes.AddPeopleToRoleStateChange",
            permission_role_pairs=["1_admins", "1_royalfamily"],
            permission_configuration={"role_name": "doramilaje"})
        roles = permission.get_roles()
        self.assertCountEqual(roles, ["1_admins", "1_royalfamily"]) 

        # We test that Shuri, in the role royalfamily, can add Ayo to doramilaje, and that 
        # Nakia, in the role admins, can add Aneka to the doramilaje.
        self.shuriClient.add_people_to_role(role_name="doramilaje", people_to_add=["ayo"])
        self.nakiaClient.add_people_to_role(role_name="doramilaje", people_to_add=["aneka"])
        roles = self.commClient.get_assigned_roles()
        self.assertCountEqual(roles["doramilaje"], ["ayo", "aneka"])

        # T'Challa then creates a configured metapermission on that configured permission that allows
        # Okoye to remove the role 'admins' but not the role 'royalfamily'.
        self.metaPermClient = PermissionResourceClient(actor=self.user, target=permission)
        self.metaPermClient.add_permission(
            permission_type="concord.permission_resources.state_changes.RemoveRoleFromPermissionStateChange",
            permission_actors=["okoye"],
            permission_configuration={"role_name": "admins"})

        # Okoye tries to remove both.  She is successful in removing admins but not royalfamily.
        self.okoyePermClient = PermissionResourceClient(actor="okoye", target=permission)
        self.okoyePermClient.remove_role_from_permission(role_name="admins", 
            community_pk=self.instance.pk, permission_pk=permission.pk)
        self.okoyePermClient.remove_role_from_permission(role_name="royalfamily", 
            community_pk=self.instance.pk, permission_pk=permission.pk)
        permission = PermissionsItem.objects.get(pk=permission.pk)  # Refresh
        roles = permission.get_roles()
        self.assertCountEqual(roles, ["1_royalfamily"])        

        # We check again: Shuri, in the royalfamily role, can add X to the doramilaje, but 
        # Nakia, as an admin, can no longer add anyone to the dora milaje.
        self.shuriClient.add_people_to_role(role_name="doramilaje", people_to_add=["xoliswa"])
        self.nakiaClient.add_people_to_role(role_name="doramilaje", people_to_add=["folami"])
        roles = self.commClient.get_assigned_roles()
        self.assertCountEqual(roles["doramilaje"], ["ayo", "aneka", "xoliswa"])

    def test_configurable_metapermission_via_form(self):
        '''Duplicates above test but does the configurable metapermission part via form.'''

        # Setup (copied from above)
        self.commClient.add_assigned_role(role_name="admins")
        self.commClient.add_people_to_role(role_name="admins", people_to_add=["nakia"])
        self.commClient.add_people_to_role(role_name="royalfamily", people_to_add=["shuri"])
        action, target_permission = self.permClient.add_permission(
            permission_type="concord.communities.state_changes.AddPeopleToRoleStateChange",
            permission_role_pairs=["1_admins", "1_royalfamily"],
            permission_configuration={"role_name": "doramilaje"})
        self.shuriClient.add_people_to_role(role_name="doramilaje", people_to_add=["ayo"])
        self.nakiaClient.add_people_to_role(role_name="doramilaje", people_to_add=["aneka"])

        # T'Challa creates configured metapermission on permission that allows
        # Okoye to remove the role 'admins' but not the role 'royalfamily'
        self.metaPermClient = PermissionResourceClient(actor=self.user, target=target_permission)
        self.metapermissions_data = {}
        permissions = self.metaPermClient.get_settable_permissions(return_format="permission_object")
        for count, permission in enumerate(permissions):
            self.metapermissions_data[str(count) + "~" + "name"] = permission.get_change_type()
            self.metapermissions_data[str(count) + "~" + "roles"] = []
            self.metapermissions_data[str(count) + "~" + "individuals"] = []
            for field in permission.get_configurable_fields():
                self.metapermissions_data['%s~configurablefield~%s' % (count, field)] = ""
        self.metapermissions_data["4~configurablefield~role_name"] = "admins"
        self.metapermissions_data["4~individuals"] = "okoye"

        self.metapermission_form = MetaPermissionForm(request=self.request, instance=target_permission,
            data=self.metapermissions_data)
        self.metapermission_form.is_valid()
        self.metapermission_form.save()

        # Test that it worked (again, copied from above)
        self.okoyePermClient = PermissionResourceClient(actor="okoye", target=target_permission)
        action, result = self.okoyePermClient.remove_role_from_permission(role_name="admins", 
            community_pk=self.instance.pk, permission_pk=target_permission.pk)
        action, result = self.okoyePermClient.remove_role_from_permission(role_name="royalfamily", 
            community_pk=self.instance.pk, permission_pk=target_permission.pk)        
        self.shuriClient.add_people_to_role(role_name="doramilaje", people_to_add=["xoliswa"])
        self.nakiaClient.add_people_to_role(role_name="doramilaje", people_to_add=["folami"])
        roles = self.commClient.get_assigned_roles()
        self.assertCountEqual(roles["doramilaje"], ["ayo", "aneka", "xoliswa"])