import json
from decimal import Decimal
import time

from django.test import TestCase

from resources.client import ResourceClient
from permission_resources.client import PermissionResourceClient
from conditionals.client import ConditionalClient, ApprovalConditionClient, VoteConditionClient
from communities.client import CommunityClient

from actions.models import Action  # For testing action status later, do we want a client?


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
        resource = self.rc.create_resource(name="Aha")
        self.prc.set_target(target=resource)
        action_pk, permission = self.prc.add_permission(permission_type="permissions_resource_additem",
            permission_actor="shauna")
        items = self.prc.get_all_permissions_on_object(target=resource)
        self.assertEquals(items.first().get_name(), 'Permission 1 (for permissions_resource_additem on Resource object (1))')

    def test_remove_permission_from_resource(self):
        """
        Test removal of permission from resource.
        """
        resource = self.rc.create_resource(name="Aha")
        self.prc.set_target(target=resource)
        action_pk, permission = self.prc.add_permission(permission_type="permissions_resource_additem",
            permission_actor="shauna")
        items = self.prc.get_all_permissions_on_object(target=resource)
        self.assertEquals(items.first().get_name(), 'Permission 1 (for permissions_resource_additem on Resource object (1))')
        self.prc.remove_permission(item_pk=permission.pk)
        items = self.prc.get_all_permissions_on_object(target=resource)
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
        action_pk, permission = self.prc.add_permission(
            target=resource,
            permission_type="resource_additem",
            permission_actor="buffy")
        items = self.prc.get_all_permissions_on_object(target=resource)
        self.assertEquals(items.first().get_name(), 'Permission 1 (for resource_additem on Resource object (1))')

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
        action_pk, permission = self.prc.add_permission(
            target=resource,
            permission_type="resource_additem",
            permission_actor="willow")

        # Buffy can't add an item to this resource because she's not the owner nor specified in
        # the permission.        
        brc = ResourceClient(actor="buffy", target=resource)
        action_pk, item = brc.add_item(item_name="Buffy's item")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "rejected")

        # Shauna adds a permission on the permission which Buffy does have.
        self.prc.set_target(target=permission)
        action_pk, rec_permission = self.prc.add_permission(
            permission_type="permissionitem_addpermission",
            permission_actor="buffy")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")

        # Buffy still cannot make the change because she does not have the permission.
        brc = ResourceClient(actor="buffy", target=resource)
        action_pk, item = brc.add_item(item_name="Buffy's item")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "rejected")
        
        # BUT Buffy CAN make the second-level change.
        bprc = PermissionResourceClient(actor="buffy", target=permission)
        action_pk, permission = bprc.add_permission(permission_type="permissionresource_addpermission",
            permission_actor="willow")        
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")


class ConditionalsTest(TestCase):

    def setUp(self):
        self.cc = ConditionalClient(actor="shauna")
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
            permission_type="conditionalvote_addvote",
            permission_actor="buffy")
        vote_permission = self.prc.add_permission(
            permission_type="conditionalvote_addvote",
            permission_actor="willow")            

        # Now Buffy and Willow can vote but Xander can't
        self.cc = ConditionalClient(actor="buffy")
        default_vote = self.cc.getVoteCondition(pk=default_vote.target.pk)
        default_vote.vote(vote="yea")
        self.assertDictEqual(default_vote.get_current_results(), 
            { "yeas": 1, "nays": 0, "abstains": 0 })
        self.cc = ConditionalClient(actor="willow")
        default_vote = self.cc.getVoteCondition(pk=default_vote.target.pk)
        default_vote.vote(vote="abstain")
        self.assertDictEqual(default_vote.get_current_results(), 
            { "yeas": 1, "nays": 0, "abstains": 1})
        self.cc = ConditionalClient(actor="xander")
        default_vote = self.cc.getVoteCondition(pk=default_vote.target.pk)
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
        action_pk, permission = self.prc.add_permission(permission_type="resource_additem",
            permission_actor="buffy")
        
        # But she places a condition on the permission that Buffy has to get
        # approval (without specifying permissions, so it uses the default.
        self.cc.set_target(target=permission)
        self.cc.addConditionToPermission(condition_type="approvalcondition")

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
        action_pk, permission = self.prc.add_permission(permission_type="resource_additem",
            permission_actor="buffy")
        
        # But she places a condition on the permission that Buffy has to get
        # approval.  She specifies that *Willow* has to approve it.
        self.cc.set_target(target=permission)
        self.cc.addConditionToPermission(condition_type="approvalcondition",
            permission_data=json.dumps({'permission_type': 'conditional_approvecondition', 
                'permission_actor': 'willow'}))

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
        new_action_pk, result = rc.change_name("A Changed Resource")
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
        new_action_pk, result = rc.change_name("A Changed Resource")
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
        action_pk, permission = prc.add_permission(permission_type="resource_changename",
            permission_actor="xander")
        
        # Test - Xander should now be allowed to change name
        rc.set_actor(actor="xander")
        new_action_pk, result = rc.change_name("A Changed Resource")
        self.assertEquals(Action.objects.get(pk=new_action_pk).status, "implemented")
        self.assertEquals(resource.name, "A Changed Resource")    

        # Test - Governors should still be able to do other things still that are not set in PR
        rc.set_actor(actor="shauna")
        new_action_pk, result = rc.add_item(item_name="Shauna's item")
        self.assertEquals(resource.get_items(), ["Shauna's item"])

    def test_add_governor(self):
        community = self.commClient.create_community(name="A New Community")
        self.commClient.set_target(community)
        action_pk, result = self.commClient.add_governor("alexandra")
        self.assertEquals(community.authorityhandler.get_governors(),
            {'actors': ['shauna', 'alexandra'], 'roles': []})


class GoverningAuthorityTest(TestCase):

    def setUp(self):
        self.commClient = CommunityClient(actor="shauna")
        self.community = self.commClient.create_community(name="A New Community")
        self.commClient.set_target(target=self.community)
        self.commClient.add_governor("alexandra")
        self.condClient = ConditionalClient(actor="shauna")
        self.condClient.set_target(target=self.community)

    def test_with_conditional_on_governer_decision_making(self):

        # Set conditional on governor decision making.  Only Alexandra can approve condition.
        action_pk, result = self.condClient.addConditionToGovernors(
            condition_type="approvalcondition",
            permission_data=json.dumps({
                'permission_type': 'conditional_approvecondition',
                'permission_actor': 'alexandra'}))
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented") # Action accepted

        # Check that the condition template's owner is correct
        ct = self.condClient.get_condition_template_for_governor(self.community.pk)
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
        community = self.commClient.get_community_given_pk(pk=self.community.pk) # Refresh
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
        owner_action_pk, result = prc.add_permission(permission_type="resource_changename",
            permission_actor="dana")
        action_pk, result = danaResourceClient.change_name(new_name="Dana's resource")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")
        self.assertEquals(resource.get_name(), "Dana's resource")

        # Now switch foundational override.
        # NOTE: it's a little weird that base client stuff is accessible from everywhere, no?
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
        owner_action_pk, result = prc.add_permission(permission_type="resource_changename",
            permission_actor="dana")
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
        action_pk, result = self.commClient.add_member("amal")
        action_pk, result = self.commClient.add_member("dana")
        action_pk, result = self.commClient.add_member("joy")
        com_members = self.commClient.get_members(self.community.name)
        self.assertCountEqual(com_members, ["shauna", "amal", "dana", "joy"])

        # In this community, all members are owners but for the foundational authority to do
        # anything they must agree via majority vote.
        action_pk, result = self.commClient.add_owner_role("members") # Add member role
        self.condClient = ConditionalClient(actor="shauna")

        # FIXME: wow this is too much configuration needed!
        action_pk, result = self.condClient.addConditionToOwners(
            condition_type = "votecondition",
            permission_data = json.dumps({
                'permission_type': 'conditional_addvote',
                'permission_actor': 'members'}),
            target=self.community,
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
        vcc.vote("yea")
        vcc.set_actor("amal")
        vcc.vote("yea")
        vcc.set_actor("joy")
        vcc.vote("yea")
        vcc.set_actor("dana")
        vcc.vote("yea")

        time.sleep(.01)

        # HACK: we need to set up signals or something to update this automatically
        action = Action.objects.get(pk=key_action_pk)
        action.take_action()

        self.assertEquals(Action.objects.get(pk=key_action_pk).status, "implemented")
        resource = self.resourceClient.get_resource_given_pk(self.resource.pk)
        self.assertTrue(resource[0].foundational_permission_enabled)

    def test_change_governors_requires_foundational_authority(self):
        # Shauna is the owner, Shauna and Alexandra are governors.
        self.commClient.set_target(self.community)
        action_pk, result = self.commClient.add_governor("alexandra")
        self.assertEquals(self.community.authorityhandler.get_governors(),
            {'actors': ['shauna', 'alexandra'], 'roles': []})

        # Dana tries to add Joy as a governor.  She cannot, she is not an owner.
        self.commClient.set_actor("dana")
        action_pk, result = self.commClient.add_governor("joy")
        self.assertEquals(self.community.authorityhandler.get_governors(), 
            {'actors': ['shauna', 'alexandra'], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action_pk).status, "rejected")

        # Alexandra tries to add Joy as a governor.  She cannot, she is not a governor.
        self.commClient.set_actor("alexandra")
        action_pk, result = self.commClient.add_governor("joy")
        self.assertEquals(self.community.authorityhandler.get_governors(), 
            {'actors': ['shauna', 'alexandra'], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action_pk).status, "rejected")

        # Shauna tries to add Joy as a governor.  She can, since has foundational authority.
        self.commClient.set_actor("shauna")
        action_pk, result = self.commClient.add_governor("joy")
        self.assertEquals(self.community.authorityhandler.get_governors(), 
            {'actors': ['shauna', 'alexandra', 'joy'], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")

    def test_change_owners_requires_foundational_authority(self):

        # Shauna adds Alexandra as owner.  There are now two owners with no conditions.
        self.commClient.set_target(self.community)
        action_pk, result = self.commClient.add_owner("alexandra")
        self.assertEquals(self.community.authorityhandler.get_owners(), 
            {'actors': ['shauna', 'alexandra'], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")

        # Dana tries to add Amal as owner.  She cannot, she is not an owner.
        self.commClient.set_actor("dana")
        action_pk, result = self.commClient.add_owner("amal")
        self.assertEquals(self.community.authorityhandler.get_owners(), 
            {'actors': ['shauna', 'alexandra'], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action_pk).status, "rejected")

        # Alexandra tries to add Amal as owner.  She can, since has foundational authority.
        self.commClient.set_actor("alexandra")
        action_pk, result = self.commClient.add_owner("amal")
        self.assertEquals(self.community.authorityhandler.get_owners(), 
            {'actors': ['shauna', 'alexandra', 'amal'], 'roles': []})
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")

    def test_change_foundational_override_requires_foundational_authority(self):
        # Shauna is the owner, Shauna and Alexandra are governors.
        self.commClient.set_target(self.community)
        action_pk, result = self.commClient.add_governor("alexandra")
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
        roles = self.commClient.get_assigned_roles(self.community.pk)
        self.assertEquals(roles, {'members': ['shauna']})

        # Add a role
        action_pk, result = self.commClient.add_assigned_role("administrators")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")
        roles = self.commClient.get_assigned_roles(self.community.pk)
        self.assertEquals(roles, {'members': ['shauna'], 'administrators': []})

        # Add people to role
        action_pk, result = self.commClient.add_people_to_role("administrators", ["helga", "jon"])
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")
        roles = self.commClient.get_assigned_roles(self.community.pk)
        self.assertCountEqual(roles["administrators"], ["helga", "jon"])

        # Remove person from role
        action_pk, result = self.commClient.remove_people_from_role("administrators", ["jon"])
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")
        roles = self.commClient.get_assigned_roles(self.community.pk)
        self.assertCountEqual(roles["administrators"], ["helga"])

        # Remove role
        action_pk, result = self.commClient.remove_assigned_role("administrators")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")
        roles = self.commClient.get_assigned_roles(self.community.pk)
        self.assertEquals(roles, {'members': ['shauna']})

    def test_basic_assigned_role_works_with_permission_item(self):

        # Dana wants to change the name of the resource, she can't
        self.resourceClient.set_actor("dana")
        action_pk, result = self.resourceClient.change_name("A Changed Resource")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "rejected")
        self.assertEquals(self.resource.name, "A new resource")

        # Shauna adds a 'namers' role to the community which owns the resource
        self.resourceClient.set_actor("shauna")
        action_pk, result = self.commClient.add_assigned_role("namers")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")
        roles = self.commClient.get_assigned_roles(self.community.pk)
        self.assertEquals(roles, {'members': ['shauna'], 'namers': []})

        # Shauna creates a permission item with the 'namers' role in it
        self.permClient.set_target(self.resource)
        role = str(self.community.pk) + "_" + "namers"  # FIXME: needs too much syntax knowledge 
        action_pk, result = self.permClient.add_permission(permission_type="resource_changename",
            permission_role=role)
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")

        # Shauna adds Dana to the 'namers' role in the community
        action_pk, result = self.commClient.add_people_to_role("namers", ["dana"])
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")
        roles = self.commClient.get_assigned_roles(self.community.pk)
        self.assertCountEqual(roles["namers"], ["dana"])

        # Dana can now change the name of the resource
        self.resourceClient.set_actor("dana")
        action_pk, result = self.resourceClient.change_name("A Changed Resource")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")
        self.assertEquals(self.resource.name, "A Changed Resource")

        # Shauna removes Dana from the namers role in the community
        action_pk, result = self.commClient.remove_people_from_role("namers", ["dana"])
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")
        roles = self.commClient.get_assigned_roles(self.community.pk)
        self.assertCountEqual(roles["namers"], [])

        # Dana can no longer change the name of the resource
        self.resourceClient.set_actor("dana")
        action_pk, result = self.resourceClient.change_name("A Newly Changed Resource")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "rejected")
        self.assertEquals(self.resource.name, "A Changed Resource")

    def test_basic_assigned_role_works_with_authorityhandler_governor(self):        

        # Shauna adds the resource to her community
        self.resourceClient.set_target(target=self.resource)
        self.resourceClient.change_owner_of_target(new_owner="A New Community", new_owner_type="com")

        # Dana wants to change the name of the resource, she can't
        self.resourceClient.set_actor("dana")
        action_pk, result = self.resourceClient.change_name("A Changed Resource")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "rejected")
        self.assertEquals(self.resource.name, "A new resource")

        # Shauna adds member role to governors
        action_pk, result = self.commClient.add_governor_role("members")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")
        gov_info = self.commClient.get_governorship_info(self.community.name)
        self.assertAlmostEquals(gov_info, {'actors': ['shauna'], 'roles': ['1_members']})

        # Dana tries to do a thing and can't
        action_pk, result = self.resourceClient.change_name("A Changed Resource")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "rejected")
        self.assertEquals(self.resource.name, "A new resource")

        # Shauna adds Dana to members
        action_pk, result = self.commClient.add_member("dana")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")
        roles = self.commClient.get_assigned_roles(self.community.pk)
        self.assertCountEqual(roles["members"], ["dana", "shauna"]) 

        # Dana tries to do a thing and can
        action_pk, result = self.resourceClient.change_name("A Changed Resource")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")
        self.assertEquals(self.resource.name, "A Changed Resource")

    def test_add_member_and_remove_member_from_roleset(self):
        self.assertEquals(self.commClient.get_members(community_name=self.community.name), 
            ['shauna'])

        # Shauna adds Dana to the community
        self.commClient.add_member("dana")
        self.assertCountEqual(self.commClient.get_members(community_name=self.community.name), 
            ['shauna', 'dana'])

        # Shauna removes Dana from the community
        self.commClient.remove_member("dana")
        self.assertEquals(self.commClient.get_members(community_name=self.community.name), 
            ['shauna'])

    # TODO: skipping automated roles for now
    

class BatchActionsTest(TestCase):
    ...