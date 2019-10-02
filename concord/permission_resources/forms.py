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
        '''Determine's owner of an instance passed to a form.  Handles instances of permissions,
        communities, and non-community objects differently.  After this method is called, 
        self.owner, self.commClient, and self.owned_by_community should be available to the form.'''

        from concord.communities.client import CommunityClient
        self.commClient = CommunityClient(actor="system")

        if not owned_object:
            owned_object = self.instance

        # If the instance is a permission, get owner of permitted object
        if type(owned_object).__name__ == "PermissionsItem":  # FIXME: this won't work
            permitted_object = owned_object.get_permitted_object()
            if permitted_object.owner_type == "com":
                self.owner = self.commClient.get_owner(
                    owned_object=owned_object.get_permitted_object())
                self.owned_by_community = True
            else:
                self.owner = permitted_object.get_owner()  # Gets indv owner
                self.owned_by_community = False
            return

        # If the instance is a community, owner is self, otherwise owner is owner community.        
        if hasattr(owned_object, "is_community") and owned_object.is_community:
            self.owner = owned_object
            self.owned_by_community = True
        else: 
            self.owner = self.commClient.get_owner(owned_object=owned_object)
            self.owned_by_community = True  # Not 100% sure this is true
        
        # TODO: handle individually owned resources

    # NOTE: this was originally a separate mixin and may need to be again
    def set_role_choices(self):

        if self.owned_by_community:
            self.commClient.set_target(target=self.owner)
            self.ROLE_CHOICES = [(role,role) for role in self.commClient.get_assigned_roles()]
        else:
            self.ROLE_CHOICES = None

    def get_settable_permissions(self):
        # content of return format doesn't matter, just overrides default
        return self.prClient.get_settable_permissions(return_format="permission_objects")  

    def initialize_permission_fields(self):
        '''Called in the init method of a form, adds permission field for the target instance.'''
        # TODO: possibly allow user to pass in a custom target, not just assuming selfl.instance?

        self.prClient = PermissionResourceClient(actor=self.request.user.username, 
            target=self.instance)

        for count, permission in enumerate(self.get_settable_permissions()):      

            self.fields['%s~name' % count] = forms.CharField(
                label="Permission type", required=True, initial=permission.get_change_type(),
                widget=forms.widgets.Textarea(attrs={'readonly':'True', 
                    'rows': 2, 'cols':40}))
            
            self.fields['%s~individuals' % count] = forms.CharField(
                label="Individuals with this permission", required=False)

            if self.ROLE_CHOICES:
                self.fields['%s~roles' % count] = forms.MultipleChoiceField(
                        label="Roles with this permission", 
                        required=False, choices=self.ROLE_CHOICES)

            for field in permission.get_configurable_fields():
                self.fields['%s~configurablefield~%s' % (count, field)] = forms.CharField(
                    label="Configurable: %s" % (field), required=False)

            # Add initial values from existing ("specific") permissions.
            specific_permissions = self.prClient.get_specific_permissions(change_type=permission.get_change_type())
            for specific_permission in specific_permissions:
                self.fields['%s~individuals' % count].initial = specific_permission.get_actor_names()    
                for key, value in specific_permission.get_configuration().items():
                    fieldname = "%s~configurablefield~%s" % (count, key)
                    if fieldname in self.fields:
                        self.fields[fieldname].initial = value
                if self.ROLE_CHOICES:
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
                self.permission_data[count]["individuals"] = value
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

                newClient = PermissionResourceClient(actor=self.request.user.username, 
                    target=db_permission[0])
                if self.ROLE_CHOICES:
                    newClient.update_roles_on_permission(role_data=form_permission["roles"], 
                        permission=db_permission[0], owner=self.owner)
                newClient.update_actors_on_permission(actor_data=form_permission["individuals"],
                    permission=db_permission[0])
                newClient.update_configuration(configuration_dict=form_permission["configurable fields"], 
                    permission=db_permission[0])

            else:   # Otherwise, create it.

                # Only create permission if there's relevant form data.

                if form_permission["individuals"] or form_permission["roles"]:

                    role_pairs = []
                    for role in form_permission["roles"]:
                        role_pairs.append("_".join([str(self.owner.pk), role]))
                    
                    if "," in form_permission["individuals"]:
                        raise ValueError("Actors in permission forms must be separated by spaces only")
                    actors = form_permission["individuals"].split(" ")
                    
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
        self.set_role_choices()  
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
        self.set_role_choices()  
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
        