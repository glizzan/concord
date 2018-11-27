from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

from actions.models import PermissionedModel


# Create your models here.
class PermissionsResource(PermissionedModel):

    # For now just using inbuilt generic relation, but may want to switch???
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    permitted_object = GenericForeignKey('content_type', 'object_id')
    ignore_defaults = models.BooleanField(default=False)

    # Basics

    def get_name(self):
        return "Permissions resource for " + self.permitted_object.get_name()

    # Read-only

    def get_items(self):
        result = []
        for item in self.permissionsitem_set.all():
            result.append(item.get_name())
        return result


class PermissionsItem(PermissionedModel):

    actor = models.CharField(max_length=200)  # Replace with user model link
    action_type = models.CharField(max_length=200)  # Replace with choices field???
    resource = models.ForeignKey(PermissionsResource, on_delete=models.CASCADE)

    def get_name(self):
        return "Permission %s (%s for %s)" % (str(self.pk), self.action_type, self.actor)

    # Permissions-specific helpers

    def get_target(self):
        return self.resource.permitted_object

    def match_action_type(self, action_type):
        return self.action_type == action_type

    def match_actor(self, actor):
        return self.actor == actor
