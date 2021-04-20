"""Resource State Changes"""

import logging

from django.core.exceptions import ValidationError
from concord.resources.models import Comment, SimpleList, Document
from concord.actions.state_changes import BaseStateChange
from concord.utils import field_utils


logger = logging.getLogger(__name__)


#############################
### Comment State Changes ###
#############################


class AddCommentStateChange(BaseStateChange):
    """State Change to add a comment."""

    descriptive_text = {
        "verb": "add",
        "default_string": "comment"
    }

    section = "Comment"
    model_based_validation = (Comment, ["text"])
    context_keys = ["commented_object"]
    linked_filters = ["TargetTypeFilter", "CreatorOfCommentedFilter"]

    # Fields
    text = field_utils.CharField(label="Comment text", required=True)

    @classmethod
    def get_context_instances(cls, action):
        """Returns the commented object by its model name, to handle cases where the referer knows the model type
        vs doesn't know the model type."""
        commented_object = action.target
        model_name = commented_object.__class__.__name__.lower()
        return {"commented_object": commented_object, model_name: commented_object}

    def implement(self, actor, target, **kwargs):

        comment = Comment(text=self.text, commentor=actor)
        comment.commented_object = target
        comment.owner = target.get_owner()
        comment.save()

        self.set_default_permissions(actor, comment)

        return comment


class EditCommentStateChange(BaseStateChange):
    """State Change to edit a comment."""

    descriptive_text = {
        "verb": "edit",
        "default_string": "comment"
    }

    section = "Comment"
    context_keys = ["comment", "commented_object"]
    model_based_validation = (Comment, ["text"])
    linked_filters = ["CommenterFilter", "CreatorOfCommentedFilter"]
    allowable_targets = [Comment]
    settable_classes = ["all_models"]

    # Fields
    text = field_utils.CharField(label="Comment text", required=True)

    @classmethod
    def get_context_instances(cls, action):
        """Returns the comment and the commented object. Also returns the commented object by its model
        name, to handle cases where the referer knows the model type vs doesn't know the model type."""
        comment = action.target
        commented_object = action.target.commented_object
        model_name = commented_object.__class__.__name__.lower()
        return {"comment": comment, "commented_object": commented_object, model_name: commented_object}

    def implement(self, actor, target, **kwargs):
        target.text = self.text
        target.save()
        return target


class DeleteCommentStateChange(BaseStateChange):
    """State Change to delete a comment."""

    descriptive_text = {
        "verb": "delete",
        "default_string": "comment"
    }

    section = "Comment"
    context_keys = ["comment", "commented_object"]
    linked_filters = ["CommenterFilter", "CreatorOfCommentedFilter"]
    allowable_targets = [Comment]
    settable_classes = ["all_models"]

    @classmethod
    def get_context_instances(cls, action):
        """Returns the comment and the commented object. Also returns the commented object by its model
        name, to handle cases where the referer knows the model type vs doesn't know the model type."""
        comment = action.target
        commented_object = action.target.commented_object
        model_name = commented_object.__class__.__name__.lower()
        return {"comment": comment, "commented_object": commented_object, model_name: commented_object}

    def implement(self, actor, target, **kwargs):
        from concord.permission_resources.utils import delete_permissions_on_target
        pk = target.pk
        delete_permissions_on_target(target)
        target.delete()
        return pk


################################
### SimpleList State Changes ###
################################


class AddListStateChange(BaseStateChange):
    """State Change to create a list in a community (or other target)."""

    descriptive_text = {
        "verb": "add",
        "default_string": "list",
        "detail_string": "list with {name}"
    }

    section = "List"
    model_based_validation = (SimpleList, ["name", "description"])
    allowable_targets = ["all_community_models"]

    # Fields
    name = field_utils.CharField(label="Name", required=True)
    configuration = field_utils.DictField(label="Configuration", required=True)
    description = field_utils.CharField(label="Description")

    def validate(self, actor, target):
        if not super().validate(actor=actor, target=target):
            return False
        try:
            SimpleList().validate_configuration(self.configuration)
            return True
        except ValidationError as error:
            self.set_validation_error(message=error.message)
            return False

    def implement(self, actor, target, **kwargs):
        simple_list = SimpleList(name=self.name, description=self.description, owner=target.get_owner(), creator=actor)
        simple_list.set_row_configuration(self.configuration)
        simple_list.save()
        self.set_default_permissions(actor, simple_list)
        return simple_list


class EditListStateChange(BaseStateChange):
    """State Change to edit an existing list."""

    descriptive_text = {
        "verb": "edit",
        "default_string": "list",
        "detail_string": "list to have name '{name}' and description '{description}'"
    }

    section = "List"
    model_based_validation = ("target", ["name", "description"])
    allowable_targets = [SimpleList]
    settable_classes = ["all_community_models", SimpleList]

    # Fields
    name = field_utils.CharField(label="Name")
    configuration = field_utils.DictField(label="Configuration")
    description = field_utils.CharField(label="Description")

    def validate(self, actor, target):
        if not super().validate(actor=actor, target=target):
            return False
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

    def implement(self, actor, target, **kwargs):
        target.name = self.name if self.name else target.name
        target.description = self.description if self.description else target.description
        if self.configuration:
            target.set_row_configuration(self.configuration)
        target.save()
        return target


class DeleteListStateChange(BaseStateChange):
    """State Change to delete an existing list."""

    descriptive_text = {
        "verb": "delete",
        "default_string": "list"
    }

    section = "List"
    allowable_targets = [SimpleList]
    settable_classes = ["all_community_models", SimpleList]

    def implement(self, actor, target, **kwargs):
        pk = target.pk
        target.delete()
        return pk


class AddRowStateChange(BaseStateChange):
    """State Change to add a row to a list."""

    descriptive_text = {
        "verb": "add",
        "default_string": "row to list",
        "detail_string": "row with content {row_content} to list"
    }

    section = "List"
    allowable_targets = [SimpleList]
    settable_classes = ["all_community_models", SimpleList]

    # Fields
    row_content = field_utils.CharField(label="Content of row", required=True)
    index = field_utils.IntegerField(label="Index of row")

    def validate(self, actor, target):
        if not super().validate(actor=actor, target=target):
            return False
        try:
            target.check_row_against_configuration(self.row_content)
        except ValidationError as error:
            self.set_validation_error(message=error.message)
            return False
        if self.index and not isinstance(self.index, int):
            self.set_validation_error(message="Index must be an integer.")
            return False
        return True

    def implement(self, actor, target, **kwargs):
        target.add_row(self.row_content, self.index)
        target.save()
        return target


class EditRowStateChange(BaseStateChange):
    """State Change to edit a row in a list."""

    descriptive_text = {
        "verb": "edit",
        "default_string": "row in list",
        "detail_string": "row with index {index} to have new content {row_content}"
    }

    section = "List"
    allowable_targets = [SimpleList]
    settable_classes = ["all_community_models", SimpleList]

    row_content = field_utils.CharField(label="Content of row", required=True)
    index = field_utils.IntegerField(label="Index of row", required=True)

    def validate(self, actor, target):
        if not super().validate(actor=actor, target=target):
            return False
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

    def implement(self, actor, target, **kwargs):
        target.edit_row(self.row_content, self.index)
        target.save()
        return target


class MoveRowStateChange(BaseStateChange):
    """State Change to move a row in a list."""

    descriptive_text = {
        "verb": "move",
        "default_string": "row in list",
        "detail_string": "row with current index {old_index} to new index {new_index}"
    }

    section = "List"
    allowable_targets = [SimpleList]
    settable_classes = ["all_community_models", SimpleList]

    # Fields
    old_index = field_utils.IntegerField(label="Old index of row", required=True)
    new_index = field_utils.IntegerField(label="New index of row", required=True)

    def validate(self, actor, target):

        if not super().validate(actor=actor, target=target):
            return False

        if not isinstance(self.old_index, int):
            self.set_validation_error(message="Current index must be an integer.")
            return False

        if not isinstance(self.new_index, int):
            self.set_validation_error(message="New index must be an integer.")
            return False

        if not 0 <= self.old_index < len(target.get_rows()):
            message = f"Current index must be within 0 and {len(target.get_rows())} not {self.old_index}"
            self.set_validation_error(message=message)
            return False

        if not 0 <= self.new_index < len(target.get_rows()):
            message = f"New index must be within 0 and {len(target.get_rows())} not {self.new_index}"
            self.set_validation_error(message=message)
            return False

        return True

    def implement(self, actor, target, **kwargs):
        target.move_row(self.old_index, self.new_index)
        target.save()
        return target


class DeleteRowStateChange(BaseStateChange):
    """State Change to delete a row in a list."""

    descriptive_text = {
        "verb": "delete",
        "default_string": "row in list",
        "detail_string": "row with index {index}"
    }

    section = "List"
    allowable_targets = [SimpleList]
    settable_classes = ["all_community_models", SimpleList]

    # Fields
    index = field_utils.IntegerField(label="Index of row to delete", required=True)

    def validate(self, actor, target):
        if not super().validate(actor=actor, target=target):
            return False
        if not isinstance(self.index, int):
            self.set_validation_error(message="Index must be an integer.")
            return False
        if not 0 <= self.index < len(target.get_rows()):
            self.set_validation_error(message=f"Index must be within 0 and {len(target.get_rows())} not {self.index}")
            return False
        return True

    def implement(self, actor, target, **kwargs):
        target.delete_row(int(self.index))
        target.save()
        return target


##############################
### Document State Changes ###
##############################


class CreateDocumentStateChange(BaseStateChange):

    descriptive_text = {
        "verb": "add",
        "default_string": "document",
        "detail_string": "document with {name}"
    }

    section = "Document"
    model_based_validation = (Document, ["name", "description", "content"])
    allowable_targets = ["all_community_models"]

    # Fields
    name = field_utils.CharField(label="Name", required=True)
    description = field_utils.CharField(label="Description")
    content = field_utils.CharField(label="Content")

    def implement(self, actor, target, **kwargs):
        doc = Document(name=self.name, owner=target.get_owner(), creator=actor)
        doc.description = self.description if self.description else doc.description
        doc.content = self.content if self.content else doc.content
        doc.save()
        self.set_default_permissions(actor, doc)
        return doc


class EditDocumentStateChange(BaseStateChange):

    descriptive_text = {
        "verb": "edit",
        "default_string": "document"
    }

    section = "Document"
    model_based_validation = (Document, ["name", "description", "content"])
    allowable_targets = [Document]
    settable_classes = ["all_community_models", Document]

    # Fields
    name = field_utils.CharField(label="Name")
    description = field_utils.CharField(label="Description")
    content = field_utils.CharField(label="Content")

    def validate(self, actor, target):
        if not super().validate(actor=actor, target=target):
            return False
        if not self.name and not self.description and not self.content:
            self.set_validation_error(message="Must edit name, description or content")
            return False
        return True

    def implement(self, actor, target, **kwargs):
        target.name = self.name if self.name else target.name
        target.description = self.description if self.description else target.description
        target.content = self.content if self.content else target.content
        target.save()
        return target


class DeleteDocumentStateChange(BaseStateChange):

    descriptive_text = {
        "verb": "delete",
        "default_string": "document"
    }

    section = "Document"
    allowable_targets = [Document]
    settable_classes = ["all_community_models", Document]

    def implement(self, actor, target, **kwargs):
        pk = target.pk
        target.delete()
        return pk
