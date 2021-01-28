from django.test import TestCase

from concord.utils.pipelines import Match


class FakeCondition:
    pk = 2

fake_condition = FakeCondition()

match_dict = {"pipeline": "specific", "has_authority": True, "matched_role": "friends", "has_condition": True,
    "condition_manager": fake_condition, "status": "waiting", "rejection": "haha you stink"}

match_dict2 = {"pipeline": "specific", "has_authority": True, "matched_role": "friends", "has_condition": True,
    "condition_manager": None, "status": "waiting", "rejection": None}

combined_match_dict = {"pipeline": "specific", "status": "waiting", "matches": [Match(**match_dict), Match(**match_dict2)]}


class MatchTestCase(TestCase):

    def test_init(self):
        match = Match(**match_dict)
        self.assertEquals(match.pipeline, "specific")
        self.assertEquals(match.status, "waiting")
        self.assertTrue(match.has_authority)

    def test_nested_init(self):
        match = Match(**combined_match_dict)
        self.assertEquals(match.pipeline, "specific")
        self.assertEquals(match.status, "waiting")
        self.assertEquals(match.matches[0].__class__, Match)

    def test_get_condition_managers(self):
        match = Match(**match_dict)
        self.assertEquals(match.get_condition_managers(), [fake_condition])
        match = Match(**combined_match_dict)
        self.assertEquals(match.get_condition_managers(), [fake_condition])

    def test_rejection_message(self):
        match = Match(**match_dict)
        self.assertEquals(match.rejection_message(), "haha you stink")
        match = Match(**combined_match_dict)
        self.assertEquals(match.rejection_message(), "haha you stink")

    def test_match_serialize(self):
        match = Match(**combined_match_dict)
        self.assertEquals(match.serialize(),
            {'pipeline': 'specific', 'status': 'waiting', 'matches': [
                {'pipeline': 'specific', 'has_authority': True, 'matched_role': 'friends', 'has_condition': True,
                'condition_manager': 2, 'status': 'waiting', 'rejection': 'haha you stink'},
                {'pipeline': 'specific', 'has_authority': True, 'matched_role': 'friends', 'has_condition': True,
                'condition_manager': None, 'status': 'waiting', 'rejection': None}]
            })
