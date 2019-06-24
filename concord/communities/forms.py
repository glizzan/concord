from django import forms
from django.utils.translation import gettext as _

from concord.communities.client import CommunityClient


class RoleForm(forms.Form):

    def __init__(self, *args, **kwargs):

        self.instance = kwargs.pop('instance')
        self.request = kwargs.pop('request')
        super().__init__(*args, **kwargs)

        # Get list of existing roles and generate fields
        count = 0
        for role_name, members in self.instance.roleset.get_assigned_roles().items():

            self.fields['%s_rolename' % count] = forms.CharField(label="Role Name", 
                initial=role_name, required=True)
            
            self.fields['%s_members' % count] = forms.CharField(label="Members", 
                initial=" ".join(members), required=False, 
                help_text="members must be separated by spaces")            

            count += 1

        # Add an additional blank row in case user wants to add a role
        self.fields['%s_rolename' % count] = forms.CharField(label="Role Name", required=False)
        self.fields['%s_members' % count] = forms.CharField(label="Members", 
            required=False, help_text="members must be separated by spaces")

    def process_roles(self):
        """Process form fields into roles"""
        # TODO: save as namedtuples not dicts, possibly
        role_data = {}
        for key, value in self.cleaned_data.items():
            count, field_type = key.split("_")
            if count not in role_data:
                role_data[count] = {}
            if field_type == "rolename":
                role_data[count]["rolename"] = value
            if field_type == "members":
                role_data[count]["members"] = value

        # Not the best place for this, but.  Deletes empty fields.
        for key in list(role_data.keys()):
            if role_data[key]["rolename"] == "":
                del role_data[key]
        
        return role_data

    def save(self):

        role_data = self.process_roles()
        commClient = CommunityClient(actor=self.request.user.username, target=self.instance)
        actions, results = commClient.update_roles(role_data=role_data)
        actions, results = commClient.update_role_membership(role_data=role_data)

