from actions.models import create_action


class BaseActionClient(object):

    def __init__(self, actor, target=None):
        self.actor = actor
        self.target = target

    def set_target(self, target):
        self.target = target

    def check_target(self, target):
        """
        Because for now we're using the same client for everything, and the client 
        sometimes creates objects without needing a target or action, we need to
        check for the target before running an action.
        """
        if target:
            self.target = target
        if not self.target:
            raise("Target is required")

    def create_and_take_action(self, change, target):
        self.check_target(target)
        action = create_action(change=change, target=self.target, actor=self.actor)
        return action.take_action()
