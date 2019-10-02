import inspect, importlib
from typing import List, Tuple

from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import User

from concord.actions.state_changes import create_change_object
from concord.actions.customfields import ResolutionField, Resolution


ACTION_STATUS_CHOICES = (
    ('draft', 'Drafted'),
    ('sent', 'Sent, awaiting approval'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
    ('withdrawn', 'Withdrawn'),
    ('implemented', 'Implemented'),
)

def get_default_resolution():
    return Resolution(status="draft")

class Action(models.Model):

    # Related fields
    actor = models.ForeignKey(User, on_delete=models.CASCADE)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    target = GenericForeignKey()

    # Information related to the change we want to make, possibly replace this with
    # custom field, although that might not work with invalid draft data.
    change_type = models.CharField(max_length=50, blank=True)
    change_data = models.CharField(max_length=500, blank=True) 

    # Log field, helps with debugging and possibly useful for end user
    resolution = ResolutionField(default=get_default_resolution)
    log = models.CharField(max_length=500, blank=True)

    # Regular old attributes
    status = models.CharField(max_length=5, choices=ACTION_STATUS_CHOICES, 
        default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Basics

    def __str__(self):
        return "%s action %s by %s on %s " % (self.status, self.change_type, self.actor, 
            self.target)

    def get_description(self):
        self.change = create_change_object(self.change_type, self.change_data)
        if self.status == "implemented":
            if hasattr(self.change,"description_past_tense"):
                return self.actor + " " + self.change.description_past_tense() + " on target " + self.target.get_name()
        else:
            if hasattr(self.change, "description_present_tense"):
                return self.actor + " asked to " + self.change.description_present_tense() + " on target " + self.target.get_name()
        return self.__str__()

    def get_targetless_description(self):
        self.change = create_change_object(self.change_type, self.change_data)
        if self.status == "implemented":
            if hasattr(self.change,"description_past_tense"):
                return self.actor + " " + self.change.description_past_tense()
        else:
            if hasattr(self.change, "description_present_tense"):
                return self.actor + " asked to " + self.change.description_present_tense()
        return self.__str__() 

    def get_condition(self):
        from concord.conditionals.client import PermissionConditionalClient
        pcc = PermissionConditionalClient(system=True)
        return pcc.get_condition_item_given_action(action_pk=self.pk) 

    def get_condition_link(self):
        '''Returns link to condition formatted as display, or None.'''
        condition = self.get_condition()
        if condition:
            return "<a href='%s'>%s</a>" % (condition.get_url(), condition.get_display_string())
        return ""

    # Steps of action execution

    def validate_action(self):
        """Checks that action is valid by providing actor and target to the change
        itself, which implements its own custom logic."""
        if self.change.validate(actor=self.actor, target=self.target):
            self.status = "sent"
        # TODO: handle invalid actions
    
    def approve_action(self, resolved_through, log=None, condition=None, role=None):
        self.log = log if log else ""
        self.status = "approved"
        self.resolution.status = "approved"
        self.resolution.is_resolved = True
        self.resolution.is_approved = True
        self.resolution.resolved_through = resolved_through
        self.resolution.condition = condition
        self.resolution.role = role

    def reject_action(self, resolved_through=None, log=None, condition=None, role=None):
        self.log = log if log else ""
        self.status = "rejected"
        self.resolution.status = "rejected"
        self.resolution.is_resolved = True
        self.resolution.is_approved = False
        self.resolution.resolved_through = resolved_through
        self.resolution.condition = condition
        self.resolution.role = role

    def implement_action(self):
        """Lets the change object carry out its custom implementation using the
        actor and target."""
        result = self.change.implement(actor=self.actor, target=self.target)
        self.status = "implemented"
        return result

    def take_action(self):
        """Checks status and attempts next step given that status."""
        # hack for now, create change from change_type and change_data
        self.change = create_change_object(self.change_type, self.change_data)

        current_result = None 

        # now go through steps
        if self.status == "draft":
            self.validate_action()
        if self.status in ["sent", "waiting"]:
            from concord.actions.permissions import has_permission
            self = has_permission(action=self)
        if self.status == "approved":
            current_result = self.implement_action()

        self.save()  # Save action, may not always be needed

        return self, current_result


# Helper method until we can call Action directly using change field
def create_action(change, target, actor):
    return Action.objects.create(actor=actor, target=target, 
        change_type=change.get_change_type(), change_data=change.get_change_data())
    

OWNER_CHOICES = (
    ('ind', 'Individually Owned'),
    ('com', 'Community Owned'),
)

class PermissionedModel(models.Model):

    owner_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_owned_objects")
    owner_object_id = models.PositiveIntegerField()
    owner = GenericForeignKey('owner_content_type', 'owner_object_id')
    # FIXME: should be able to delete this and just check content_type when determining ownership
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

    def get_actions(self):
        from concord.actions.client import ActionClient
        client = ActionClient(system=True, target=self)
        return client.get_action_history_given_target(target=self)

    @classmethod
    def get_state_change_objects(cls):
        # Get list of all objects in model's app's state_changes file 
        relative_import = "." + cls._meta.app_label + ".state_changes"
        state_changes_module = importlib.import_module(relative_import, package="concord")
        return inspect.getmembers(state_changes_module) 

    def save(self, *args, **kwargs):
        '''
        A permissioned model's save method can *only* be invoked by a 
        descendant of BaseStateChange, on update (create is fine).

        For now, we inspect who is calling us.  This is a hack.  Once we
        have better testing, we will enforce this via tests.
        '''
        if not self.pk:  # Don't need to check for newly created objects
            return super().save(*args, **kwargs)  # Call the "real" save() method.
        import inspect
        curframe = inspect.currentframe()
        caller = inspect.getouterframes(curframe, 5)
        calling_function_name = caller[1].function
        if calling_function_name == "implement":
            del curframe, caller
            return super().save(*args, **kwargs)  # Call the "real" save() method.
        # Hack to accomodate overriding save on subclasses
        if calling_function_name == "save":
            calling_function_name = caller[2].function
            if calling_function_name == "implement":
                del curframe, caller
                return super().save(*args, **kwargs)  # Call the "real" save() method.
        raise BaseException("Save called incorrectly")