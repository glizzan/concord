from django.test import TestCase

from concord.actions.utils import AutoDescription
from concord.resources.state_changes import AddRowStateChange
from concord.resources.client import CommentClient


class AutoDesciptionTestCase(TestCase):

    def setUp(self):
        self.add_row_state_change = AddRowStateChange(index=3, row_content="new stuff for row")

    def test_simple_autodescription(self):
        auto = AutoDescription(verb="add", default_string="comment")
        self.assertEquals(auto.shortname, "add comment")
        self.assertEquals(auto.description_present_tense(), "add comment")
        self.assertEquals(auto.description_past_tense(), "added comment")

    def test_autodescription_specialized_past_tense(self):
        auto = AutoDescription(verb="begin", past_tense="began", default_string="vote")
        self.assertEquals(auto.description_present_tense(), "begin vote")
        self.assertEquals(auto.description_past_tense(), "began vote")

    def test_with_change_data(self):
        auto = AutoDescription(verb="add", default_string="row", detail_string="row with index {index} to have new content '{row_content}'")
        self.assertEquals(auto.description_present_tense(self.add_row_state_change),
            "add row with index 3 to have new content 'new stuff for row'")
        self.assertEquals(auto.description_past_tense(self.add_row_state_change),
            "added row with index 3 to have new content 'new stuff for row'")

    def test_uninstantiated_description(self):
        self.assertEquals(AddRowStateChange.get_uninstantiated_description(), "add row to list")


class LookupStateChangeMethodsTestCase(TestCase):

    def test_generation_of_client_methods(self):

        client = CommentClient()
        self.assertTrue(client.edit_comment)
        self.assertEquals(client.edit_comment.__name__, "state_change_function")
        self.assertTrue(client.delete_comment)
        self.assertEquals(client.delete_comment.__name__, "state_change_function")
        self.assertTrue(client.add_comment)
        self.assertEquals(client.add_comment.__name__, "add_comment")  # exists explicitly on client