from django import forms
from django.utils.translation import gettext as _

from concord.communities.client import CommunityClient
from concord.resources.client import ResourceClient
from concord.permission_resources.client import PermissionResourceClient


class AccessForm(forms.Form):

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance')
        self.request = kwargs.pop('request')
        super().__init__(*args, **kwargs)

        # Get permissions & reformat as choices
        PERMISSION_CHOICES = tuple(self.instance.get_settable_permissions())

        # Create set of fields for each role
        count = 0
        for role_name, members in self.instance.roleset.get_assigned_roles().items():

            self.fields['%s_rolename' % count] = forms.CharField(label="Role Name", 
                initial=role_name, required=False)
            
            self.fields['%s_members' % count] = forms.CharField(label="Members", 
                initial=", ".join(members), required=False)

            # Look for existing permissions for this role
            client = PermissionResourceClient(actor=self.request.user.username)
            permissions = client.get_permissions_associated_with_role(
                target=self.instance, role_name=role_name,
                community=self.instance) # TODO: should be community that owns instance

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

    def get_client(self):
        """Get client depending on instance type"""
        if hasattr(self.instance, "is_communuty") and \
            self.instance.is_communuty:
            client = CommunityClient(actor=self.request.user.username) 
        else:
            client = ResourceClient(actor=self.request.user.username)        
        client.set_target(target=self.instance)
        return client 

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

        # Not the best place for this, but.
        for key in list(role_data.keys()):
            if role_data[key]["rolename"] == "":
                del role_data[key]
        
        return role_data

    def save_resource(self, client, role_data):
        Raise("Called save_resource when you shouldn't have!")

    def save_community(self, client, role_data):

        existing_roles = client.get_assigned_roles(community_pk=self.instance.pk)
        # TODO: set permclient when we set commclient
        permClient = PermissionResourceClient(actor=self.request.user.username)
        permClient.set_target(self.instance)
        perms_on_object = permClient.get_all_permissions_on_object(target=self.instance)

        # NOTE: this is goddamn absurd, maybe make this a cleaner method on client?

        for index, role in role_data.items():

            # Check if role exists, if not make it
            if role["rolename"] not in existing_roles:
                client.add_assigned_role(role_name=role["rolename"])

            # Add or remove people from role as needed
            member_data = role["members"].split(", ")
            previous_members = client.get_users_given_role(role_name=role["rolename"])
            people_to_add = list(set(member_data).difference(set(previous_members)))
            people_to_remove = list(set(previous_members).difference(set(member_data)))
            if people_to_add:
                client.add_people_to_role(role["rolename"], people_to_add)
            if people_to_remove:
                client.remove_people_from_role(role["rolename"], people_to_remove)

            # Add or remove permissions as needed

            permission_data = role["permissions"]   # format: list of strings of full changetypes
            previous_permissions = permClient.get_permissions_associated_with_role(
                target=self.instance, role_name=role["rolename"], community=self.instance) # queryset

            permissions_to_remove = []
            for permission in previous_permissions:
                if permission.change_type in permission_data:
                    permission_data.remove(permission.change_type)
                else:
                    permissions_to_remove.append(permission)

            # If we've got an extra permission, remove it.
            for permission in permissions_to_remove:
                permClient.remove_role_from_permission(role_name=role["rolename"], 
                    community=self.instance, permission=permission)

            # If we're missing a new permission, add it
            for permission in permission_data:
                if permission in perms_on_object:
                    # add role to existing permission
                    permClient.add_role_to_permission(role_name=role["rolename"],
                        community_pk=str(self.instance.pk), permission=permission)
                else:
                    # create entirely new permission and assign role
                    role_pair = str(self.instance.pk) + "_" + role["rolename"]
                    action, new_permission = permClient.add_permission(permission_type=permission, 
                        permission_role=role_pair)
            
        # Delete roles that no longer exist
        # FIXME: check that this is correct -- will role_data cover all roles in community?
        new_roles = [role["rolename"] for index, role in role_data.items()]
        roles_to_delete = list(set(existing_roles).difference(set(new_roles)))
        for deprecated_role in roles_to_delete:
            action, result = client.remove_assigned_role(role_name=deprecated_role)
            # Remove role from permission (this is inefficient too)
            for permission in perms_on_object:
                # role_pair = str(self.instance.pk) + " " + deprecated_role  # self.instance != self.community
                permClient.remove_role_from_permission(role_name=deprecated_role, 
                    community_pk=str(self.instance.pk), permission=str(permission.pk))



    def save(self):

        role_data = self.process_roles()

        if hasattr(self.instance, "is_community"):
            client = CommunityClient(actor=self.request.user.username) 
            client.set_target(target=self.instance)
            self.save_community(client=client, role_data=role_data)
        else:
            client = ResourceClient(actor=self.request.user.username)
            client.set_target(target=self.instance)
            self.save_resource(client=client, role_data=role_data)


        

 