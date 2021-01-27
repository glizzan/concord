from django.contrib.auth.models import User

from concord.resources.models import Comment as DBComment # TODO: fix naming shcema!
from concord.core import fields
# from concord.core.base_classes import ConcordObjectMixin
from concord.core.concord_models import PermissionedModel

class newActorField(fields.ActorField):

    def db_lookup(self, pk):
        from django.contrib.auth.models import User
        users = User.objects.filter(pk=pk)
        if users: return users[0]


class Comment(PermissionedModel):

    _django_model = DBComment

    commented_object = fields.GenericForeignKeyField(db_model=DBComment, db_field_name="commented_object",
                                                     label="What is being commented on?")
    commentor = fields.ActorField(db_model=DBComment, db_field_name="commentor", label="Who is commenting?",)
    created_at = fields.DateTimeField(db_model=DBComment, db_field_name="created_at", label="When was this created?")
    updated_at = fields.DateTimeField(db_model=DBComment, db_field_name="updated_at", label="When was this last updated?")
    text = fields.CharField(db_model=DBComment, db_field_name="text", label="Comment text")

    def get_name(self):
        if len(self.text) < 30:
            return self.text
        return self.text[:30] + "..."
