import json

from django.test import TestCase

from resources.client import ResourceClient
from permission_resources.client import PermissionResourceClient
from conditionals.client import ConditionalClient, ApprovalConditionClient
from communities.client import CommunityClient

from actions.models import Action  # For testing action status later, do we want a client?


### TODO: 

# 1. Update the clients to return a model wrapped in a client, so that we actually
# enforce the architectural rule of 'only client can be referenced outside the app'
# since tests.py is 100% outside the app.


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

    def test_create_permission_resource(self):
        """
        Test creation of permissions resource through client.
        """
        resource = self.rc.create_resource(name="Aha")
        pr = self.prc.create_permission_resource(permitted_object=resource)
        self.assertEquals(pr.get_unique_id(), "permission_resources_permissionsresource_1")

    def test_add_permission_to_resource(self):
        """
        Test addition of permisssion to resource.
        """
        resource = self.rc.create_resource(name="Aha")
        pr = self.prc.create_permission_resource(permitted_object=resource)
        self.prc.set_target(target=pr)
        action_pk, permission = self.prc.add_permission(permission_type="permissions_resource_additem",
            permission_actor="shauna")
        self.assertEquals(pr.get_items(), ['Permission 1 (permissions_resource_additem for shauna)'])

    def test_remove_permission_from_resource(self):
        """
        Test removal of permission from resource.
        """
        resource = self.rc.create_resource(name="Aha")
        pr = self.prc.create_permission_resource(permitted_object=resource)
        self.prc.set_target(target=pr)
        action_pk, permission = self.prc.add_permission(permission_type="permissions_resource_additem",
            permission_actor="shauna")
        self.assertEquals(pr.get_items(), ['Permission 1 (permissions_resource_additem for shauna)'])
        self.prc.remove_permission(item_pk=permission.pk)
        self.assertEquals(pr.get_items(), [])


class PermissionSystemTest(TestCase):
    """
    The previous two sets of tests use the default permissions setting for the items
    they're modifying.  (Default permissions = 'owner does everything, no one else 
    does anything'.  This set of tests looks at the basic functioning of the 
    permissions system and in particular 'check_permission'.
    """

    def setUp(self):
        self.rc = ResourceClient(actor="shauna")
        self.prc = PermissionResourceClient(actor="shauna")

    def test_permissions_system(self):
        # Here we create a resource, add a permissions resource to it, and 
        # add a specific permission for a non-owner actor.
        resource = self.rc.create_resource(name="Aha")
        pr = self.prc.create_permission_resource(permitted_object=resource)
        self.prc.set_target(target=pr)
        action_pk, permission = self.prc.add_permission(permission_type="resource_additem",
            permission_actor="buffy")
        self.assertEquals(pr.get_items(), ['Permission 1 (resource_additem for buffy)'])
        # Now let's have Buffy do a thing on the resource
        brc = ResourceClient(actor="buffy", target=resource)
        action_pk, item = brc.add_item(item_name="Test New")
        self.assertEquals(item.name, "Test New")

    def test_recursive_permission(self):
        """
        Tests setting permissions on permission.
        """

        # First we have Shauna create a resource and a PR for the resource
        resource = self.rc.create_resource(name="Aha")
        pr = self.prc.create_permission_resource(permitted_object=resource)
        
        # With no recursive PR, Buffy can't make a change to the top level PR, 
        # because she's not the owner.
        bprc = PermissionResourceClient(actor="buffy", target=pr)
        action_pk, permission = bprc.add_permission(
            permission_type="permissionresource_addpermission",
            permission_actor="willow")
        self.assertEquals(pr.get_items(), [])
        self.assertEquals(Action.objects.get(pk=action_pk).status, "rejected")
        
        # So Shauna creates a PR for her PR, and adds a permission for Buffy on it
        recursive_pr = self.prc.create_permission_resource(permitted_object=pr)
        self.prc.set_target(target=recursive_pr)
        action_pk, rec_permission = self.prc.add_permission(
            permission_type="permissionresource_addpermission",
            permission_actor="buffy")
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")

        # Now Buffy should be able to make a change to the top level PR
        action_pk, permission = bprc.add_permission(permission_type="permissionresource_addpermission",
            permission_actor="willow")        
        self.assertEquals(pr.get_items(), ['Permission 2 (permissionresource_addpermission for willow)'])
        self.assertEquals(Action.objects.get(pk=action_pk).status, "implemented")


class ConditionalsTest(TestCase):

    def setUp(self):
        self.cc = ConditionalClient(actor="shauna")
        self.rc = ResourceClient(actor="shauna")
        self.prc = PermissionResourceClient(actor="shauna")

    def test_create_vote_conditional(self):
        default_vote = self.cc.createVoteCondition(action=1)
        self.assertEquals(default_vote.publicize_votes(), False)
        public_vote = self.cc.createVoteCondition(publicize_votes=True, action=1)
        self.assertEquals(public_vote.publicize_votes(), True)

    def test_add_vote_to_vote_conditional(self):
        default_vote = self.cc.createVoteCondition(action=1)
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
        default_vote = self.cc.createVoteCondition(action=1)

        # TODO: this is hacky, esp the default_vote.target and then setting target
        pr = self.prc.create_permission_resource(permitted_object=default_vote.target)
        self.prc.set_target(target=pr)  # need to refactor pr & r clients to return new client with target pre-set

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

        # First we have Shauna create a resource and a PR for the resource
        resource = self.rc.create_resource(name="Aha")
        pr = self.prc.create_permission_resource(permitted_object=resource)

        # Then she adds a permission that says that Buffy can add items.
        self.prc.set_target(target=pr)
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

        # First we have Shauna create a resource and a PR for the resource
        resource = self.rc.create_resource(name="Aha")
        pr = self.prc.create_permission_resource(permitted_object=resource)

        # Then she adds a permission that says that Buffy can add items.
        self.prc.set_target(target=pr)
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

    def test_add_pr_to_community_owned_resource_allowing_nongovernor_to_change_name(self):
        # SetUp
        community = self.commClient.create_community(name="A New Community")
        rc = ResourceClient(actor="shauna")
        resource = rc.create_resource(name="A New Resource")
        rc.set_target(target=resource)
        action_pk, result = rc.change_owner_of_target(new_owner="A New Community", new_owner_type="com")
        self.assertEquals(resource.get_owner(), "A New Community")
        # Add PR with permission for nongovernor to change name
        prc = PermissionResourceClient(actor="shauna")
        pr = prc.create_permission_resource(permitted_object=resource)
        prc.set_target(pr)
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

class ConditionalCommunityTest(TestCase):

    def setUp(self):
        self.commClient = CommunityClient(actor="shauna")
        self.community = self.commClient.create_community(name="A New Community")

    def test_with_conditional_on_governer_decision_making(self):
        # Set conditional on governor decision making

        # Now when governor changes name of community, they must meet condition.
        # Maybe a time elapse condition of .5 seconds?  Or maybe have multiple
        # governors.

    def test_change_governors_without_conditional_on_change(self):
        pass

    def test_change_governors_with_conditional_on_change(self):
        pass