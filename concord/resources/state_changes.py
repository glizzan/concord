"""Resource State Changes"""

import logging

from django.core.exceptions import ObjectDoesNotExist, ValidationError

from concord.actions.state_changes import BaseStateChange
from concord.resources.models import Resource, Item, Comment, SimpleList
from concord.permission_resources.utils import delete_permissions_on_target


logger = logging.getLogger(__name__)


#############################
### Comment State Changes ###
#############################


class AddCommentStateChange(BaseStateChange):
    """State Change to add a comment."""
    description = "Add comment"
    input_fields = ["text"]
    input_target = Comment

    def __init__(self, text):
        self.text = text

    def description_present_tense(self):
        return "add comment"

    def description_past_tense(self):
        return "added comment"

    def implement(self, actor, target):

        comment = Comment(text=self.text, commentor=actor)
        comment.commented_object = target
        comment.owner = target.get_owner()

        comment.save()
        return comment


class EditCommentStateChange(BaseStateChange):
    """State Change to edit a comment."""
    description = "Edit comment"
    input_fields = ["text"]

    def __init__(self, text):
        self.text = text

    @classmethod
    def get_allowable_targets(cls):
        return [Comment]

    @classmethod
    def get_settable_classes(cls):
        """Comments may be made on any target - it's up to the front end to decide what comment functionality to
        expose to the user."""
        return cls.get_all_possible_targets()

    def description_present_tense(self):
        return "edit comment"

    def description_past_tense(self):
        return "edited comment"

    def implement(self, actor, target):
        target.text = self.text
        target.save()
        return target


class DeleteCommentStateChange(BaseStateChange):
    """State Change to delete a comment."""
    description = "Delete comment"

    @classmethod
    def get_allowable_targets(cls):
        return [Comment]

    @classmethod
    def get_settable_classes(cls):
        """Comments may be made on any target - it's up to the front end to decide what comment functionality to
        expose to the user."""
        return cls.get_all_possible_targets()

    def description_present_tense(self):
        return "delete comment"

    def description_past_tense(self):
        return "deleted comment"

    def implement(self, actor, target):
        pk = target.pk
        delete_permissions_on_target(target)
        target.delete()
        return pk


#####################################
### Resource & Item State Changes ###
#####################################

class ChangeResourceNameStateChange(BaseStateChange):
    """State Change to change a resource name."""
    description = "Change name of resource"
    preposition = "for"
    input_fields = ["name"]

    def __init__(self, name):
        self.name = name

    @classmethod
    def get_allowable_targets(cls):
        return [Resource, Item]

    @classmethod
    def get_settable_classes(cls):
        return cls.get_all_possible_targets()

    def description_present_tense(self):
        return f"change name of resource to {self.name}"

    def description_past_tense(self):
        return f"changed name of resource to {self.name}"

    def implement(self, actor, target):
        target.name = self.name
        target.save()
        return target


class AddItemStateChange(BaseStateChange):
    """State Change to add item to a resource."""
    description = "Add item to resource"
    input_fields = ["name"]
    input_target = Item

    def __init__(self, name):
        self.name = name

    @classmethod
    def get_allowable_targets(cls):
        return [Resource]

    @classmethod
    def get_settable_classes(cls):
        """An AddItem permission can be set on an item, a resource, or on the community that owns the
        item or resource."""
        return [Resource] + cls.get_community_models()

    def description_present_tense(self):
        return f"add item {self.name}"

    def description_past_tense(self):
        return f"added item {self.name}"

    def implement(self, actor, target):
        item = Item.objects.create(name=self.name, resource=target, owner=actor.default_community)
        return item


class RemoveItemStateChange(BaseStateChange):
    """State Change to remove item from a resource."""
    description = "Remove item from resource"
    preposition = "from"

    @classmethod
    def get_allowable_targets(cls):
        return [Item]

    @classmethod
    def get_settable_classes(cls):
        return [Resource, Item] + cls.get_community_models()

    def description_present_tense(self):
        return "remove item"

    def description_past_tense(self):
        return "removed item"

    def implement(self, actor, target):
        try:
            delete_permissions_on_target(target)
            target.delete()
            return True
        except ObjectDoesNotExist as exception:
            logger.warning(exception)
            return False


################################
### SimpleList State Changes ###
################################


class AddListStateChange(BaseStateChange):
    """State Change to create a list in a community (or other target)."""
    description = "Add list"
    input_fields = ["name", "description"]
    input_target = SimpleList

    def __init__(self, name, configuration, description=None):
        self.name = name
        self.configuration = configuration
        self.description = description if description else ""

    @classmethod
    def get_allowable_targets(cls):
        return cls.get_community_models()

    def description_present_tense(self):
        return f"add list with name {self.name}"

    def description_past_tense(self):
        return f"added list with name {self.name}"

    def validate(self, actor, target):
        super().validate(actor=actor, target=target)
        try:
            SimpleList().validate_configuration(self.configuration)
            return True
        except ValidationError as error:
            self.set_validation_error(message=error.message)
            return False

    def implement(self, actor, target):
        simple_list = SimpleList(name=self.name, description=self.description, owner=target.get_owner())
        simple_list.set_row_configuration(self.configuration)
        simple_list.save()
        return simple_list


class EditListStateChange(BaseStateChange):
    """State Change to edit an existing list."""
    description = "Edit list"
    input_fields = ["name", "description"]

    def __init__(self, name=None, configuration=None, description=None):
        self.name = name
        self.configuration = configuration
        self.description = description

    @classmethod
    def get_allowable_targets(self):
        return [SimpleList]

    @classmethod
    def get_settable_classes(cls):
        return cls.get_community_models() + [SimpleList]

    def description_present_tense(self):
        return f"edit list with new name {self.name} and new description {self.description}"

    def description_past_tense(self):
        return f"edited list with new name {self.name} and new description {self.description}"

    def validate(self, actor, target):
        super().validate(actor=actor, target=target)
        if not self.name and not self.description and not self.configuration:
            self.set_validation_error(message="Must supply new name, description, or configuration when editing List.")
            return False
        if self.configuration:
            try:
                target.validate_configuration(self.configuration)
                target.adjust_rows_to_new_configuration(self.configuration)
                return True
            except ValidationError as error:
                self.set_validation_error(message=error.message)
                return False
        return True

    def implement(self, actor, target):
        target.name = self.name if self.name else target.name
        target.description = self.description if self.description else target.description
        if self.configuration:
            target.set_row_configuration(self.configuration)
        target.save()
        return target


class DeleteListStateChange(BaseStateChange):
    """State Change to delete an existing list."""
    description = "Delete list"

    @classmethod
    def get_allowable_targets(cls):
        return [SimpleList]

    @classmethod
    def get_settable_classes(cls):
        return cls.get_community_models() + [SimpleList]

    def description_present_tense(self):
        return "delete list"

    def description_past_tense(self):
        return "deleted list"

    def implement(self, actor, target):
        pk = target.pk
        target.delete()
        return pk


class AddRowStateChange(BaseStateChange):
    """State Change to add a row to a list."""
    description = "Add row to list"

    def __init__(self, row_content, index=None):
        self.row_content = row_content
        self.index = index

    @classmethod
    def get_allowable_targets(cls):
        return [SimpleList]

    @classmethod
    def get_settable_classes(cls):
        return cls.get_community_models() + [SimpleList]

    def description_present_tense(self):
        return f"add row with content {self.row_content}"

    def description_past_tense(self):
        return f"added row with content {self.row_content}"

    def validate(self, actor, target):
        super().validate(actor=actor, target=target)
        try:
            target.check_row_against_configuration(self.row_content)
        except ValidationError as error:
            self.set_validation_error(message=error.message)
            return False
        if self.index and not isinstance(self.index, int):
            self.set_validation_error(message="Index must be an integer.")
            return False
        return True

    def implement(self, actor, target):
        target.add_row(self.row_content, self.index)
        target.save()
        return target


class EditRowStateChange(BaseStateChange):
    """State Change to edit a row in a list."""
    description = "Edit row in list"

    def __init__(self, row_content, index):
        self.row_content = row_content
        self.index = index

    @classmethod
    def get_allowable_targets(cls):
        return [SimpleList]

    @classmethod
    def get_settable_classes(cls):
        return cls.get_community_models() + [SimpleList]

    def description_present_tense(self):
        return f"edit row with index {self.index} to have new content {self.row_content}"

    def description_past_tense(self):
        return f"edited row with index {self.index} to have new content {self.row_content}"

    def validate(self, actor, target):
        super().validate(actor=actor, target=target)
        try:
            target.check_row_against_configuration(self.row_content)
        except ValidationError as error:
            self.set_validation_error(message=error.message)
            return False
        if not isinstance(self.index, int):
            self.set_validation_error(message="Index must be an integer.")
            return False
        if not 0 <= self.index < len(target.get_rows()):
            self.set_validation_error(message=f"Index must be within 0 and {len(target.get_rows())} not {self.index}")
            return False
        return True

    def implement(self, actor, target):
        target.edit_row(self.row_content, self.index)
        target.save()
        return target


class DeleteRowStateChange(BaseStateChange):
    """State Change to delete a row in a list."""
    description = "Delete row in list"

    def __init__(self, index):
        self.index = index

    @classmethod
    def get_allowable_targets(cls):
        return [SimpleList]

    @classmethod
    def get_settable_classes(cls):
        return cls.get_community_models() + [SimpleList]

    def description_present_tense(self):
        return f"delete row with index {self.index}"

    def description_past_tense(self):
        return f"deleted row with index {self.index}"

    def validate(self, actor, target):
        super().validate(actor=actor, target=target)
        if not isinstance(self.index, int):
            self.set_validation_error(message="Index must be an integer.")
            return False
        if not 0 <= self.index < len(target.get_rows()):
            self.set_validation_error(message=f"Index must be within 0 and {len(target.get_rows())} not {self.index}")
            return False
        return True

    def implement(self, actor, target):
        target.delete_row(int(self.index))
        target.save()
        return target
