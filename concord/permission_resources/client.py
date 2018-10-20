from django.contrib.contenttypes.models import ContentType

from actions.clients import BaseActionClient

from permission_resources.models import PermissionsResource
from permission_resources import state_changes as sc


################################
### PermissionResourceClient ###
################################


class PermissionResourceClient(BaseActionClient):

    # Read only

    def get_permitted_object_helper(self, permitted_object):
        object_id = permitted_object.pk
        content_type = ContentType.objects.get_for_model(permitted_object)
        return PermissionsResource.objects.filter(content_type__pk=content_type.pk,
            object_id=object_id)

    def get_permission_resource(self, permitted_object):
        result = self.get_permitted_object_helper(permitted_object)
        if result:
            return result.first()
        return None

    def get_permissions_for_target(self, target):
        pr = PermissionsResource.objects.get(permitted_object=target)
        return pr.permissionitem_set.all()

    # Create only

    def create_permission_resource(self, permitted_object):
        return PermissionsResource.objects.create(permitted_object=permitted_object)

    # State changes

    def add_permission(self, permission_type, permission_actor, target=None):
        change = sc.AddPermissionStateChange(permission_type=permission_type,
            permission_actor=permission_actor)
        return self.create_and_take_action(change, target)

    def remove_permission(self, item_pk, target=None):
        change = sc.RemovePermissionStateChange(item_pk=item_pk)
        return self.create_and_take_action(change, target)


