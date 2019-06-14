import json
from decimal import Decimal
import time

from django.test import TestCase

from concord.resources.client import ResourceClient
from concord.permission_resources.client import PermissionResourceClient
from concord.conditionals.client import (ApprovalConditionClient, VoteConditionClient, 
    PermissionConditionalClient, CommunityConditionalClient)
from concord.communities.client import CommunityClient

from concord.communities.forms import RoleForm
from concord.permission_resources.forms import AccessForm, PermissionForm, MetaPermissionForm
from concord.actions.models import Action  # For testing action status later, do we want a client?


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
        action_pk, item = self.rc.add_item(item_name="Aha")
        self.assertEquals(item.get_unique_id(), "resources_item_1")

    def test_remove_item_from_resource(self):
        """
        Test removal of item from resource.
        """
        resource = self.rc.create_resource(name="Aha")
        self.rc.set_target(target=resource)
        action_pk, item = self.rc.add_item(item_name="Aha")
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
        action_pk, permission = self.prc.add_permission(permission_type="permissions_resource_additem",
            permission_actors=["shauna"])
        items = self.prc.get_permissions_on_object(object=resource)
        self.assertEquals(items.first().get_name(), 'Permission 1 (for permissions_resource_additem on Resource object (1))')

    def test_remove_permission_from_resource(self):
        """
        Test removal of permission from resource.
        """
        # FIXME: these permissions are invalid, replace with real permissions
        resource = self.rc.create_resource(name="Aha")
        self.prc.set_target(target=resource)
        action_pk, permission = self.prc.add_permission(permission_type="permissions_resource_additem",
            permission_actors=["shauna"])
        items = self.prc.get_permissions_on_object(object=resource)
        self.assertEquals(items.first().get_name(), 'Permission 1 (for permissions_resource_additem on Resource object (1))')
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
        action_pk, permission = self.prc.add_permission(
            permission_type="concord.resources.state_changes.AddItemResourceStateChange",
            permission_actors=["buffy"])
        items = self.prc.get_permissions_on_object(object=resource)
        self.assertEquals(items.first().get_name(), 
            'Permission 1 (for concord.resources.state_changes.AddItemResourceStateChange on Resource object (1))')

        # Now let's have Buffy do a thing on the resource
        brc = ResourceClient(actor="buffy", target=resource)
        action_pk, item = brc.add_item(item_name="Test New")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")
        self.assertEquals(item.name, "Test New")

    def test_recursive_permission(self):
        """
        Tests setting permissions on permission.
        """

        # Shauna creates a resource and adds a permission to the resource.
        resource = self.rc.create_resource(name="Aha")
        self.prc.set_target(target=resource)
        action_pk, permission = self.prc.add_permission(
            permission_type="concord.resources.state_changes.AddItemResourceStateChange",
            permission_actors=["willow"])

        # Buffy can't add an item to this resource because she's not the owner nor specified in
        # the permission.        
        brc = ResourceClient(actor="buffy", target=resource)
        action_pk, item = brc.add_item(item_name="Buffy's item")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "rejected")

        # Shauna adds a permission on the permission which Buffy does have.
        self.prc.set_target(target=permission)
        action_pk, rec_permission = self.prc.add_permission(
            permission_type="concord.permission_resources.state_changes.AddPermissionStateChange",
            permission_actors=["buffy"])
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")

        # Buffy still cannot make the change because she does not have the permission.
        brc = ResourceClient(actor="buffy", target=resource)
        action_pk, item = brc.add_item(item_name="Buffy's item")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "rejected")
        
        # BUT Buffy CAN make the second-level change.
        bprc = PermissionResourceClient(actor="buffy", target=permission)
        action_pk, permission = bprc.add_permission(permission_type="concord.permission_resources.state_changes.AddPermissionStateChange",
            permission_actors=["willow"])        
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")


class ConditionalsTest(TestCase):

    def setUp(self):
        self.cc = PermissionConditionalClient(actor="shauna")
        self.rc = ResourceClient(actor="shauna")
        self.prc = PermissionResourceClient(actor="shauna")
        self.target = self.rc.create_resource(name="Aha")
        self.action = Action.objects.create(actor="elena", target=self.target)

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
        action_pk, permission = self.prc.add_permission(permission_type="concord.resources.state_changes.AddItemResourceStateChange",
            permission_actors=["buffy"])
        
        # But she places a condition on the permission that Buffy has to get
        # approval (without specifying permissions, so it uses the default.
        self.cc.set_target(target=permission)
        self.cc.addCondition(condition_type="approvalcondition")

        # Now when Xander tries to add an item he is flat out rejected
        self.rc.set_actor(actor="xander")
        self.rc.set_target(target=resource)
        action_pk, item = self.rc.add_item(item_name="Xander's item")
        self.assertEquals(resource.get_items(), [])
        self.assertEquals(Action.objects.get(pk=action_pk).status, "rejected")

        # When Buffy tries to add an item it is stuck waiting
        self.rc.set_actor(actor="buffy")
        buffy_action_pk, item = self.rc.add_item(item_name="Buffy's item")
        self.assertEquals(resource.get_items(), [])
        self.assertEquals(Action.objects.get(pk=buffy_action_pk).status, "waiting")

        # Get the conditional action
        conditional_action = self.cc.get_condition_item_given_action(action_pk=buffy_action_pk)

        # Xander tries to approve it and fails.  Xander you goof.
        acc = ApprovalConditionClient(target=conditional_action, actor="xander")
        action_pk, result = acc.approve()
        self.assertEquals(Action.objects.get(pk=action_pk).status, "rejected")
        self.assertEquals(resource.get_items(), [])

        # Now Shauna approves it
        acc.set_actor(actor="shauna")
        action_pk, result = acc.approve()
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")
    
        # And Buffy's item has been added

        # HACK: we need to set up signals or something to update this automatically
        action = Action.objects.get(pk=buffy_action_pk)
        action.take_action()

        self.assertEquals(Action.objects.get(pk=buffy_action_pk).status, "implemented")
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
        action_pk, permission = self.prc.add_permission(permission_type="concord.resources.state_changes.AddItemResourceStateChange",
            permission_actors=["buffy"])
        
        # But she places a condition on the permission that Buffy has to get
        # approval.  She specifies that *Willow* has to approve it.
        self.cc.set_target(target=permission)
        self.cc.addCondition(condition_type="approvalcondition",
            permission_data=json.dumps({
                'permission_type': 'concord.conditionals.state_changes.ApproveStateChange', 
                'permission_actors': ['willow'],
                'permission_roles': []}))

        # When Buffy tries to add an item it is stuck waiting
        self.rc.set_actor(actor="buffy")
        self.rc.set_target(target=resource)
        buffy_action_pk, item = self.rc.add_item(item_name="Buffy's item")
        self.assertEquals(resource.get_items(), [])
        self.assertEquals(Action.objects.get(pk=buffy_action_pk).status, "waiting")

        # Get the conditional action
        conditional_action = self.cc.get_condition_item_given_action(action_pk=buffy_action_pk)

       # Now Willow approves it
        acc = ApprovalConditionClient(target=conditional_action, actor="willow")
        action_pk, result = acc.approve()
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")
    
        # And Buffy's item has been added

        # HACK: we need to set up signals or something to update this automatically
        action = Action.objects.get(pk=buffy_action_pk)
        action.take_action()

        self.assertEquals(Action.objects.get(pk=buffy_action_pk).status, "implemented")
        self.assertEquals(resource.get_items(), ["Buffy's item"])

    def test_cant_self_approve(self):
        # TODO: add this test!
        pass


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
        action_pk, result = self.commClient.change_name(new_name="A Newly Named Community")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")
        self.assertEquals(community.name, "A Newly Named Community")

    def test_reject_change_name_of_community_from_nongovernor(self):
        community = self.commClient.create_community(name="A New Community")
        self.commClient.set_target(target=community)
        self.commClient.set_actor(actor="xander")
        action_pk, result = self.commClient.change_name(new_name="A Newly Named Community")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "rejected")
        self.assertEquals(community.name, "A New Community")

    def test_change_name_of_community_owned_resource(self):
        # SetUp
        community = self.commClient.create_community(name="A New Community")
        rc = ResourceClient(actor="shauna")
        resource = rc.create_resource(name="A New Resource")
        rc.set_target(target=resource)
        action_pk, result = rc.change_owner_of_target(new_owner="A New Community", new_owner_type="com")
        self.assertEquals(resource.get_owner(), "A New Community")
        # Test
        new_action_pk, result = rc.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=new_action_pk).status, "implemented")
        self.assertEquals(resource.name, "A Changed Resource")

    def test_reject_change_name_of_community_owned_resource_from_nongovernor(self):
        # SetUp
        community = self.commClient.create_community(name="A New Community")
        rc = ResourceClient(actor="shauna")
        resource = rc.create_resource(name="A New Resource")
        rc.set_target(target=resource)
        action_pk, result = rc.change_owner_of_target(new_owner="A New Community", new_owner_type="com")
        self.assertEquals(resource.get_owner(), "A New Community")
        # Test
        rc.set_actor(actor="xander")
        new_action_pk, result = rc.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=new_action_pk).status, "rejected")
        self.assertEquals(resource.name, "A New Resource")

    def test_add_permission_to_community_owned_resource_allowing_nongovernor_to_change_name(self):
        
        # SetUp
        community = self.commClient.create_community(name="A New Community")
        rc = ResourceClient(actor="shauna")
        resource = rc.create_resource(name="A New Resource")
        rc.set_target(target=resource)
        action_pk, result = rc.change_owner_of_target(new_owner="A New Community", new_owner_type="com")
        self.assertEquals(resource.get_owner(), "A New Community")

        # Add  permission for nongovernor to change name
        prc = PermissionResourceClient(actor="shauna")
        prc.set_target(target=resource)
        action_pk, permission = prc.add_permission(permission_type="concord.resources.state_changes.ChangeResourceNameStateChange",
            permission_actors=["xander"])
        
        # Test - Xander should now be allowed to change name
        rc.set_actor(actor="xander")
        new_action_pk, result = rc.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=new_action_pk).status, "implemented")
        self.assertEquals(resource.name, "A Changed Resource")    

        # Test - Governors should still be able to do other things still that are not set in PR
        rc.set_actor(actor="shauna")
        new_action_pk, result = rc.add_item(item_name="Shauna's item")
        self.assertEquals(resource.get_items(), ["Shauna's item"])

    def test_add_governor(self):
        community = self.commClient.create_community(name="A New Community")
        self.commClient.set_target(community)
        action_pk, result = self.commClient.add_governor(governor_name="alexandra")
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
        action_pk, result = self.condClient.addConditionToGovernors(
            condition_type="approvalcondition",
            permission_data=json.dumps({
                'permission_type': 'concord.conditionals.state_changes.ApproveStateChange',
                'permission_actors': ['alexandra'],
                'permission_roles': ''}))
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented") # Action accepted

        # Check that the condition template's owner is correct
        ct = self.condClient.get_condition_template_for_governor()
        self.assertEquals(ct.get_owner(), "A New Community")

        # Governor A does a thing, creates a conditional action to be approved
        action_pk, result = self.commClient.change_name(new_name="A Newly Named Community")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "waiting")
        self.assertEquals(self.community.name, "A New Community")
        conditional_action = self.condClient.get_condition_item_given_action(action_pk=action_pk)

        # Governer B reviews
        acc = ApprovalConditionClient(target=conditional_action, actor="alexandra")
        review_action_pk, result = acc.approve()
        self.assertEquals(Action.objects.get(pk=review_action_pk).status, "implemented")

        # HACK: we need to set up signals or something to update this automatically
        action = Action.objects.get(pk=action_pk)
        action.take_action()

        # Now governor A's thing passes.
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")
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
        action_pk, result = danaResourceClient.change_name(new_name="Dana's resource")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "rejected")
        self.assertEquals(resource.get_name(), "A resource")

        # Owner adds a specific permission for Dana, Dana's action is successful
        prc = PermissionResourceClient(actor="shauna", target=resource)
        owner_action_pk, result = prc.add_permission(permission_type="concord.resources.state_changes.ChangeResourceNameStateChange",
            permission_actors=["dana"])
        action_pk, result = danaResourceClient.change_name(new_name="Dana's resource")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")
        self.assertEquals(resource.get_name(), "Dana's resource")

        # Now switch foundational override.
        fp_action_pk, result = prc.enable_foundational_permission()

        # Dana's actions are no longer successful
        danaResourceClient = ResourceClient(actor="dana", target=resource)
        action_pk, result = danaResourceClient.change_name(new_name="A new name for Dana's resource")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "rejected")
        self.assertEquals(resource.get_name(), "Dana's resource")

    def test_foundational_authority_override_on_community_owned_object(self):
        
        # By default, Dana's actions are not successful
        danaResourceClient = ResourceClient(actor="dana", target=self.resource)
        action_pk, result = danaResourceClient.change_name(new_name="Dana's resource")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "rejected")
        self.assertEquals(self.resource.get_name(), "A New Resource")

        # Owner adds a specific permission for Dana, Dana's action is successful
        prc = PermissionResourceClient(actor="shauna", target=self.resource)
        owner_action_pk, result = prc.add_permission(permission_type="concord.resources.state_changes.ChangeResourceNameStateChange",
            permission_actors=["dana"])
        action_pk, result = danaResourceClient.change_name(new_name="Dana's resource")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")
        self.assertEquals(self.resource.get_name(), "Dana's resource")

        # Now switch foundational override.
        # NOTE: it's a little weird that base client stuff is accessible from everywhere, no?
        fp_action_pk, result = prc.enable_foundational_permission()

        # Dana's actions are no longer successful
        danaResourceClient = ResourceClient(actor="dana", target=self.resource)
        action_pk, result = danaResourceClient.change_name(new_name="A new name for Dana's resource")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "rejected")
        self.assertEquals(self.resource.get_name(), "Dana's resource")

    def test_foundational_authority_override_on_community_owned_object_with_conditional(self):
        
        # Shauna, Amal, Dana and Joy are members of community X.  
        self.commClient.set_target(self.community)
        action_pk, result = self.commClient.add_member(name="amal")
        action_pk, result = self.commClient.add_member(name="dana")
        action_pk, result = self.commClient.add_member(name="joy")
        com_members = self.commClient.get_members()
        self.assertCountEqual(com_members, ["shauna", "amal", "dana", "joy"])

        # In this community, all members are owners but for the foundational authority to do
        # anything they must agree via majority vote.
        action_pk, result = self.commClient.add_owner_role(owner_role="members") # Add member role
        self.condClient = CommunityConditionalClient(actor="shauna", target=self.community)

        # FIXME: wow this is too much configuration needed!
        action_pk, result = self.condClient.addConditionToOwners(
            condition_type = "votecondition",
            permission_data = json.dumps({
                'permission_type': 'concord.conditionals.state_changes.AddVoteStateChange',
                'permission_actors': '[]',
                'permission_roles': ['1_members']}),
            condition_data=json.dumps({"voting_period": 0.0001 }))

        # Dana tries to change the name of the resource but is not successful.
        danaResourceClient = ResourceClient(actor="dana", target=self.resource)
        action_pk, result = danaResourceClient.change_name(new_name="Dana's resource")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "rejected")
        self.assertEquals(self.resource.get_name(), "A New Resource")

        # Dana tries to switch on foundational override.  This goes to foundational authority
        # and it generates a vote.  Everyone votes and it's approved. 
        key_action_pk, result = danaResourceClient.enable_foundational_permission()
        self.assertEquals(Action.objects.get(pk=key_action_pk).status, "waiting")
        conditional_action = self.condClient.get_condition_item_given_action(action_pk=key_action_pk)

        vcc = VoteConditionClient(target=conditional_action, actor="shauna")
        vcc.vote(vote="yea")
        vcc.set_actor("amal")
        vcc.vote(vote="yea")
        vcc.set_actor("joy")
        vcc.vote(vote="yea")
        vcc.set_actor("dana")
        vcc.vote(vote="yea")

        time.sleep(.02)

        # HACK: we need to set up signals or something to update this automatically
        action = Action.objects.get(pk=key_action_pk)
        action.take_action()

        self.assertEquals(Action.objects.get(pk=key_action_pk).status, "implemented")
        resource = self.resourceClient.get_resource_given_pk(pk=self.resource.pk)
        self.assertTrue(resource[0].foundational_permission_enabled)

    def test_change_governors_requires_foundational_authority(self):
        # Shauna is the owner, Shauna and Alexandra are governors.
        self.commClient.set_target(self.community)
        action_pk, result = self.commClient.add_governor(governor_name="alexandra")
        self.assertEquals(self.community.authorityhandler.get_governors(),
            {'actors': ['shauna', 'alexandra'], 'roles': []})

        # Dana tries to add Joy as a governor.  She cannot, she is not an owner.
        self.commClient.set_actor("dana")
        action_pk, result = self.commClient.add_governor(governor_name="joy")
        self.assertEquals(self.community.authorityhandler.get_governors(), 
            {'actors': ['shauna', 'alexandra'], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action_pk).status, "rejected")

        # Alexandra tries to add Joy as a governor.  She cannot, she is not a governor.
        self.commClient.set_actor("alexandra")
        action_pk, result = self.commClient.add_governor(governor_name="joy")
        self.assertEquals(self.community.authorityhandler.get_governors(), 
            {'actors': ['shauna', 'alexandra'], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action_pk).status, "rejected")

        # Shauna tries to add Joy as a governor.  She can, since has foundational authority.
        self.commClient.set_actor("shauna")
        action_pk, result = self.commClient.add_governor(governor_name="joy")
        self.assertEquals(self.community.authorityhandler.get_governors(), 
            {'actors': ['shauna', 'alexandra', 'joy'], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")

    def test_change_owners_requires_foundational_authority(self):

        # Shauna adds Alexandra as owner.  There are now two owners with no conditions.
        self.commClient.set_target(self.community)
        action_pk, result = self.commClient.add_owner(owner_name="alexandra")
        self.assertEquals(self.community.authorityhandler.get_owners(), 
            {'actors': ['shauna', 'alexandra'], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")

        # Dana tries to add Amal as owner.  She cannot, she is not an owner.
        self.commClient.set_actor("dana")
        action_pk, result = self.commClient.add_owner(owner_name="amal")
        self.assertEquals(self.community.authorityhandler.get_owners(), 
            {'actors': ['shauna', 'alexandra'], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action_pk).status, "rejected")

        # Alexandra tries to add Amal as owner.  She can, since has foundational authority.
        self.commClient.set_actor("alexandra")
        action_pk, result = self.commClient.add_owner(owner_name="amal")
        # self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")

        self.assertEquals(self.community.authorityhandler.get_owners(), 
            {'actors': ['shauna', 'alexandra', 'amal'], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")

    def test_change_foundational_override_requires_foundational_authority(self):
        # Shauna is the owner, Shauna and Alexandra are governors.
        self.commClient.set_target(self.community)
        action_pk, result = self.commClient.add_governor(governor_name="alexandra")
        self.assertEquals(self.community.authorityhandler.get_governors(), 
            {'actors': ['shauna', 'alexandra'], 'roles': []})
        self.resourceClient.set_target(self.resource)

        # Dana tries to enable foundational override on resource. 
        # She cannot, she is not an owner.
        self.resourceClient.set_actor("dana")
        action_pk, result = self.resourceClient.enable_foundational_permission()
        self.assertEquals(Action.objects.get(pk=action_pk).status, "rejected")
        self.assertFalse(self.resource.foundational_permission_enabled)

        # Alexandra tries to enable foundational override on resource.
        # She cannot, she is not a governor.
        self.resourceClient.set_actor("alexandra")
        action_pk, result = self.resourceClient.enable_foundational_permission()
        self.assertEquals(Action.objects.get(pk=action_pk).status, "rejected")
        self.assertFalse(self.resource.foundational_permission_enabled)

        # Shauna tries to enable foundational override on resource.
        # She can, since has foundational authority.
        self.resourceClient.set_actor("shauna")
        action_pk, result = self.resourceClient.enable_foundational_permission()
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")
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
        action_pk, result = self.commClient.add_assigned_role(role_name="administrators")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")
        roles = self.commClient.get_assigned_roles()
        self.assertEquals(roles, {'members': ['shauna'], 'administrators': []})

        # Add people to role
        action_pk, result = self.commClient.add_people_to_role(role_name="administrators", 
            people_to_add=["helga", "jon"])
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")
        roles = self.commClient.get_assigned_roles()
        self.assertCountEqual(roles["administrators"], ["helga", "jon"])

        # Remove person from role
        action_pk, result = self.commClient.remove_people_from_role(role_name="administrators", 
            people_to_remove=["jon"])
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")
        roles = self.commClient.get_assigned_roles()
        self.assertCountEqual(roles["administrators"], ["helga"])

        # Remove role
        action_pk, result = self.commClient.remove_assigned_role(role_name="administrators")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")
        roles = self.commClient.get_assigned_roles()
        self.assertEquals(roles, {'members': ['shauna']})

    def test_basic_assigned_role_works_with_permission_item(self):

        # Dana wants to change the name of the resource, she can't
        self.resourceClient.set_actor("dana")
        action_pk, result = self.resourceClient.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "rejected")
        self.assertEquals(self.resource.name, "A new resource")

        # Shauna adds a 'namers' role to the community which owns the resource
        self.resourceClient.set_actor("shauna")
        action_pk, result = self.commClient.add_assigned_role(role_name="namers")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")
        roles = self.commClient.get_assigned_roles()
        self.assertEquals(roles, {'members': ['shauna'], 'namers': []})

        # Shauna creates a permission item with the 'namers' role in it
        self.permClient.set_target(self.resource)
        role_pair = str(self.community.pk) + "_" + "namers"  # FIXME: needs too much syntax knowledge 
        action_pk, result = self.permClient.add_permission(permission_type="concord.resources.state_changes.ChangeResourceNameStateChange",
            permission_role_pairs=[role_pair])
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")

        # Shauna adds Dana to the 'namers' role in the community
        action_pk, result = self.commClient.add_people_to_role(role_name="namers", 
            people_to_add=["dana"])
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")
        roles = self.commClient.get_assigned_roles()
        self.assertCountEqual(roles["namers"], ["dana"])

        # Dana can now change the name of the resource
        self.resourceClient.set_actor("dana")
        action_pk, result = self.resourceClient.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")
        self.assertEquals(self.resource.name, "A Changed Resource")

        # Shauna removes Dana from the namers role in the community
        action_pk, result = self.commClient.remove_people_from_role(role_name="namers", 
            people_to_remove=["dana"])
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")
        roles = self.commClient.get_assigned_roles()
        self.assertCountEqual(roles["namers"], [])

        # Dana can no longer change the name of the resource
        self.resourceClient.set_actor("dana")
        action_pk, result = self.resourceClient.change_name(new_name="A Newly Changed Resource")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "rejected")
        self.assertEquals(self.resource.name, "A Changed Resource")

    def test_basic_assigned_role_works_with_authorityhandler_governor(self):        

        # Shauna adds the resource to her community
        self.resourceClient.set_target(target=self.resource)
        self.resourceClient.change_owner_of_target(new_owner="A New Community", new_owner_type="com")

        # Dana wants to change the name of the resource, she can't
        self.resourceClient.set_actor("dana")
        action_pk, result = self.resourceClient.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "rejected")
        self.assertEquals(self.resource.name, "A new resource")

        # Shauna adds member role to governors
        action_pk, result = self.commClient.add_governor_role(governor_role="members")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")
        gov_info = self.commClient.get_governorship_info()
        self.assertAlmostEquals(gov_info, {'actors': ['shauna'], 'roles': ['1_members']})

        # Dana tries to do a thing and can't
        action_pk, result = self.resourceClient.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "rejected")
        self.assertEquals(self.resource.name, "A new resource")

        # Shauna adds Dana to members
        action_pk, result = self.commClient.add_member(name="dana")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")
        roles = self.commClient.get_assigned_roles()
        self.assertCountEqual(roles["members"], ["dana", "shauna"]) 

        # Dana tries to do a thing and can
        action_pk, result = self.resourceClient.change_name(new_name="A Changed Resource")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")
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
    

class CommunityAccessFormTest(TestCase):

    def setUp(self):

        # Create a user
        self.user = "lisemeitner"

        # Create a community
        self.commClient = CommunityClient(actor=self.user)
        self.instance = self.commClient.create_community(name="Nuclear Physicists")
        self.commClient.set_target(self.instance)

        # Create a request object
        import collections
        User = collections.namedtuple('User', 'username')
        Request = collections.namedtuple('Request', 'user')
        self.request = Request(user=User(username=self.user))

        # Create permissions client too
        self.permClient = PermissionResourceClient(actor=self.user, target=self.instance)

        # Initial data
        self.data = {"0_rolename": "members", "0_members": "lisemeitner", "0_permissions": []}

    def test_initialize_access_form(self):

        self.access_form = AccessForm(instance=self.instance, request=self.request)
        self.assertEquals(list(self.access_form.fields.keys()), 
            ['0_rolename', '0_members', '0_permissions', '1_rolename', '1_members', '1_permissions'])
        self.assertEquals(self.access_form.fields["0_rolename"].initial, "members")
        self.assertEquals(self.access_form.fields["0_members"].initial, "lisemeitner")
        self.assertEquals(self.access_form.fields["0_permissions"].initial, [])

        # Add some roles+permissions, so fields and initial will have more data
        self.commClient.add_assigned_role(role_name="PrincipalInvestigators")
        self.commClient.add_people_to_role(role_name="PrincipalInvestigators",
            people_to_add=["Irene Joliot-Curie", "Ida Noddack"])
        action, permission = self.permClient.add_permission(
            permission_type="concord.communities.state_changes.ChangeNameStateChange",
            permission_role_pairs=["1_PrincipalInvestigators"])

        # Test again
        self.access_form = AccessForm(instance=self.instance, request=self.request)
        self.assertEquals(list(self.access_form.fields.keys()), 
            ['0_rolename', '0_members', '0_permissions', '1_rolename', '1_members', 
            '1_permissions', '2_rolename', '2_members', '2_permissions'])

        if self.access_form.fields["1_rolename"].initial == 'PrincipalInvestigators':
            self.assertCountEqual(self.access_form.fields["1_members"].initial.split(", "),
                ["Ida Noddack", "Irene Joliot-Curie"])        
            self.assertEquals(self.access_form.fields["1_permissions"].initial, 
                ["concord.communities.state_changes.ChangeNameStateChange"])  
        else:
            self.assertCountEqual(self.access_form.fields["0_members"].initial.split(", "),
                ["Ida Noddack", "Irene Joliot-Curie"])        
            self.assertEquals(self.access_form.fields["0_permissions"].initial, 
                ["concord.communities.state_changes.ChangeNameStateChange"])    

    def test_add_role_via_access_form(self):

        # Add a role! 

        self.data.update({
            '1_rolename': 'PrincipalInvestigators',
            '1_members': 'Ida Noddack, Irene Joliot-Curie',
            '1_permissions': ['concord.communities.state_changes.ChangeNameStateChange']
        })
        self.access_form = AccessForm(instance=self.instance, request=self.request, data=self.data)
        result = self.access_form.is_valid()
        self.assertEquals(self.access_form.cleaned_data, 
            {'0_rolename': 'members', '0_members': 'lisemeitner', '0_permissions': [], 
                '1_rolename': 'PrincipalInvestigators', '1_members': 'Ida Noddack, Irene Joliot-Curie',
                '1_permissions': ['concord.communities.state_changes.ChangeNameStateChange']})

        self.access_form.save()
        perms = self.permClient.get_permissions_on_object(object=self.instance)
        self.assertEquals(perms[0].get_roles(), ['1_PrincipalInvestigators'])

        roles = self.commClient.get_assigned_roles()
        self.assertCountEqual(list(roles.keys()), ['members', 'PrincipalInvestigators'])

        # Now remove role from permission

        self.data = {"0_rolename": "members", "0_members": "lisemeitner", "0_permissions": []}
        self.access_form = AccessForm(instance=self.instance, request=self.request, data=self.data)
        result = self.access_form.is_valid()
        self.access_form.save()

        perms = self.permClient.get_permissions_on_object(object=self.instance)
        self.assertFalse(perms)  # Empty queryset should be falsy

        # Does not remove role from community
        roles = self.commClient.get_assigned_roles()
        self.assertCountEqual(list(roles.keys()), ['members', 'PrincipalInvestigators'])
   
    def test_add_permission_to_existing_role_via_access_form(self):

        self.data["0_permissions"] = ['concord.communities.state_changes.ChangeNameStateChange']

        self.access_form = AccessForm(instance=self.instance, request=self.request, data=self.data)
        result = self.access_form.is_valid()
        self.access_form.save()

        roles = self.commClient.get_assigned_roles()
        self.assertEquals(list(roles.keys()), ['members'])

        perms = self.permClient.get_permissions_on_object(object=self.instance)
        self.assertEquals(perms[0].get_roles(), ['1_members'])
        self.assertEquals(perms[0].change_type, 'concord.communities.state_changes.ChangeNameStateChange')

    # do we want to test the view itself? ie with https://docs.djangoproject.com/en/2.2/topics/testing/advanced/#the-request-factory

class ResourceAccessFormTest(TestCase):

    def setUp(self):

        # Create a user
        self.user = "lisemeitner"

        # Create a community
        self.commClient = CommunityClient(actor=self.user)
        self.instance = self.commClient.create_community(name="Nuclear Physicists")
        self.commClient.set_target(self.instance)

        # Create a resource
        self.resClient = ResourceClient(actor=self.user)
        self.resource = self.resClient.create_resource(name="Table of the Elements")
        self.resClient.set_target(target=self.resource)
        self.resClient.change_owner_of_target(new_owner="Nuclear Physicists", new_owner_type="com")
 
        # Perm client for resource
        self.permClient = PermissionResourceClient(actor=self.user, target=self.resource)

        # Add more people to 'members' role
        self.commClient.add_people_to_role(role_name="members",
            people_to_add=["Irene Joliot-Curie", "Ida Noddack"])

        # Create request objects for various users
        import collections
        User = collections.namedtuple('User', 'username')
        Request = collections.namedtuple('Request', 'user')
        self.lise_request = Request(user=User(username=self.user))
        self.ida_request = Request(user=User(username="Ida Noddack"))

        # Initial data
        self.data = {"0_rolename": "members", "0_members": "lisemeitner, Ida Noddack, Irene Joliot-Curie", "0_permissions": []}

    def test_access_form_on_owned_resource(self):

        self.data.update({
            '1_rolename': 'PrincipalInvestigators',
            '1_members': 'Ida Noddack, Irene Joliot-Curie',
            '1_permissions': ['concord.resources.state_changes.ChangeResourceNameStateChange']
        })

        # member of community cannot use access form to change permissions

        self.access_form = AccessForm(instance=self.resource, request=self.ida_request, data=self.data)
        result = self.access_form.is_valid()
        self.assertEquals(self.access_form.cleaned_data, 
            {'0_rolename': 'members', 
            '0_members': 'lisemeitner, Ida Noddack, Irene Joliot-Curie', 
            '0_permissions': [], 
            '1_rolename': 'PrincipalInvestigators', 
            '1_members': 'Ida Noddack, Irene Joliot-Curie',
            '1_permissions': ['concord.resources.state_changes.ChangeResourceNameStateChange']})
        self.access_form.save()
        perms = self.permClient.get_permissions_on_object(object=self.resource)
        self.assertFalse(perms)  # Empty queryset should be falsy

        # creator of community can use access form to change permissions

        self.access_form = AccessForm(instance=self.resource, request=self.lise_request, data=self.data)
        result = self.access_form.is_valid()
        self.assertEquals(self.access_form.cleaned_data, 
            {'0_rolename': 'members', '0_members': 'lisemeitner, Ida Noddack, Irene Joliot-Curie', '0_permissions': [], 
                '1_rolename': 'PrincipalInvestigators', '1_members': 'Ida Noddack, Irene Joliot-Curie',
                '1_permissions': ['concord.resources.state_changes.ChangeResourceNameStateChange']})

        self.access_form.save()
        perms = self.permClient.get_permissions_on_object(object=self.resource)
        self.assertEquals(perms[0].get_roles(), ['1_PrincipalInvestigators'])


class RoleFormTest(TestCase):

    def setUp(self):
        # Create a user
        self.user = "cap"

        # Create a community
        self.commClient = CommunityClient(actor=self.user)
        self.instance = self.commClient.create_community(name="Barbershop Quartet")
        self.commClient.set_target(self.instance)

        # Create request object
        import collections
        User = collections.namedtuple('User', 'username')
        Request = collections.namedtuple('Request', 'user')
        self.request = Request(user=User(username=self.user))

        # Initial data
        self.data = {"0_rolename": "members", "0_members": "cap"}

    def test_add_role_via_role_form(self):

        # Before doing anything, only role is members and only user in members is cap
        self.assertEquals(self.commClient.get_assigned_role_names(), ["members"])
        self.assertEquals(self.commClient.get_members(), ["cap"])

        # Add a new role using the role form
        self.data.update({
            '1_rolename': 'runners',
            '1_members': 'cap, falcon'})
        self.role_form = RoleForm(instance=self.instance, request=self.request, data=self.data)
        
        # Form is valid and cleaned data is correct
        result = self.role_form.is_valid()
        self.assertEquals(self.role_form.cleaned_data, 
            {'0_rolename': 'members', 
            '0_members': 'cap', 
            '1_rolename': 'runners', 
            '1_members': 'cap, falcon'})

        # After saving, data is updated.
        self.role_form.save()
        self.assertCountEqual(self.commClient.get_assigned_role_names(), ["members", "runners"])
        self.assertEquals(self.commClient.get_members(), ["cap"])

    def test_add_user_to_role_via_role_form(self):

        # Before doing anything, only user in members is cap
        self.assertEquals(self.commClient.get_members(), ["cap"])

        # Add a user using the role form
        self.data.update({
            '0_rolename': 'members', 
            '0_members': 'cap, falcon'})
        self.role_form = RoleForm(instance=self.instance, request=self.request, data=self.data)
        
        # Form is valid and cleaned data is correct
        result = self.role_form.is_valid()
        self.assertEquals(self.role_form.cleaned_data, 
            {'0_rolename': 'members', 
            '0_members': 'cap, falcon',
            '1_members': '',    # empty row, will be discarded
            '1_rolename': ''})  # empty row, will be discarded

        # After saving, data is updated.
        self.role_form.save()
        self.assertCountEqual(self.commClient.get_members(), ["cap", "falcon"])

    # TODO: can't remove role via form since it may have dependencies, need a different
    # way to test this.
    # def test_remove_role_via_role_form(self):
    
    def test_remove_user_from_role_via_role_form(self):

        # Quick add via form
        self.data.update({
            '1_rolename': 'runners',
            '1_members': 'cap, falcon'})
        self.role_form = RoleForm(instance=self.instance, request=self.request, data=self.data)
        self.role_form.is_valid()
        self.role_form.save()
        self.assertCountEqual(self.commClient.get_assigned_role_names(), 
            ["members", "runners"])
        self.assertCountEqual(self.commClient.get_users_given_role(role_name="runners"), 
            ["cap", "falcon"])

        # Remove role via form
        self.data = {"0_rolename": "members", "0_members": "cap", 
            '1_rolename': 'runners', '1_members': 'cap'}
        self.role_form = RoleForm(instance=self.instance, request=self.request, data=self.data)

         # Form is valid and cleaned data is correct
        result = self.role_form.is_valid()
        self.assertEquals(self.role_form.cleaned_data, 
            {'0_rolename': 'members', '0_members': 'cap', 
            '1_rolename': 'runners', '1_members': 'cap',
            '2_rolename': '', '2_members': ''})

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
        self.instance = self.commClient.create_community(name="Barbershop Quartet")
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
            self.data[str(count) + "_" + "name"] = permission
            self.data[str(count) + "_" + "roles"] = []
            self.data[str(count) + "_" + "individuals"] = []

    def test_instantiate_permission_form(self):
        # NOTE: this only works for community permission form with role_choices set

        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request)

        # Get possible permissions to set on instance
        self.prClient = PermissionResourceClient(actor=self.user, target=self.instance)
        permissions = self.prClient.get_settable_permissions(return_format="list_of_strings")

        # Number of fields on permission form should be permissions x 3
        self.assertEqual(len(permissions)*3, len(self.permission_form.fields))

    def test_add_role_to_permission(self):

        # Before changes, no permissions associated with role
        permissions_for_role = self.prClient.get_permissions_associated_with_role(role_name="assassins",
            community=self.instance)
        self.assertEqual(permissions_for_role, [])

        # add role to permission
        self.data["4_roles"] = ["assassins"]
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)

        # Check that it's valid
        self.permission_form.is_valid()
        self.assertEquals(self.permission_form.cleaned_data["4_roles"], ["assassins"])
        
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
        self.data["4_roles"] = ["assassins", "veterans"]  # Use this format since it's a multiple choice field
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)

        # Check that it's valid
        self.permission_form.is_valid()
        self.assertEquals(self.permission_form.cleaned_data["4_roles"], ["assassins", "veterans"])
        
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
        self.data["4_individuals"] = "whitewolf"  # use this format since it's a character field
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)

        # Check that it's valid
        self.permission_form.is_valid()
        self.assertEquals(self.permission_form.cleaned_data["4_individuals"], 
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
        self.data["4_individuals"] = "whitewolf blackwidow"  # uses this format since it's a charfield
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)

        # Check that it's valid
        self.permission_form.is_valid()
        self.assertEquals(self.permission_form.cleaned_data["4_individuals"], 
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
        self.data["4_individuals"] = "whitewolf"
        self.data["5_individuals"] = "whitewolf blackwidow falcon"
        self.data["4_roles"] = ["assassins", "veterans"]
        self.data["2_roles"] = ["assassins", "veterans"]
        self.data["1_roles"] = ["veterans"]

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
        self.data["4_roles"] = ["assassins"]
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()
        permissions_for_role = self.prClient.get_permissions_associated_with_role(role_name="assassins",
            community=self.instance)
        self.assertEqual(permissions_for_role[0].change_type,
            'concord.communities.state_changes.AddPeopleToRoleStateChange')

        # now remove it
        self.data["4_roles"] = []
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()
        permissions_for_role = self.prClient.get_permissions_associated_with_role(role_name="assassins",
            community=self.instance)
        self.assertFalse(permissions_for_role) # Empty list should be falsy

    def test_remove_roles_from_permission(self):

        # add roles to permission
        self.data["4_roles"] = ["assassins", "veterans"]
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
        self.data["4_roles"] = []
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
        self.data["4_individuals"] = "whitewolf"  # use this format since it's a character field
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="whitewolf")
        self.assertEqual(permissions_for_actor[0].change_type,
            'concord.communities.state_changes.AddPeopleToRoleStateChange')

        # Remove actor from permission
        self.data["4_individuals"] = ""  # use this format since it's a character field
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.request, data=self.data)
        self.permission_form.is_valid()
        self.permission_form.save()
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="whitewolf")
        self.assertFalse(permissions_for_actor)  # Empty list should be falsy

    def test_remove_individuals_from_permission(self):
        
        # Add actors to permission
        self.data["4_individuals"] = "blackwidow falcon"  # use this format since it's a character field
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
        self.data["4_individuals"] = ""  # use this format since it's a character field
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
        self.data["4_individuals"] = "whitewolf"
        self.data["5_individuals"] = "whitewolf blackwidow falcon"
        self.data["4_roles"] = ["assassins", "veterans"]
        self.data["2_roles"] = ["assassins", "veterans"]
        self.data["1_roles"] = ["veterans"]

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
        self.data["4_individuals"] = ""
        self.data["5_individuals"] = "blackwidow falcon"
        self.data["4_roles"] = []
        self.data["2_roles"] = ["assassins"]
        self.data["1_roles"] = ["veterans"]

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
        self.data["4_individuals"] = "blackwidow"
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
        self.instance = self.commClient.create_community(name="Barbershop Quartet")
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
            self.permissions_data[str(count) + "_" + "name"] = permission
            self.permissions_data[str(count) + "_" + "roles"] = []
            self.permissions_data[str(count) + "_" + "individuals"] = []

        # Give Natasha permission to add people to roles
        self.permissions_data["4_individuals"] = "blackwidow"
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
            self.metapermissions_data[str(count) + "_" + "name"] = permission
            self.metapermissions_data[str(count) + "_" + "roles"] = []
            self.metapermissions_data[str(count) + "_" + "individuals"] = []

    def test_adding_metapermission_adds_access_to_permission(self):
        # Currently, only Tony is in the Avengers role, only Natasha has permission to 
        # add people to roles, and only Steve has permission to give permission to add
        # people to roles.

        # Steve wants to give Sam the permission to give permission to add people to
        # roles.  Before Steve does anything, Sam tries to give Bucky permission to 
        # add people to roles.  It fails, and we can see that Sam lacks the relevant
        # metapermission and Bucky the relevant permission.

        self.permissions_data["4_individuals"] = "blackwidow whitewolf"
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

        # Then Steve alters, through the metapermissions form, who can add people to
        # a role to include Sam.  He alters the metapermission on the AddPeopleToRole 
        # permission, adding the individual Sam.

        self.metapermissions_data["0_individuals"] = "falcon"
        self.metapermission_form = MetaPermissionForm(instance=self.target_permission, 
            request=self.request, data=self.metapermissions_data)
        self.metapermission_form.is_valid()
        self.metapermission_form.save()

        permissions_for_actor = self.metaClient.get_permissions_associated_with_actor(
            actor="falcon")
        change_types = [perm.short_change_type() for perm in permissions_for_actor]
        self.assertCountEqual(change_types, ['AddActorToPermissionStateChange'])

        # Now Sam can give Bucky permission to add people to roles.

        self.permissions_data["4_individuals"] = "blackwidow whitewolf"
        self.permission_form = PermissionForm(instance=self.instance, 
            request=self.samRequest, data=self.permissions_data)
        self.permission_form.is_valid()
        self.permission_form.save()

        # FIXME: This form save is not working... why?

        # Thing #1: Sam should have specific permission now, thanks to Steve.  Why is 
        # it not hitting that, and going to the governing authority?

        # Thing #2: Why is governing authority even enabled???

        # # Bucky can assign people to roles now.

        # self.buckyClient.add_people_to_role(role_name="avengers", people_to_add=["scarletwitch"])
        # roles = self.commClient.get_assigned_roles()
        # self.assertCountEqual(roles["avengers"], ["ironman", "scarletwitch"])

        # Finally, Bucky and Natasha both have permission to add people to roles, while
        # Sam and Steve do not.

        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="whitewolf")
        change_types = [perm.short_change_type() for perm in permissions_for_actor]
        self.assertCountEqual(change_types, ['AddActorToPermissionStateChange'])
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="blackwidow")
        change_types = [perm.short_change_type() for perm in permissions_for_actor]
        self.assertCountEqual(change_types, ['AddActorToPermissionStateChange'])
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="cap")
        change_types = [perm.short_change_type() for perm in permissions_for_actor]
        self.assertCountEqual(change_types, [])
        permissions_for_actor = self.prClient.get_permissions_associated_with_actor(
            actor="falcon")
        change_types = [perm.short_change_type() for perm in permissions_for_actor]
        self.assertCountEqual(change_types, [])

    def test_removing_metapermission_removes_access_to_permission(self):
        ...

    def test_adding_metapermission_to_nonexistent_permission(self):
        ...