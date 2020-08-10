from concord.actions.state_changes import BaseStateChange

from concord.resources.models import Item, Comment


#############################
### Comment State Changes ###
#############################


class AddCommentStateChange(BaseStateChange):
    description = "Add comment"

    def __init__(self, text):
        self.text = text

    @classmethod
    def get_settable_classes(cls):
        """Comments may be made on any target - it's up to the front end to decide what comment functionality to
        expose to the user."""
        return cls.get_all_possible_targets()

    def description_present_tense(self):
        return "add comment"  

    def description_past_tense(self):
        return "added comment"

    def validate(self, actor, target):
        """Checks that text is a string of at least one character long."""
        if self.text and type(self.text) == str and len(self.text) > 0:
            return True
        self.set_validation_error(message="Comment text must be a string at least one character long.")
        return False

    def implement(self, actor, target):

        comment = Comment(text=self.text, commentor=actor)
        comment.commented_object = target
        comment.owner = target.get_owner() # FIXME: should it be the target owner though?
        
        comment.save()
        return comment


class EditCommentStateChange(BaseStateChange):
    description = "Edit comment"

    def __init__(self, pk, text):
        self.pk = pk
        self.text = text

    @classmethod
    def get_settable_classes(cls):
        """Comments may be made on any target - it's up to the front end to decide what comment functionality to
        expose to the user."""
        return cls.get_all_possible_targets()

    def description_present_tense(self):
        return f"edit comment {self.pk}"  

    def description_past_tense(self):
        return f"edited comment {self.pk}" 

    def validate(self, actor, target):
        """Checks that text is a string of at least one character long."""
        if self.text and type(self.text) == str and len(self.text) > 0:
            return True
        self.set_validation_error(message="Comment text must be a string at least one character long.")
        return False

    def implement(self, actor, target):
        comment = Comment.objects.get(pk=self.pk)
        comment.text = self.text
        comment.save()
        return comment


class DeleteCommentStateChange(BaseStateChange):
    description = "Delete comment"

    def __init__(self, pk):
        self.pk = pk

    @classmethod
    def get_settable_classes(cls):
        """Comments may be made on any target - it's up to the front end to decide what comment functionality to
        expose to the user."""
        return cls.get_all_possible_targets()

    def description_present_tense(self):
        return f"delete comment {self.pk}"

    def description_past_tense(self):
        return f"deleted comment {self.pk}"

    def validate(self, actor, target):
        # TODO: real validation
        return True

    def implement(self, actor, target):
        comment = Comment.objects.get(pk=self.pk)
        comment.delete()
        return self.pk


#####################################
### Resource & Item State Changes ###
#####################################

class ChangeResourceNameStateChange(BaseStateChange):
    description = "Change name of resource"
    preposition = "for"

    def __init__(self, new_name):
        self.new_name = new_name

    @classmethod
    def get_settable_classes(cls):
        # FIXME: if we want to let people inherit from abstract resource, we need to check
        # parents here.
        from concord.resources.models import AbstractResource, AbstractItem, Resource, Item
        return [AbstractResource, AbstractItem, Resource, Item]    

    def description_present_tense(self):
        return "change name of resource to %s" % (self.new_name)  

    def description_past_tense(self):
        return "changed name of resource to %s" % (self.new_name) 

    def validate(self, actor, target):
        """
        put real logic here
        """
        return True

    def implement(self, actor, target):
        target.name = self.new_name
        target.save()
        return target


class AddItemStateChange(BaseStateChange):
    description = "Add item to resource"

    def __init__(self, item_name):
        self.item_name = item_name

    @classmethod
    def get_settable_classes(cls):
        """An AddItem permission can be set on an item, a resource, or on the community that owns the
        item or resource."""
        from concord.resources.models import Resource, Item
        return [Resource, Item] + cls.get_community_models()

    def description_present_tense(self):
        return "add item %s" % (self.item_name)  

    def description_past_tense(self):
        return "added item %s" % (self.item_name)

    def validate(self, actor, target):
        """
        put real logic here
        """
        if actor and target and self.item_name:
            return True
        return False

    def implement(self, actor, target):
        item = Item.objects.create(name=self.item_name, resource=target, 
                owner=actor.default_community)
        return item


class RemoveItemStateChange(BaseStateChange):
    description = "Remove item from resource"
    preposition = "from"

    def __init__(self, item_pk):
        self.item_pk = item_pk

    @classmethod
    def get_settable_classes(cls):
        # FIXME: if we want to let people inherit from abstract resource, we need to check
        # parents here.
        from concord.resources.models import AbstractResource, AbstractItem, Resource, Item
        return [AbstractResource, AbstractItem, Resource, Item]    

    def description_present_tense(self):
        return "remove item with pk %s" % (self.item_pk)  

    def description_past_tense(self):
        return "removed item with pk %s" % (self.item_pk)

    def validate(self, actor, target):
        """
        put real logic here
        """
        if actor and target and self.item_pk:
            return True
        return False

    def implement(self, actor, target):
        try:
            item = Item.objects.get(pk=self.item_pk)
            item.delete()
            return True
        except Exception as exception:
            print(exception)
            return False
