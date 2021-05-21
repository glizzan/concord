from django.test import TestCase
from django.core.exceptions import ValidationError

from concord.resources.models import SimpleList
from concord.resources import state_changes


class SimpleListModelTestCase(TestCase):

    def setUp(self):
        self.list = SimpleList(name="Animals", description="A list of my favorite animals")

    def test_initialization(self):
        self.assertEquals(self.list.get_rows(), {})
        self.assertEquals(self.list.get_columns(), {})

    def test_column_configuration(self):
        self.list.add_column(column_name="color", required=True, default_value="brown")
        self.assertEquals(self.list.get_columns(), {"color": {"required": True, "default_value": "brown"}})

    def test_add_valid_row(self):
        self.list.add_column(column_name="color", required=True, default_value="brown")
        self.list.add_row({"color": "blue"})
        self.assertEquals(self.list.get_rows(keys=False), [{"color": "blue"}])

    def test_add_row_with_missing_data(self):
        self.list.add_column(column_name="color", required=True, default_value="brown")
        self.list.add_row({})
        self.assertEquals(self.list.get_rows(keys=False), [{"color": "brown"}])

    def test_add_invalid_row(self):
        self.list.add_column(column_name="color", required=True)
        with self.assertRaises(ValidationError):
            self.list.add_row({})

    def test_edit_row(self):
        self.list.add_column(column_name="color", required=True, default_value="brown")
        self.list.add_row({"color": "blue"})
        self.list.add_row({"color": "green"})
        self.assertEquals(self.list.get_rows(keys=False), [{'color': 'blue'}, {'color': 'green'}])
        unique_ids = self.list.get_row_keys()
        self.list.edit_row({"color": "white"}, unique_ids[0])
        self.list.edit_row({"color": "purple"}, unique_ids[1])
        self.assertEquals(self.list.get_rows(keys=False), [{'color': 'white'}, {'color': 'purple'}])

    def test_delete_row(self):
        self.list.add_column(column_name="color", required=True, default_value="brown")
        self.list.add_row({"color": "blue"})
        self.list.add_row({"color": "green"})
        unique_id = self.list.get_row_keys()[0]
        self.list.delete_row(unique_id)
        self.assertEquals(self.list.get_rows(keys=False), [{'color': 'green'}])

    # new methods

    def test_adding_column_adds_to_rows(self):
        self.list.add_column(column_name="color", required=True, default_value="brown")
        self.list.add_row({"color": "blue"})
        self.list.add_row({"color": "green"})
        self.list.add_column(column_name="size", required=True, default_value="medium")
        self.list.add_column(column_name="location", required=False, default_value=None)
        self.assertEquals(self.list.get_rows(keys=False),
            [{'color': 'blue', 'size': 'medium', 'location': None},
             {'color': 'green', 'size': 'medium', 'location': None}])

    def test_cant_add_required_column_without_default_value(self):
        self.list.add_column(column_name="color", required=True, default_value="brown")
        self.list.add_row({"color": "blue"})
        with self.assertRaises(ValidationError):
            self.list.add_column(column_name="size", required=True, default_value=None)
        with self.assertRaises(ValidationError):
            self.list.add_column(column_name="size", required=True)

    def test_cant_add_column_with_same_name(self):
        self.list.add_column(column_name="color", required=True, default_value="brown")
        self.list.add_row({"color": "blue"})
        with self.assertRaises(ValidationError):
            self.list.add_column(column_name="color", required=True, default_value="brown")

    def test_edit_column_value(self):
        self.list.add_column(column_name="color", required=True, default_value="brown")
        self.list.add_column(column_name="size", required=True, default_value="medium")
        self.list.add_row({"color": "blue"})
        self.list.edit_column(column_name="size", required=True, default_value="large")
        self.list.add_row({"color": "red"})
        self.assertEquals(self.list.get_rows(keys=False),
            [{'color': 'blue', 'size': 'medium'}, {'color': 'red', 'size': 'large'}])

    def test_edit_column_to_required_with_no_default_value_causes_error(self):
        self.list.add_column(column_name="color", required=True, default_value="brown")
        self.list.add_column(column_name="size", required=False)
        self.list.add_row({"color": "blue"})
        with self.assertRaises(ValidationError):
            self.list.edit_column(column_name="size", required=True)

    def test_edit_nonexistent_column_causes_error(self):
        self.list.add_column(column_name="color", required=True, default_value="brown")
        self.list.add_column(column_name="size", required=False)
        self.list.add_row({"color": "blue"})
        with self.assertRaises(ValidationError):
            self.list.edit_column(column_name="friends", required=True)

    def test_edit_column_name(self):
        self.list.add_column(column_name="color", required=True, default_value="brown")
        self.list.add_row({"color": "blue"})
        self.list.add_row({"color": "green"})
        self.list.edit_column(column_name="color", new_name="collar color")
        self.assertEquals(self.list.get_rows(keys=False), [{"collar color": "blue"}, {"collar color": "green"}])

    def test_deleting_column_deletes_from_rows(self):
        self.list.add_column(column_name="color", required=True, default_value="brown")
        self.list.add_column(column_name="size", required=True, default_value="medium")
        self.list.add_row({"color": "blue"})
        self.list.add_row({"color": "green"})
        self.list.delete_column("color")
        self.assertEquals(self.list.get_rows(keys=False), [{'size': 'medium'}, {'size': 'medium'}])


class SimpleListStateChangeTestCase(TestCase):

    def test_add_column_state_change(self):

        # basic column is valid
        self.list = SimpleList(name="Animals", description="A list of my favorite animals")
        sc = state_changes.AddColumnStateChange(column_name="color")
        self.assertTrue(sc.validate_state_change(actor="a", target=self.list))

        # more complex is valid
        self.list = SimpleList(name="Animals", description="A list of my favorite animals")
        sc = state_changes.AddColumnStateChange(column_name="color", required=True, default_value="blue")
        self.assertTrue(sc.validate_state_change(actor="a", target=self.list))

        # no column name is invalid
        self.list = SimpleList(name="Animals", description="A list of my favorite animals")
        sc = state_changes.AddColumnStateChange(required=True, default_value="blue")
        self.assertFalse(sc.validate_state_change(actor="a", target=self.list))

    def test_edit_column_state_change(self):

        # changing name is valid
        self.list = SimpleList(name="Animals", description="A list of my favorite animals")
        self.list.add_column(column_name="color", required=True, default_value="brown")
        sc = state_changes.EditColumnStateChange(column_name="color", new_name="collar color")
        self.assertTrue(sc.validate_state_change(actor="a", target=self.list))

        # changing default value is valid
        self.list = SimpleList(name="Animals", description="A list of my favorite animals")
        self.list.add_column(column_name="color", required=True, default_value="brown")
        sc = state_changes.EditColumnStateChange(column_name="color", default_value="blue")
        self.assertTrue(sc.validate_state_change(actor="a", target=self.list))

        # changing required is valid
        self.list = SimpleList(name="Animals", description="A list of my favorite animals")
        self.list.add_column(column_name="color", required=True, default_value="brown")
        sc = state_changes.EditColumnStateChange(column_name="color", required=False)
        self.assertTrue(sc.validate_state_change(actor="a", target=self.list))

        # changing multiple is valid
        self.list = SimpleList(name="Animals", description="A list of my favorite animals")
        self.list.add_column(column_name="color", required=True, default_value="brown")
        sc = state_changes.EditColumnStateChange(column_name="color", new_name="collar color", required=False)
        self.assertTrue(sc.validate_state_change(actor="a", target=self.list))
