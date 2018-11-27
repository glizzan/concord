from actions.state_changes import BaseStateChange

from resources.models import Item


#####################################
### Resource & Item State Changes ###
#####################################

class ChangeResourceNameStateChange(BaseStateChange):
    name = "resource_changename"

    def __init__(self, new_name):
        self.new_name = new_name

    def validate(self, actor, target):
        """
        TODO: put real logic here
        """
        return True

    def implement(self, actor, target):
        target.name = self.new_name
        target.save()
        return target

class AddItemResourceStateChange(BaseStateChange):
    name = "resource_additem"

    def __init__(self, item_name):
        self.item_name = item_name

    def validate(self, actor, target):
        """
        TODO: put real logic here
        """
        if actor and target and self.item_name:
            return True
        return False

    def implement(self, actor, target):
        item = Item.objects.create(name=self.item_name, resource=target, 
            owner=actor)
        return item


class RemoveItemResourceStateChange(BaseStateChange):
    name = "resource_removeitem"

    def __init__(self, item_pk):
        self.item_pk = item_pk

    def validate(self, actor, target):
        """
        TODO: put real logic here
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
