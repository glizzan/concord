from collections import namedtuple

from django import forms
from django.utils.translation import gettext as _

from concord.communities.client import CommunityClient
from concord.resources.client import ResourceClient
from concord.permission_resources.client import PermissionResourceClient
from concord.permission_resources.models import PermissionsItem


class PermissionFormMixin(object):
    '''This mixin can be added to forms that rely on permissions, including the forms in this file.'''

    # NOTE: this was originally a separate mixin and may need to be again
    def determine_owner(self, owned_object=None):
        '''Determine's owner of an instance passed to a form.  Handles instances of 
        permissions, differently - the owner there is the permission target's owner.  
        Afterwards, self.owner & self.commClient should be available to the form.'''

        from concord.communities.client import CommunityClient
        self.commClient = CommunityClient(system=True)

        if not owned_object:
            owned_object = self.instance

        if type(owned_object).__name__ == "PermissionsItem":  # FIXME: this won't work
            # If the instance is a permission, get owner of permitted object
            permitted_object = owned_object.get_permitted_object()
            self.owner = permitted_object.get_owner()
        else:
            self.owner = owned_object.get_owner()

    # NOTE: this was originally a separate mixin and may need to be again
    def set_choices(self):
        self.commClient.set_target(target=self.owner)
        self.ROLE_CHOICES = [(role,role) for role in self.commClient.get_roles()]
        self.ACTOR_CHOICES = [(user.pk, user.username) for user in self.commClient.get_members()]

    def get_settable_permissions(self):
        # content of return format doesn't matter, just overrides default
        return self.prClient.get_settable_permissions(return_format="permission_objects")  

    def initialize_permission_fields(self):
        '''Called in the init method of a form, adds permission field for the target instance.'''
        # TODO: possibly allow user to pass in a custom target, not just assuming self.instance?

        self.prClient = PermissionResourceClient(actor=self.request.user, 
            target=self.instance)

        for count, permission in enumerate(self.get_settable_permissions()):      

            self.fields['%s~name' % count] = forms.CharField(
                label="Permission type", required=True, initial=permission.get_change_type(),
                widget=forms.widgets.Textarea(attrs={'readonly':'True', 
                    'rows': 2, 'cols':40}))
            
            self.fields['%s~individuals' % count] = forms.MultipleChoiceField(
                label="Individuals with this permission", required=False,
                choices=self.ACTOR_CHOICES)

            self.fields['%s~roles' % count] = forms.MultipleChoiceField(
                label="Roles with this permission", required=False, 
                choices=self.ROLE_CHOICES)

            for field in permission.get_configurable_fields():
                self.fields['%s~configurablefield~%s' % (count, field)] = forms.CharField(
                    label="Configurable: %s" % (field), required=False)

            # Add initial values from existing ("specific") permissions.
            specific_permissions = self.prClient.get_specific_permissions(change_type=permission.get_change_type())
            for specific_permission in specific_permissions:
                self.fields['%s~individuals' % count].initial = specific_permission.get_actors()    
                for key, value in specific_permission.get_configuration().items():
                    fieldname = "%s~configurablefield~%s" % (count, key)
                    if fieldname in self.fields:
                        self.fields[fieldname].initial = value
                self.fields['%s~roles' % count].initial = specific_permission.get_role_names()

    def process_permissions(self):
        """Process form fields into a dict with key change_type"""

        self.permission_data = {}
        for key, value in self.cleaned_data.items():
        
            fieldname_pieces = key.split("~")  
        
            count = fieldname_pieces[0]
            if count not in self.permission_data:
                self.permission_data[count] = {"configurable fields": {}}

            field_type = fieldname_pieces[1]

            if field_type == "name":
                self.permission_data[count]["name"] = value
            if field_type == "individuals":
                self.permission_data[count]["individuals"] = [int(pk) for pk in value]
            if field_type == "roles":
                self.permission_data[count]["roles"] = value

            if field_type == "configurablefield":
                configurablefieldname = fieldname_pieces[2]
                self.permission_data[count]["configurable fields"][configurablefieldname] = value
    
    def save_permissions(self):
        """Goes through processed permissions data from the form, and creates relevants state
        changes."""

        for count, form_permission in self.permission_data.items():

            db_permission = self.prClient.get_specific_permissions(change_type=form_permission["name"])

            if db_permission:  # If permission item exists, update it.

                newClient = PermissionResourceClient(actor=self.request.user, 
                    target=db_permission[0])
                newClient.update_roles_on_permission(role_data=form_permission["roles"], 
                        permission=db_permission[0], owner=self.owner)
                newClient.update_actors_on_permission(actor_data=form_permission["individuals"],
                    permission=db_permission[0])
                newClient.update_configuration(configuration_dict=form_permission["configurable fields"], 
                    permission=db_permission[0])

            else:   # Otherwise, create it.

                # Only create permission if there's relevant form data.

                if "individuals" in form_permission and form_permission["individuals"]:
                    actors = form_permission["individuals"]
                else:
                    actors = []                
                
                if "roles" in form_permission and form_permission["roles"]:
                    role_pairs = []
                    for role in form_permission["roles"]:
                        role_pairs.append("_".join([str(self.owner.pk), role]))
                else:
                    role_pairs = []
                    
                if actors or role_pairs:
                    
                    permission_configuration = {}
                    for cf_key, cf_value in form_permission["configurable fields"].items():
                        permission_configuration[cf_key] = cf_value
                    
                    action, result = self.prClient.add_permission(permission_type=form_permission["name"],
                        permission_actors=actors, permission_role_pairs=role_pairs,
                        permission_configuration=permission_configuration)

                else:
                    continue   # If no relevant data in the form, just move on


class PermissionForm(PermissionFormMixin, forms.Form):

    def __init__(self, *args, **kwargs):

        self.instance = kwargs.pop('instance')
        self.request = kwargs.pop('request')
        super().__init__(*args, **kwargs)

        self.determine_owner()  
        self.set_choices()  
        self.initialize_permission_fields() 

    def save(self):

        self.process_permissions()
        self.save_permissions()


class MetaPermissionForm(PermissionFormMixin, forms.Form):
    
    # TODO: possibly create a default method for instantiating the PRC client which this form overrides?

    def __init__(self, *args, **kwargs):

        self.instance = kwargs.pop('instance')
        self.request = kwargs.pop('request')
        super().__init__(*args, **kwargs)

        self.determine_owner() 
        self.set_choices()  
        self.initialize_permission_fields()

    def get_settable_permissions(self):
        '''Occasionally metapermission form will be passed a mock permission object.  We need to 
        override get_settable_permissions to handle that case.'''

        # FIXME: I really do not like this hack, specifically how we're juggling the target of prClient,
        # but we need to set the target back to Mock so that the client can check for it. (UGH.)

        if type(self.instance).__name__ == "MockMetaPermission":
            from concord.permission_resources.models import PermissionsItem
            self.prClient.set_target(target=PermissionsItem)  
            settable_permissions = self.prClient.get_settable_permissions(return_format="permission_objects")
            self.prClient.set_target(target=self.instance)
            return settable_permissions

        return self.prClient.get_settable_permissions(return_format="permission_objects")  

    def save(self):

        self.process_permissions()

        # If any metapermissions are set, yet no target permission exists, create & set as target.
        if len(self.permission_data) > 0 and type(self.instance) != PermissionsItem:
            self.instance = self.instance.create_self(owner=self.owner)
            self.prClient.set_target(self.instance)

            # BUG: should the owner of the new permission be the actor, or the owner of the community?

        self.save_permissions()
        