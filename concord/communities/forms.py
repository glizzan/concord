from django import forms
from django.utils.translation import gettext as _

from concord.communities.client import CommunityClient


class LeadershipForm(forms.Form):

    def __init__(self, *args, **kwargs):

        self.instance = kwargs.pop('instance')
        self.request = kwargs.pop('request')
        super().__init__(*args, **kwargs)

        from concord.communities.client import CommunityClient
        self.commClient = CommunityClient(actor=self.request.user.username, target=self.instance)
        ROLE_CHOICES = [(role,role) for role in self.commClient.get_assigned_roles()]

        # Set up owner list ('ol') fields
        owners = self.instance.list_owners()
        initial_individuals = " ".join(owners['actors'])
        initial_roles = [role_pair.split("_")[1] for role_pair in owners['roles']]
        self.fields["ol_individuals"] = forms.CharField(label="Individual Owners", 
                initial=initial_individuals, required=False)
        self.fields["ol_roles"] = forms.MultipleChoiceField(label="Owner Roles", 
                required=False, choices=ROLE_CHOICES)
        self.fields["ol_roles"].initial = initial_roles

        # Set up governor list ('gl') fields
        governors = self.instance.list_governors()
        initial_individuals = " ".join(governors['actors'])
        initial_roles = [role_pair.split("_")[1] for role_pair in governors['roles']]
        self.fields["gl_individuals"] = forms.CharField(label="Individual Governors", 
                initial=initial_individuals, required=False)
        self.fields["gl_roles"] = forms.MultipleChoiceField(label="Governor Roles", 
                required=False, choices=ROLE_CHOICES)
        self.fields["gl_roles"].initial = initial_roles

        # Get condition data for owners
        # type of condition, once type is selected: configuration, plus permissions
        # sooo do we want this all part of the same form?  Or should this be AJAXy?



        # Get condition data for governors

    def process_data(self):

        leadership_data = {
            "ol": { "individuals": [], "roles": [] },
            "gl": { "individuals": [], "roles": [] },
            "oc": [],
            "gc": []
        }

        # Process owner list data
        if self.cleaned_data['ol_individuals']:
            leadership_data["ol"]["individuals"] = self.cleaned_data['ol_individuals'].split(" ")
        if self.cleaned_data["ol_roles"]:
            leadership_data["ol"]["roles"] = self.cleaned_data['ol_roles']

        # Process governor list data
        if self.cleaned_data['gl_individuals']:
            leadership_data["gl"]["individuals"] = self.cleaned_data['gl_individuals'].split(" ")
        if self.cleaned_data["gl_roles"]:
            leadership_data["gl"]["roles"] = self.cleaned_data['gl_roles']

        # Process owner condition data

        # Process governor condition data

        return leadership_data

    def save(self):
        leadership_data = self.process_data()
        self.commClient.update_owners(new_owner_data=leadership_data["ol"])
        self.commClient.update_governors(new_governor_data=leadership_data["gl"])
        # Save owner condition data
        # Save governor condition data


class RoleForm(forms.Form):

    def __init__(self, *args, **kwargs):

        self.instance = kwargs.pop('instance')
        self.request = kwargs.pop('request')
        super().__init__(*args, **kwargs)

        # Get list of existing roles and generate fields
        count = 0
        for role_name, members in self.instance.roleset.get_assigned_roles().items():

            self.fields['%s~rolename' % count] = forms.CharField(label="Role Name", 
                initial=role_name, required=True)
            
            self.fields['%s~members' % count] = forms.CharField(label="Members", 
                initial=" ".join(members), required=False, 
                help_text="members must be separated by spaces")            

            count += 1

        # Add an additional blank row in case user wants to add a role
        self.fields['%s~rolename' % count] = forms.CharField(label="Role Name", required=False)
        self.fields['%s~members' % count] = forms.CharField(label="Members", 
            required=False, help_text="members must be separated by spaces")

    def process_roles(self):
        """Process form fields into roles"""
        # TODO: save as namedtuples not dicts, possibly
        role_data = {}
        for key, value in self.cleaned_data.items():
            count, field_type = key.split("~")
            if count not in role_data:
                role_data[count] = {}
            if field_type == "rolename":
                role_data[count]["rolename"] = value
            if field_type == "members":
                role_data[count]["members"] = value.strip()                

        # Not the best place for this, but.  Deletes empty fields.
        for key in list(role_data.keys()):
            if role_data[key]["rolename"] == "":
                del role_data[key]
        
        return role_data

    def save(self):

        role_data = self.process_roles()
        commClient = CommunityClient(actor=self.request.user.username, target=self.instance)
        commClient.update_roles(role_data=role_data)
        commClient.update_role_membership(role_data=role_data)
