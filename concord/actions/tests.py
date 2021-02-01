from django.test import TestCase

from concord.actions.utils import AutoDescription
from concord.resources.state_changes import AddRowStateChange


add_row_state_change = AddRowStateChange(index=3, row_content="new stuff for row")


class AutoDesciptionTestCase(TestCase):

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
        self.assertEquals(auto.description_present_tense(add_row_state_change),
            "add row with index 3 to have new content 'new stuff for row'")
        self.assertEquals(auto.description_past_tense(add_row_state_change),
            "added row with index 3 to have new content 'new stuff for row'")

    def test_with_configuration(self):
        auto = AutoDescription(verb="add", default_string="comment", configurations=[
            ("commentor_only", "if the user is the commentor"),
            ("original_creator_only", "if the user is the creator of the thing being commented on")])

        configuration = {"commentor_only": True, "original_creator_only": True}
        self.assertEquals(auto.description_with_configuration(configuration),
            "add comment, but only if the user is the commentor and if the user is the creator of the thing being commented on")

        configuration = {"commentor_only": True}
        self.assertEquals(auto.description_with_configuration(configuration), "add comment, but only if the user is the commentor")

        configuration = {"original_creator_only": True}
        self.assertEquals(auto.description_with_configuration(configuration), "add comment, but only if the user is the creator of the thing being commented on")

        configuration = {}
        self.assertEquals(auto.description_with_configuration(configuration), "add comment")

    def test_with_configuration_with_data(self):
        auto = AutoDescription(verb="add", default_string="people to role", configurations=[("role_name", "if the role is '{role_name}'")])
        configuration = {"role_name": "members"}
        self.assertEquals(auto.description_with_configuration(configuration), "add people to role, but only if the role is 'members'")

    def test_uninstantiated_description(self):
        configuration = {"role_name": "members"}
        self.assertEquals(AddRowStateChange.get_uninstantiated_description(configuration), "add row to list")
