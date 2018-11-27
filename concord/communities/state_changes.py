from actions.state_changes import BaseStateChange


###############################
### Community State Changes ###
###############################

class ChangeNameStateChange(BaseStateChange):
    name = "community_changename"

    def __init__(self, new_name):
        self.new_name = new_name

    def validate(self, actor, target):
        """
        TODO: put real logic here
        """
        if actor and target and self.new_name:
            return True
        return False

    def implement(self, actor, target):
        target.name = self.new_name
        target.save()
        return target