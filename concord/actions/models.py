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

    # Steps of action execution

    def validate_action(self):
        """Checks that action is valid by providing actor and target to the change
        itself, which implements its own custom logic."""
        if self.change.validate(actor=self.actor, target=self.target):
            self.status = "sent"
            self.save()
    
    def check_permissions(self):
        """Checks that action is permissable."""
        if has_permission(action=self):
            self.status = "approved"
        else:
            self.status = "rejected"
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

        # now go through steps
        if self.status == "draft":
            self.validate_action()
        if self.status == "sent":
            self.check_permissions()
        if self.status == "approved":
            return self.implement_action()


# Helper method until we can call Action directly using change field
def create_action(change, target, actor):
    return Action.objects.create(actor=actor, target=target, 
        change_type=change.get_change_type(), change_data=change.get_change_data())
    
