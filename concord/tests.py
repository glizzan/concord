from django.test import TestCase

from resources.client import ResourceClient
from permission_resources.client import PermissionResourceClient

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
        item = self.rc.add_item(item_name="Aha")
        self.assertEquals(item.get_unique_id(), "resources_item_1")

    def test_remove_item_from_resource(self):
        """
        Test removal of item from resource.
        """
        resource = self.rc.create_resource(name="Aha")
        self.rc.set_target(target=resource)
        item = self.rc.add_item(item_name="Aha")
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
        self.assertEquals(pr.get_unique_id(), "permissionresources_permissionsresource_1")

    def test_add_permission_to_resource(self):
        """
        Test addition of permisssion to resource.
        """
        resource = self.rc.create_resource(name="Aha")
        pr = self.prc.create_permission_resource(permitted_object=resource)
        self.prc.set_target(target=pr)
        permission = self.prc.add_permission(permission_type="permissions_resource_additem",
            permission_actor="shauna")
        self.assertEquals(pr.get_items(), ['Permission 1 (permissions_resource_additem for shauna)'])

    def test_remove_permission_from_resource(self):
        """
        Test removal of permission from resource.
        """
        resource = self.rc.create_resource(name="Aha")
        pr = self.prc.create_permission_resource(permitted_object=resource)
        self.prc.set_target(target=pr)
        permission = self.prc.add_permission(permission_type="permissions_resource_additem",
            permission_actor="shauna")
        self.assertEquals(pr.get_items(), ['Permission 1 (permissions_resource_additem for shauna)'])
        self.prc.remove_permission(item_pk=permission.pk)
        self.assertEquals(pr.get_items(), [])


class PermissionSystemTest(TestCase):
    """
    The previous two sets of tests use the default permissions setting for the items
    they're modifying.  (Default permissions = 'creator does everything, no one else 
    does anything'.  This set of tests looks at the basic functioning of the 
    permissions system and in particular 'check_permission'.
    """

    def setUp(self):
        self.rc = ResourceClient(actor="shauna")
        self.prc = PermissionResourceClient(actor="shauna")

    def test_permissions_system(self):
        # Here we create a resource, add a permissions resource to it, and 
        # add a specific permission for a non-creator actor.
        resource = self.rc.create_resource(name="Aha")
        pr = self.prc.create_permission_resource(permitted_object=resource)
        self.prc.set_target(target=pr)
        permission = self.prc.add_permission(permission_type="resource_additem",
            permission_actor="buffy")
        self.assertEquals(pr.get_items(), ['Permission 1 (resource_additem for buffy)'])
        # Now let's have Buffy do a thing on the resource
        brc = ResourceClient(actor="buffy", target=resource)
        item = brc.add_item(item_name="Test New")
        self.assertEquals(item.name, "Test New")

    def test_recursive_permission(self):
        """
        Tests setting permissions on permission.
        """

        # First we have Shauna create a resource and a PR for the resource
        resource = self.rc.create_resource(name="Aha")
        pr = self.prc.create_permission_resource(permitted_object=resource)
        
        # With no recursive PR, Buffy can't make a change to the top level PR, 
        # because she's not the creator.
        bprc = PermissionResourceClient(actor="buffy", target=pr)
        item = bprc.add_permission(permission_type="permissionresource_addpermission",
            permission_actor="willow")
        self.assertEquals(pr.get_items(), [])       
        
        # So Shauna creates a PR for her PR, and adds a permission for Buffy on it
        recursive_pr = self.prc.create_permission_resource(permitted_object=pr)
        self.prc.set_target(target=recursive_pr)
        rec_permission = self.prc.add_permission(permission_type="permissionresource_addpermission",
            permission_actor="buffy")

        # Now Buffy should be able to make a change to the top level PR
        item = bprc.add_permission(permission_type="permissionresource_addpermission",
            permission_actor="willow")        
        self.assertEquals(pr.get_items(), ['Permission 2 (permissionresource_addpermission for willow)'])
        
        # While we're here let's just check that the actions are correct
        from actions.models import Action
        actions = Action.objects.all()
        self.assertEquals(actions[0].status, "rejected")
        self.assertEquals(actions[1].status, "implemented")
        self.assertEquals(actions[2].status, "implemented")

