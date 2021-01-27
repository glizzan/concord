import datetime, pytz

from django.test import TestCase

from concord.core.concord_models import Actor
from concord.core.base_classes import TransformationObject
from concord.resources.concord_models import Comment
from concord.resources.models import Comment as DBComment


class CommentUnitTests(TestCase):

    # Model create/save

    def test_create_comment(self):
        comment = Comment()
        self.assertEquals(comment.get_field("text").label, "Comment text")

    def test_serialize_comment(self):
        comment = Comment()
        self.assertEquals(
            comment.serialize(),
            {'class': 'Comment',
             'parameters': {'commented_object': None,
                            'commentor': None,
                            'created_at': None,
                            'text': None,
                            'updated_at': None,
                            'creator': None,
                            'foundational_permission_enabled': None,
                            'governing_permission_enabled': None,
                            'owner': None,
                            'text': None,
                            }})

    # Model fields

    def test_commentor(self):

        def fake_lookup_strategy(field, value):
            if value == 2:
                return Actor(username="jane", id=2)
            return TransformationObject(success=False)

        jane = Actor(username="jane", id=2)
        comment = Comment()
        comment.commentor.transformation_strategies = [fake_lookup_strategy]
        from concord.core.validation import db_field_strategy
        comment.commentor.skip_validation_strategies = [db_field_strategy]
        comment.commentor = jane

        self.assertTrue(comment.validate()["commentor"].valid)
        self.assertEquals(comment.commentor.id, jane.id)
        self.assertEquals(comment.serialize_field("commentor"), jane.id)

        deserialized_comment = Comment(**comment.serialize()["parameters"])
        self.assertEquals(deserialized_comment.commentor.id, jane.id)

    def test_commented(self):
        parent_comment = Comment(text="Hullo!")
        main_comment = Comment(commented_object=parent_comment)
        self.assertEquals(main_comment.commented_object, parent_comment)
        self.assertEquals(main_comment.serialize_field("commented_object"),
            {'pk': None, 'concord_model': 'Comment'})
        deserialized_comment = Comment(**main_comment.serialize()["parameters"])
        self.assertEquals(deserialized_comment.commented_object.__class__, parent_comment.__class__)
        # NOTE: the following won't work unless we save & load from DB
        # self.assertEquals(deserialized_comment.commented_object.text, parent_comment.text)

    def test_short_text(self):

        # Test basic
        short_text = "Hullo!"
        comment = Comment(text="Hullo!")
        self.assertEquals(comment.text, short_text)
        self.assertTrue(comment.validate()["text"].valid)

        # Test serializing & deserializing
        self.assertEquals(comment.serialize_field("text"), short_text)
        deserialized_comment = Comment(**comment.serialize()["parameters"])
        self.assertEquals(deserialized_comment.text, short_text)
        self.assertTrue(deserialized_comment.validate()["text"].valid)

    def test_text_invalid_length(self):

        # Test basic
        long_text = "Hello, my name is Inigo Montoya. You killed my father. Prepare to die. " * 100
        comment = Comment(text=long_text)
        self.assertEquals(comment.text, long_text)
        self.assertFalse(comment.validate()["text"].valid)

    def test_created_at(self):
        created_at = datetime.datetime(month=1, year=2000, day=1, tzinfo=pytz.utc)
        comment = Comment(created_at=created_at)
        self.assertFalse(comment.validate()["created_at"].valid)
        self.assertEquals(comment.validate()["created_at"].msg, "DateTimeField created_at is read only so must be null")

    def test_updated(self):
        updated_at = datetime.datetime(month=1, year=2000, day=1, tzinfo=pytz.utc)
        comment = Comment(updated_at=updated_at)
        self.assertFalse(comment.validate()["updated_at"].valid)
        self.assertEquals(comment.validate()["updated_at"].msg, "DateTimeField updated_at is read only so must be null")

    # Model methods

    def test_get_name(self):
        fake_text = "Okay well so here's the thing, I really like this post but I feel it could be improved by"
        comment = Comment(text=fake_text)
        self.assertEquals(comment.get_name(), "Okay well so here's the thing,...")

    def test_save(self):
        """
        Requirements:
        - all Concord models linked to a Django model must have an owner to save to DB
        - to save a generic foreign key field to Django DB, we must have the full Django model object

        Note that we don't have easily working Concord Model with linked Django model we can use, because
        we're just testing for the first time here, so lots of stubbing happening here.

        The tests SHOULD run, but...

        FIXME Issues:
        - we're using 'override_check' by default which is bad
        - also generally this is all WAY too janky, the abstraction must be wrong

        see brainstorming.py

        """

        from concord.communities.models import Community
        from concord.core.concord_models import PermissionedModel
        from django.contrib.auth.models import User

        class ConcordCommunity(PermissionedModel):
            _django_model = Community

        django_comm = Community.objects.create(name="MockCommunity")
        cc = ConcordCommunity(pk=django_comm.pk)
        cc.save()

        # Before save, no comments in DB
        self.assertFalse(DBComment.objects.all())

        # Save comment
        fake_text = "Okay well so here's the thing, I really like this post but I feel it could be improved by"
        comment = Comment(text=fake_text, owner=cc, commented_object=cc, commentor=User.objects.create(username="janeee"))
        comment.save()

        # Now comments in DB
        saved_comment = DBComment.objects.first()
        self.assertEquals(saved_comment.text, fake_text)

    def test_read_only_fields_on_save(self):
        ...
