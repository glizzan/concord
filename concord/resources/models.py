"""Resource models."""

import json

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

    commentor = models.ForeignKey(User, on_delete=models.CASCADE)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    text = models.CharField(max_length=1000)

    def get_name(self):
        if len(self.text) < 30:
            return self.text
        return self.text[:30] + "..."

    def export(self):
        return {"commentor": self.commentor.username, "text": self.text, "created_at": str(self.created_at),
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
    """Model to store simple lists with arbitrary fields."""

    name = models.CharField(max_length=200)
    description = models.CharField(max_length=200)
    rows = models.TextField(list)
    row_configuration = models.TextField(list)

    def get_name(self):
        """Get name of item."""
        return self.name

    def get_row_configuration(self):
        """Gets row configuation json and loads to Python dict."""
        if self.row_configuration:
            return json.loads(self.row_configuration)
        return {}

    def set_row_configuration(self, row_configuration):
        """Given a row configuration with format, validated and saves to DB."""
        self.validate_configuration(row_configuration)
        self.adjust_rows_to_new_configuration(row_configuration)
        self.row_configuration = json.dumps(row_configuration)

    def validate_configuration(self, row_configuration):
        """Checks that a given configuration is valid.  Should have format:

        { field_name : { 'required': True, 'default_value': 'default'}}

        If required is not supplied, defaults to False.  If default_value is not supplied, defaults to None."""
        if not isinstance(row_configuration, dict):
            raise ValidationError(f"List configuration must be a dict, not {type(row_configuration)}")
        if len(row_configuration.items()) < 1:
            raise ValidationError("Must supply at least one column to configuration.")
        field_name_list = []
        for field_name, params in row_configuration.items():
            if field_name in field_name_list:
                raise ValidationError(f"Field names must be unique. Multiple instances of field {field_name}")
            field_name_list.append(field_name)
            params["required"] = params["required"] if "required" in params else False
            params["default_value"] = params["default_value"] if "default_value" in params else None
            if not isinstance(params["required"], bool):
                raise ValidationError(f"Required parameter for {field_name} must be True or False, " +
                                      f"not {type(params['required'])}")
            if params["default_value"] and not isinstance(params["default_value"], str):
                raise ValidationError(f"default_value parameter for {field_name} must be str, not " +
                                      f"{type(params['default_value'])}")
            if set(params.keys()) - set(["required", "default_value"]):
                unexpected_keys = list(set(params.keys()) - set(["required", "default_value"]))
                raise ValidationError(f"unexpected keys {unexpected_keys} in row configuration")

    def check_row_against_configuration(self, row):
        """Given a row, check that it's valid for the row configuration."""
        config = self.get_row_configuration()
        for field_name, params in config.items():
            if params["required"]:
                if field_name not in row or row[field_name] in ["", None]:
                    if not params["default_value"]:
                        raise ValidationError(f"Field {field_name} is required with no default_value, " +
                                              "so must be supplied")
        for field_name, params in row.items():
            if field_name not in config:
                field_names = ", ".join([field_name for field_name, params in config.items()])
                raise ValidationError(f"Field {field_name} is not a valid field, must be one of {field_names}")

    def handle_missing_fields_and_values(self, row):
        """Given a row, check that it's valid for the row configuration."""
        config = self.get_row_configuration()
        for field_name, params in config.items():
            if field_name not in row:
                row[field_name] = ""
            if params["required"] and not row[field_name]:
                row[field_name] = params["default_value"]
        return row

    def adjust_rows_to_new_configuration(self, configuration):
        """Given a new row configuration, goes through existing rows and adjusts them them."""
        required_fields = [field_name for field_name, params in configuration.items() if params["required"] is True]
        adjusted_rows = []
        for row in self.get_rows():
            new_row = {}
            for row_field_name, row_field_value in row.items():
                if row_field_name in configuration:  # leaves behind fields not in new config
                    new_row.update({row_field_name: row_field_value})
            for field in required_fields:
                if field not in row:
                    new_row[field] = None
                if field in row and row[field]:
                    new_row[field] = row[field]
                else:
                    default_value = configuration[field].get("default_value", None)
                    if default_value:
                        new_row[field] = default_value
                    else:
                        raise ValidationError(f"Need default value for required field {field}")
            adjusted_rows.append(new_row)
        self.rows = json.dumps(adjusted_rows)

    def get_rows(self):
        """Get the rows in the list."""
        if self.rows:
            return json.loads(self.rows)
        return []

    def add_row(self, row, index=None):
        """Add a row to the list."""
        self.check_row_against_configuration(row)
        row = self.handle_missing_fields_and_values(row)
        rows = self.get_rows()
        if index or index == 0:
            rows.insert(index, row)
        else:
            rows.append(row)
        self.rows = json.dumps(rows)

    def edit_row(self, row, index):
        """Edit a row in the list."""
        self.check_row_against_configuration(row)
        row = self.handle_missing_fields_and_values(row)
        rows = self.get_rows()
        rows[index] = row
        self.rows = json.dumps(rows)

    def move_row(self, old_index, new_index):
        """Moves a row from old index to new index."""
        rows = self.get_rows()
        row = rows.pop(old_index)
        rows.insert(new_index, row)
        self.rows = json.dumps(rows)

    def delete_row(self, index):
        """Delete a row from the list."""
        rows = self.get_rows()
        rows.pop(index)
        self.rows = json.dumps(rows)

    def get_nested_objects(self):
        """Get models that permissions for this model might be set on."""
        return [self.get_owner()]

    def get_csv_data(self):
        columns = ["index"] + list(self.get_row_configuration().keys())
        rows = []
        for index, row_dict in enumerate(self.get_rows()):
            rows.append({**row_dict, **{"index": index}})
        return columns, rows
