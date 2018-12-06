from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

from actions.permissions import has_permission
from actions.state_changes import create_change_object



ACTION_STATUS_CHOICES = (
    ('draft', 'Drafted'),
    ('sent', 'Sent, awaiting approval'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
    ('withdrawn', 'Withdrawn'),
    ('implemented', 'Implemented'),
)

class Action(models.Model):

    # Related fields
    actor = models.CharField(max_length=50)  # Replace with link to user/account
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    target = GenericForeignKey()

    # Information related to the change we want to make, possibly replace this with
    # custom field, although that might not work with invalid draft data.
    change_type = models.CharField(max_length=50, blank=True)
    change_data = models.CharField(max_length=500, blank=True) 

    # Regular old attributes
    status = models.CharField(max_length=5, choices=ACTION_STATUS_CHOICES, 
        default='draft')

    # Basics

    def __str__(self):
        return "%s action %s by %s on %s " % (self.status, self.change_type, self.actor, 
            self.target)

    # Steps of action execution

    def validate_action(self):
        """Checks that action is valid by providing actor and target to the change
        itself, which implements its own custom logic."""
        if self.change.validate(actor=self.actor, target=self.target):
            self.status = "sent"
            self.save()
    
    def check_permissions(self):
        """Checks that action is permissable."""
        self.status = has_permission(action=self)
        self.save()

    def implement_action(self):
        """Lets the change object carry out its custom implementation using the
        actor and target."""
        result = self.change.implement(actor=self.actor, target=self.target)
        self.status = "implemented"
        self.save()
        return result

    def take_action(self):
        """Checks status and attempts next step given that status."""
        # hack for now, create change from change_type and change_data
        self.change = create_change_object(self.change_type, self.change_data)

        current_result = None 

        # now go through steps
        if self.status == "draft":
            current_result = self.validate_action()
        if self.status in ["sent", "waiting"]:
            current_result = self.check_permissions()
        if self.status == "approved":
            current_result = self.implement_action()
        
        return self.pk, current_result


# Helper method until we can call Action directly using change field
def create_action(change, target, actor):
    return Action.objects.create(actor=actor, target=target, 
        change_type=change.get_change_type(), change_data=change.get_change_data())
    

OWNER_CHOICES = (
    ('ind', 'Individually Owned'),
    ('com', 'Community Owned'),
)

class PermissionedModel(models.Model):

    owner = models.CharField(max_length=200)
    owner_type = models.CharField(max_length=3, choices=OWNER_CHOICES, 
        default='ind')
    
    # Permission-related fields
    foundational_permission_enabled = models.BooleanField(default=False)
    governing_permission_enabled = models.BooleanField(default=True)

    class Meta:
        abstract = True

    def get_owner(self):
        return self.owner

    def get_unique_id(self):
        # App name + model name + pk
        contentType = ContentType.objects.get_for_model(self)
        return "_".join([contentType.app_label, contentType.model, str(self.pk)])

    # TODO: add a method that overrides save and checks whether it's 
    # called from a BaseStateChange object.
