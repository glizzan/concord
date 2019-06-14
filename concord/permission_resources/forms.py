from collections import namedtuple

from django import forms
from django.utils.translation import gettext as _

from concord.communities.client import CommunityClient
from concord.resources.client import ResourceClient
from concord.permission_resources.client import PermissionResourceClient
from concord.permission_resources.models import PermissionsItem


class PermissionForm(forms.Form):
    """"""

    def __init__(self, *args, **kwargs):

        self.instance = kwargs.pop('instance')
        self.request = kwargs.pop('request')
        super().__init__(*args, **kwargs)

        # Get roles set on owner of instance, and format for choicefield
        from concord.communities.client import CommunityClient
        if hasattr(self.instance, "is_community") and self.instance.is_community:
            self.commClient = CommunityClient(actor="system", target=self.instance)
        else: 
            self.commClient = CommunityClient(actor="system")
            owner_community = self.commClient.get_owner(owned_object=self.instance)
            self.commClient.set_target(target=owner_community)
        # TODO: handle individually owned resources
            
        ROLE_CHOICES = [(role,role) for role in self.commClient.get_assigned_roles()]

        # Get permissions 
        self.prClient = PermissionResourceClient(actor=self.request.user.username, 
            target=self.instance)

        for count, change_type in enumerate(self.prClient.get_settable_permissions(return_format="list_of_strings")):
             
            self.fields['%s_name' % count] = forms.CharField(
                label="Permission type", required=True, initial=change_type,
                widget=forms.widgets.Textarea(attrs={'readonly':'True', 
                    'rows': 2, 'cols':40}))
            
            self.fields['%s_individuals' % count] = forms.CharField(
                label="Individuals with this permission", required=False)

            self.fields['%s_roles' % count] = forms.MultipleChoiceField(
                    label="Roles with this permission", 
                    required=False, choices=ROLE_CHOICES)

            permission = self.prClient.get_specific_permissions(change_type=change_type)
            if permission:
                self.fields['%s_individuals' % count].initial = permission[0].get_actor_names()
                self.fields['%s_roles' % count].initial = permission[0].get_role_names()

    def process_permissions(self):
        """Process form fields into a dict with key change_type"""
        permission_data = {}
        for key, value in self.cleaned_data.items():
            count, field_type = key.split("_")
            if count not in permission_data:
                permission_data[count] = {}
            if field_type == "name":
                permission_data[count]["name"] = value
            if field_type == "individuals":
                permission_data[count]["individuals"] = value
            if field_type == "roles":
                permission_data[count]["roles"] = value
            
        return permission_data

    def save(self):

        # Get owner community
        owner_community = self.commClient.get_owner(owned_object=self.instance)
        # Process form fields into dict
        form_permission_data = self.process_permissions()
        
        for count, form_permission in form_permission_data.items():

            db_permission = self.prClient.get_specific_permissions(change_type=form_permission["name"])

            if db_permission:  

                # if permission item exists, update it
                self.prClient.update_roles_on_permission(role_data=form_permission["roles"], 
                    permission=db_permission[0], owner=owner_community)
                self.prClient.update_actors_on_permission(actor_data=form_permission["individuals"],
                    permission=db_permission[0])

            else:

                # If it doesn't exist, but there's relevant form data, create a
                # permission using the form data.
                if form_permission["individuals"] or form_permission["roles"]:
                    role_pairs = []
                    for role in form_permission["roles"]:
                        role_pairs.append("_".join([str(owner_community.pk), role]))
                    if "," in form_permission["individuals"]:
                        raise ValueError("Actors in permission forms must be separated by spaces only")
                    actors = form_permission["individuals"].split(" ")
                    self.prClient.add_permission(permission_type=form_permission["name"],
                        permission_actors=actors, permission_role_pairs=role_pairs)                    
                else:
                    continue # If no data in form either, just move on


class MetaPermissionForm(forms.Form):
    """Handles permission on a permission item"""

    def __init__(self, *args, **kwargs):

        self.target_permission = kwargs.pop('instance')
        self.request = kwargs.pop('request')  
        super().__init__(*args, **kwargs)

        # Get owner of permitted object
        permitted_object = self.target_permission.get_permitted_object()
        self.owned_by_community = True if permitted_object.owner_type == "com" else False

        if self.owned_by_community:
            commClient = CommunityClient(actor="system")
            self.owner = commClient.get_owner(
                owned_object=self.target_permission.get_permitted_object())
            commClient.set_target(target=self.owner)
            ROLE_CHOICES = [(role,role) for role in commClient.get_assigned_roles()]

        # Get permissions 
        self.prClient = PermissionResourceClient(target=PermissionsItem,
            actor=self.request.user.username)
        settable_permissions = self.prClient.get_settable_permissions(return_format="list_of_strings")

        for count, change_type in enumerate(settable_permissions):
            
            self.fields['%s_name' % count] = forms.CharField(
                label="Permission type", required=True, initial=change_type,
                widget=forms.widgets.Textarea(attrs={'readonly':'True', 
                    'rows': 2, 'cols':40}))
            
            self.fields['%s_individuals' % count] = forms.CharField(
                label="Individuals with this permission", required=False)

            if self.owned_by_community:
                self.fields['%s_roles' % count] = forms.MultipleChoiceField(
                        label="Roles with this permission", 
                        required=False, choices=ROLE_CHOICES)

            # If permission already exists, check for metapermissions
            if type(self.target_permission) == PermissionsItem:
                self.prClient.set_target(self.target_permission)
                metapermission = self.prClient.get_specific_permissions(change_type=change_type)
                if metapermission:
                    self.fields['%s_individuals' % count].initial = metapermission[0].get_actor_names()
                    if self.owned_by_community:
                        self.fields['%s_roles' % count].initial = metapermission[0].get_role_names()        

    def process_permissions(self):
        """Process form fields into a dict with key change_type"""
        permission_data = {}
        for key, value in self.cleaned_data.items():
            count, field_type = key.split("_")
            if count not in permission_data:
                permission_data[count] = {}
            if field_type == "name":
                permission_data[count]["name"] = value
            if field_type == "individuals":
                permission_data[count]["individuals"] = value
            if field_type == "roles":
                permission_data[count]["roles"] = value
        return permission_data

    # NOTE: this duplicates a LOT from permission form, refactor?
    def save(self):

        form_permission_data = self.process_permissions()

        # If any metapermissions are set, yet no target permission exists, 
        # create it and set as target_permission and prc target.
        if len(form_permission_data) > 0 and type(self.target_permission) != PermissionsItem:
            self.target_permission = self.target_permission.create_self()
            self.prClient.set_target(self.target_permission)

        for count, form_permission in form_permission_data.items():

            db_permission = self.prClient.get_specific_permissions(change_type=form_permission["name"])

            if db_permission:  

                # if permission item exists, update it
                if self.owned_by_community:
                    self.prClient.update_roles_on_permission(role_data=form_permission["roles"], 
                        permission=db_permission[0], owner=self.owner)
                self.prClient.update_actors_on_permission(actor_data=form_permission["individuals"],
                    permission=db_permission[0])

            else:

                # If it doesn't exist, but there's relevant form data, create a
                # permission using the form data.
                role_pairs = []
                if self.owned_by_community and form_permission["roles"]:
                    for role in form_permission["roles"]:
                        role_pairs.append("_".join([str(self.owner.pk), role]))

                actors = []
                if form_permission["individuals"]:
                    actors = form_permission["individuals"].split(" ")
                
                if actors or role_pairs:
                    self.prClient.add_permission(permission_type=form_permission["name"],
                        permission_actors=actors, permission_role_pairs=role_pairs)                    
                else:
                    continue # If no data in form either, just move on


class AccessForm(forms.Form):
    """Possibly deprecated form which combines permissions form and
    role change form into one."""

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance')
        self.request = kwargs.pop('request')
        super().__init__(*args, **kwargs)

        # Get permissions & reformat as choices
        prClient = PermissionResourceClient(actor=self.request.user.username, 
            target=self.instance)
        PERMISSION_CHOICES = tuple(prClient.get_settable_permissions())

        # Gets roleset and creates role fields on form, if instance is community or 
        # community-owned object, otherwise skip.
        if self.instance.owner_type is not "ind":

            # If a community, get community's roleset & PR. If community-owned object,
            # get owner community's roleset & PR
            if hasattr(self.instance, "is_community") and self.instance.is_community:
                community = self.instance
                roleset = self.instance.roleset
            else:
                from concord.communities.client import CommunityClient
                community = CommunityClient(actor="system").get_owner(owned_object=self.instance)
                roleset = community.roleset                
        
            # Create set of fields for each role
            count = 0
            for role_name, members in roleset.get_assigned_roles().items():

                self.fields['%s_rolename' % count] = forms.CharField(label="Role Name", 
                    initial=role_name, required=False)
                
                self.fields['%s_members' % count] = forms.CharField(label="Members", 
                    initial=", ".join(members), required=False)

                # Look for existing permissions for this role
                permissions = prClient.get_permissions_associated_with_role(
                    role_name=role_name, community=community) 
                self.fields['%s_permissions' % count] = forms.MultipleChoiceField(
                    label="Permissions", required=False, choices=PERMISSION_CHOICES,
                    initial=[p.change_type for p in permissions])

                count += 1

                # Add an additional blank row in case user wants to add a role
                # TODO: refactor this to use formsets
                self.fields['%s_rolename' % count] = forms.CharField(label="Role Name", required=False)
                self.fields['%s_members' % count] = forms.CharField(label="Members", required=False)
                self.fields['%s_permissions' % count] = forms.MultipleChoiceField(
                        label="Permissions", required=False, choices=PERMISSION_CHOICES)

        # TODO: Gets non-role permissions and creates fields on form.

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
            if field_type == "permissions":
                role_data[count]["permissions"] = value

        # Not the best place for this, but.  Deletes empty fields.
        for key in list(role_data.keys()):
            if role_data[key]["rolename"] == "":
                del role_data[key]
        
        return role_data

    def save(self):

        # Process form fields into dict
        role_data = self.process_roles()

        # Set clients depending on if target is community, community owned resource,
        # or individually owned resource.
        if hasattr(self.instance, "is_community"):
            ownerClient = CommunityClient(actor=self.request.user.username, target=self.instance)
            permissionClient = PermissionResourceClient(actor=self.request.user.username, target=self.instance)
        else:
            ownerClient = CommunityClient(actor=self.request.user.username)
            owning_community = ownerClient.get_owner(owned_object=self.instance)
            ownerClient.set_target(target=owning_community)
            permissionClient = PermissionResourceClient(actor=self.request.user.username, target=self.instance)

        # Process role metadata.  Create role if it doesn't exist.
        actions, results = ownerClient.update_roles(role_data=role_data)

        # For each role, update membership.  Add members if new, remove members who
        # are no longer there.
        actions, results = ownerClient.update_role_membership(role_data=role_data)

        # For each role, update permissions.  Add permissions if new, remove if gone.
        actions, results = permissionClient.update_role_permissions(
            role_data=role_data, owner=ownerClient.target)

        # TODO: handle non-role permissions data
