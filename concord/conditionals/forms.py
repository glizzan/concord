import json
from abc import abstractmethod

from django import forms

from concord.permission_resources.forms import PermissionFormMixin
from concord.permission_resources.client import PermissionResourceClient
from concord.conditionals.client import PermissionConditionalClient
from concord.conditionals.models import ApprovalCondition, VoteCondition


class ConditionSelectionForm(forms.Form):

    def __init__(self, *args, **kwargs):
        '''The ConditionalForm allows users to set conditions on a permission instance.  The form
        provides all available conditions; it's up to the front end to hide unused conditions.'''

        self.instance = kwargs.pop('instance')
        self.request = kwargs.pop('request')
        super().__init__(*args, **kwargs)

        conditionalClient = PermissionConditionalClient(actor=self.request.user)
        CONDITION_CHOICES = []
        for condition in conditionalClient.get_possible_conditions():
            CONDITION_CHOICES.append((condition.get_slug(),condition.descriptive_name))

        self.fields["condition"] = forms.MultipleChoiceField(label="Type of condition to add", 
            required=True, choices=CONDITION_CHOICES)

    def get_condition_choice(self):
        return self.cleaned_data["condition"][0]


class BaseConditionForm(PermissionFormMixin, forms.Form):

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request')
        self.target_permission = kwargs.pop('permission')
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)

        # This is a little funky, but we're using instance in two ways here.  If we pass in an 
        # instance, we're saying "this conditiontemplate exists" and saving it to it own property,
        # but we're using self.instance to indicate the target permission since that's getting used in
        # PermissionFormMixin.  Probably worth refactoring PermissionFormMixin to fix htis.
        if self.instance:
            self.condition_data_dict = json.loads(self.instance.condition_data)
            self.condition = self.instance
        self.instance = self.target_permission

        # Add condition's fields
        for field in self.condition_model._meta.fields:
            if field.name in self.condition_fields:
                self.fields[field.name] = field.formfield()
                # If we've got existing data, and this field is in the data, and the value is Truthy...
                if (hasattr(self, 'condition_data_dict') and field.name in self.condition_data_dict and 
                            self.condition_data_dict[field.name]):
                    self.fields[field.name].initial = self.condition_data_dict[field.name]

        # Add permissions info
        self.determine_owner(owned_object=self.target_permission)
        self.set_choices() 
        self.initialize_permission_fields() 
        if hasattr(self, "condition") and self.condition:
            self.add_permission_initial_data()

    def add_permission_initial_data(self):
        '''In the PermissionFormMixin, initial data is collected by searching for instantiated permissions,
        but in a condition form the permission data is stored in condition_template.permission_data.'''
        # FIXME: this is hacky too :(
        for field_name, field_object in self.fields.items():
            if self.condition.permission_data:
                permission= json.loads(self.condition.permission_data)
                if "~" in field_name:  # If it's a permission field
                    if field_object.initial and permission["permission_type"] in field_object.initial:
                        count = field_name.split("~")[0]
                        self.fields["%s~individuals" % count].initial = permission["permission_actors"]
                        self.fields["%s~roles" % count].initial = permission["permission_roles"]
                        for cf_key, cf_value in permission["permission_configuration"].items():
                            self.fields["%s~configurablefield~%s" % (count, cf_key)] = cf_value

    def get_settable_permissions(self):
        '''Occasionally metapermission form will be passed a mock permission object.  We need to 
        override get_settable_permissions to handle that case.'''

        # FIXME: Doing this because self.instance/self.target_permission shenanigans meant that the
        # form was using the target permission's change_types instead of the condition's change_types
        prClient = PermissionResourceClient(actor=self.request.user, target=self.condition_model)
        return prClient.get_settable_permissions(return_format="permission_objects")

    def save(self):
        conditionalClient = PermissionConditionalClient(actor=self.request.user, target=self.target_permission)
        if hasattr(self, 'condition_data_dict'):  # Indicates we're updating, not adding, a condition
            # You can only update condition data and permission data
            # FIXME: ownership stuff needs refactoring
            conditionalClient.change_condition(
                condition_pk=self.condition.pk,
                condition_data=self.get_configuration_dict(),
                permission_data=self.get_permissions_dict())
        else:    
            conditionalClient.add_condition(
                condition_type=self.condition_type, 
                condition_data=self.get_configuration_dict(),
                permission_data=self.get_permissions_dict())

    def process_permissions(self):
        # FIXME: Copied and pasted from mixin method, but need to avoid non permissions fields.
        # Gotta be a better way to do this.

        self.permission_data = {}

        for key, value in self.cleaned_data.items():

            if '~' not in key:  # FIXME: only permissions have the ~
                continue

            fieldname_pieces = key.split("~")

            count = fieldname_pieces[0]
            if count not in self.permission_data:
                self.permission_data[count] = {"configurable fields": {}}

            field_type = fieldname_pieces[1]

            if field_type == "name":
                self.permission_data[count]["name"] = value
            if field_type == "individuals":
                self.permission_data[count]["individuals"] = value
            if field_type == "roles":
                self.permission_data[count]["roles"] = value

            if field_type == "configurablefield":
                configurablefieldname = fieldname_pieces[2]
                self.permission_data[count]["configurable fields"][configurablefieldname] = value

    def get_permissions_dict(self):

        self.process_permissions()

        # FIXME: assumes a single permission, just returns the first it finds

        for index, permission in self.permission_data.items():

            if "individuals" in permission:
                p_actors = [int(actor) for actor in permission["individuals"]]
            else:
                p_actors = []

            p_roles = permission["roles"] if  "roles" in permission and permission["roles"] else []

            if p_actors or p_roles:

                config_dict = {}
                if hasattr(permission, "configurable_fields"):
                    for cf_key, cf_value in permission["configurable_fields"].items():
                        config_dict[cf_key] = cf_value

                return json.dumps({ 'permission_type': permission['name'], 
                    'permission_actors': p_actors, 'permission_roles': p_roles,
                    'permission_configuration': config_dict})

    def get_configuration_dict(self):
        configuration_dict = {}
        for field in self.condition_model._meta.fields:
            if field.name in self.condition_fields:
                configuration_dict.update({field.name: self.cleaned_data[field.name]})
        return json.dumps(configuration_dict)


class ApprovalConditionForm(BaseConditionForm):

    condition_model = ApprovalCondition
    condition_type = "approvalcondition"
    condition_fields = ['self_approval_allowed']


class VotingConditionForm(BaseConditionForm):

    condition_model = VoteCondition
    condition_type = "votecondition"
    condition_fields = ['allow_abstain', 'require_majority', 'publicize_votes', 'voting_period']


conditionFormDict = {
    "approvalcondition": ApprovalConditionForm,
    "votecondition": VotingConditionForm
}

