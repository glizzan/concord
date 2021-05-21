"""Resource models."""

import json, random

from django.db import models
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.auth.models import User

from concord.actions.models import PermissionedModel


class Comment(PermissionedModel):
    """Comment model."""

    commented_object_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    commented_object_id = models.PositiveIntegerField()
    commented_object = GenericForeignKey('commented_object_content_type', 'commented_object_id')

    commenter = models.ForeignKey(User, on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    text = models.CharField(max_length=1000)

    def get_name(self):
        if len(self.text) < 30:
            return self.text
        return self.text[:30] + "..."

    def export(self):
        return {"commenter": self.commenter.username, "text": self.text, "created_at": str(self.created_at),
                "updated_at": str(self.updated_at)}


class CommentCatcher(PermissionedModel):
    """The comment catcher model is a hack to deal with leaving comments on non-permissioned models.  Right now,
    the only model we're doing this for is Action."""

    action = models.IntegerField(unique=True)

    def get_name(self):
        """Get name of object."""
        return f"Comment catcher for action {self.action}"

    def get_nested_objects(self):
        return [self.get_owner()]


class SimpleList(PermissionedModel):
    """Model to store simple lists with arbitrary fields. Although simple, these lists have a few notable
    behaviors. First, when adding a column, you can supply a default value to apply to all existing rows.
    Second, columns can be required, which means all rows must have a value for that cell. Cells can be null,
    meaning they contain the value None."""

    name = models.CharField(max_length=200)
    description = models.CharField(max_length=200, default="")
    rows = models.TextField(list)
    columns = models.TextField(list)

    # Get data

    def get_name(self):
        """Get name of item."""
        return self.name

    def get_columns(self):
        """Gets column configuation json and loads to Python dict."""
        if self.columns:
            return json.loads(self.columns)
        return {}

    def get_rows(self, keys=True):
        """Get the rows in the list."""
        if self.rows:
            if not keys:
                return [value for key, value in json.loads(self.rows).items()]
            return json.loads(self.rows)
        return {}

    def get_row_keys(self):
        if self.rows:
            return [key for key, value in json.loads(self.rows).items()]
        return []

    def get_unique_id(self, column_name, cell_value):
        """Given a column name and cell value, retrieves the unique_id of the first row matching that value."""
        for unique_id, row_data in self.get_rows().items():
            if column_name in row_data and row_data[column_name] == cell_value:
                return unique_id

    # set row data

    def generate_unique_id(self, rows):
        unique_id = random.randrange(1, 100000)
        while unique_id in rows:
            unique_id = random.randrange(1, 100000)
        return str(unique_id)

    def new_row(self, row):
        rows = self.get_rows()
        unique_id = self.generate_unique_id(rows)
        rows[unique_id] = row
        self.rows = json.dumps(rows)
        return unique_id

    def add_row(self, row):
        """Add a row to the list."""
        self.validate_row(row)
        row = self.handle_missing_fields_and_values(row)
        return self.new_row(row)

    def edit_row(self, row, unique_id):
        """Edit a row in the list."""
        rows = self.get_rows()
        if unique_id not in rows:
            raise ValidationError(f"Unique ID '{unique_id}' not in list")
        self.validate_row(row)
        row = self.handle_missing_fields_and_values(row)
        rows[str(unique_id)] = row
        self.rows = json.dumps(rows)

    def delete_row(self, unique_id):
        """Delete a row from the list."""
        rows = self.get_rows()
        del(rows[str(unique_id)])
        self.rows = json.dumps(rows)

    # Set column data

    def add_column(self, *, column_name, **kwargs):

        config = self.get_columns()
        if column_name in config:
            raise ValidationError(f"Column {column_name} already exists")

        column = {column_name: {
            "required": kwargs["required"] if "required" in kwargs else False,
            "default_value": kwargs["default_value"] if "default_value" in kwargs else None
        }}

        config.update(column)
        self.update_column_in_rows(column)
        self.columns = json.dumps(config)

    def edit_column(self, column_name, **kwargs):

        config = self.get_columns()
        if column_name not in config:
            raise ValidationError(f"Column {column_name} does not exist")

        if "new_name" in kwargs and kwargs["new_name"]:

            new_name = kwargs["new_name"]
            if new_name in config:
                raise ValidationError(f"Column {new_name} already exists")

            old_column = config.pop(column_name)
            config[new_name] = old_column

            # edit in rows
            rows = self.get_rows()
            for key, row_data in rows.items():
                row_data[new_name] = row_data[column_name]
                del(row_data[column_name])
            self.rows = json.dumps(rows)

            column_name = new_name

        if "required" in kwargs:
            config[column_name]["required"] = kwargs["required"]

        if "default_value" in kwargs:
            config[column_name]["default_value"] = kwargs["default_value"]

        self.update_column_in_rows({column_name: config[column_name]})
        self.columns = json.dumps(config)

    def delete_column(self, column_name):
        config = self.get_columns()
        if column_name not in config:
            raise ValidationError(f"Column {column_name} does not exist")
        del(config[column_name])
        self.remove_column_from_rows(column_name)
        self.columns = json.dumps(config)

    # Validation/Adjustment

    def validate_row(self, row):
        """Given a row, check that it's valid for the row configuration."""
        config = self.get_columns()
        for field_name, params in config.items():
            if params["required"] and (field_name not in row or not row[field_name]) and not params["default_value"]:
                raise ValidationError(f"Field {field_name} is required with no default value, so must be supplied")
        for field_name, params in row.items():
            if field_name not in config:
                field_names = ", ".join([field_name for field_name, params in config.items()])
                raise ValidationError(f"Field {field_name} is not a valid field, must be one of {field_names}")

    def handle_missing_fields_and_values(self, row):
        """If a row is missing a required field, add the default value.
        NOTE: this method should be called post-validation, so we can assume that there is a default value."""
        config = self.get_columns()
        for field_name, params in config.items():
            if field_name not in row:
                row[field_name] = None
            if params["required"] and not row[field_name]:
                row[field_name] = params["default_value"]
        return row

    def update_column_in_rows(self, column):
        column_name, column_data = list(column.keys())[0], list(column.values())[0]
        rows = self.get_rows()
        for unique_id, row_data in rows.items():
            if column_name not in row_data:
                row_data[column_name] = None
            if column_data["required"] and not row_data[column_name]:
                if column_data["default_value"]:
                    row_data[column_name] = column_data["default_value"]
                else:
                    raise ValidationError(f"Must supply default for existing rows for required column '{column_name}'")
            rows[unique_id] = row_data
        self.rows = json.dumps(rows)

    def remove_column_from_rows(self, column_name):
        rows = self.get_rows()
        for unique_id, row_data in rows.items():
            if column_name in row_data:
                del(row_data[column_name])
        self.rows = json.dumps(rows)

    # Misc

    def get_nested_objects(self):
        """Get models that permissions for this model might be set on."""
        return [self.get_owner()]

    def get_csv_data(self):
        columns = ["index"] + list(self.get_columns().keys())
        rows = []
        for index, row_dict in enumerate(self.get_rows()):
            rows.append({**row_dict, **{"index": index}})
        return columns, rows


class Document(PermissionedModel):
    """Document model."""
    name = models.CharField(max_length=200)
    description = models.CharField(max_length=200, default="")
    content = models.TextField(default="")

    def get_nested_objects(self):
        return [self.get_owner()]
