import json

from django.db import models


class RoleHandler(object):
    '''
    Every community has a list of roles, which are set community-wide.  People with the
    relevant permissions can add and remove roles, and add or remove people from roles.

    There are three protected names which cannot be used: owners, governors, and members.
    
    A person cannot be added as owner, governor or custom role unless they're already a member.  
    '''

    members = []
    owners = {}
    governors = {}
    custom_roles = {}
    protected_roles = ["owners", "governors", "members"]

    def __init__(self, *, members=None, owners=None, governors=None, custom_roles=None):

        if members:
            self.validate_members(members=members)
        self.members = members if members else []

        if custom_roles:
            self.validate_custom_roles(custom_roles=custom_roles)
        self.custom_roles = custom_roles if custom_roles else {}

        if owners:
            self.validate_owners(owners=owners)
        self.owners = owners if owners else {'actors': [], 'roles': []}
        
        if governors:
            self.validate_governors(governors=governors)
        self.governors = governors if governors else {'actors': [], 'roles': []}

    def initialize_with_creator(self, creator):
        '''To be valid, the RoleHandler must have at least one member and one owner.  The most
        common use case is that the creator of a community is the only member and only owner
        upon initialization, which this help method allows us to accomplish.  We also add the
        creator to the governors as well.  Most commonly used after RoleHandler is
        initialized with no data passed in.'''
        self.members.append(creator)
        self.owners['actors'].append(creator)
        self.governors['actors'].append(creator)
    
    ##########################
    ### Validation Methods ###
    ##########################

    def validate_members(self, members):
        '''Members should be a list of integers.  For now, we do not check that these are
        real users.'''
        if type(members) is not list:
            raise TypeError("Members must be supplied as a list.")
        if not members:
            raise ValueError("Members list must contain at least one member.")
        if type(members[0]) is not int:
            raise TypeError("Individual members in list must be integers.")

    def validate_owners(self, owners):
        '''
        Owners dict should look like: 

        { 'actors': [1,2,3], 'roles': ['knights', 'bishops', 'rooks'] }
        
        All actors must be members and all roles must be a protected role or custom role. 
        '''

        if set(owners.keys()) != set(["actors", "roles"]):
            raise KeyError("Owners must be a dict with keys 'actors' and 'roles', not %s" % ", ".join(owners.keys()))
        
        for actor in owners["actors"]:
            if type(actor) is not int:
                raise TypeError("Actor ", actor, " must be supplied as integer.")
            if not self.is_member(actor):
                raise ValueError("Actor ", actor, " must be added as member before they can be an owner.")
        
        for role in owners["roles"]:
            if type(role) is not str:
                raise TypeError("Role ", role, " must be supplied as string.")
            if not self.is_role(role):
                raise ValueError("Role ", role, " must be added as a custom role before it can be assigned ownership.")

    def validate_governors(self, governors):
        '''
        Governors dict should look like: 

        { 'actors': [1,2,3], 'roles': ['knights', 'bishops', 'rooks'] }
        
        All actors must be members and all roles must be a protected role or custom role. 
        '''

        if set(governors.keys()) != set(["actors", "roles"]):
            raise KeyError("Governors must be a dict with keys 'actors' and 'roles', not %s" % ", ".join(governors.keys()))
        
        for actor in governors["actors"]:
            if type(actor) is not int:
                raise TypeError("Actor ", actor, " must be supplied as integer.")
            if not self.is_member(actor):
                raise ValueError("Actor ", actor, " must be added as member before they can be a governor.")
        
        for role in governors["roles"]:
            if type(role) is not str:
                raise TypeError("Role ", role, " must be supplied as string.")
            if not self.is_role(role):
                raise ValueError("Role ", role, " must be added as a custom role before it can be assigned governorship.")

    def validate_custom_roles(self, custom_roles):
        '''
        Custom roles dict should look like:

        { 'knights': [1,2,3], 'rooks': [2,3,4] }
        
        All items in each list must correspond to members pks.
        '''

        for role_name, role_actors in custom_roles.items():
            if role_name in self.protected_roles:
                raise ValueError("The role name ", role_name, " is protected, please pick a different name.")
            if type(role_actors) is not list:
                raise TypeError("Actors must be supplied to role in RoleDict in a list.")
            for actor in role_actors:
                if type(actor) is not int:
                    raise TypeError("Actor ", actor, " must be supplied as integer.")     
                if not self.is_member(actor):
                    raise ValueError("Actor ", actor, " must be added as member before they can be assigned a custom role.")

    def validate_role_handler(self):

        self.validate_members(members=self.members)
        self.validate_custom_roles(custom_roles=self.custom_roles)
        self.validate_owners(owners=self.owners)
        self.validate_governors(governors=self.governors)

        # Also confirm that there is at least one owner
        no_owners = True
        if not self.owners["actors"]:
            for role in self.owners["roles"]:
                if self.owners["roles"][role]:
                    no_owners = False
                    break
        if no_owners:
            raise ValueError("At least one owner must be assigned")
    
    ###############################
    ### Check Methods (Boolean) ###
    ###############################

    def is_member(self, pk):
        return pk in self.members

    def is_role(self, role_name):
        return role_name in self.get_role_names()

    def has_specific_role(self, role_name, pk):
        all_roles = self.get_roles()
        if role_name not in all_roles.keys():
            print("Role ", role_name, " does not exist")
        if role_name in ["owners", "governors"]:
            return pk in all_roles[role_name][actors]
        return pk in all_roles[role_name]

    def has_governors(self):
        return self.governors['actors'] or self.governors['roles']

    def is_governor(self, pk):
        '''Checks if user is an governor.  Not a pure boolean since it's helpful to know 
        which (if any) role matched for permission pipeline logging.'''
        if pk in self.governors['actors']:
            return True, None
        for role in self.governors['roles']:
            if self.has_specific_role(role_name=role, pk=pk):
                return True, role
        return False, None

    def is_owner(self, pk):
        '''Checks if user is an owner.  Not a pure boolean since it's helpful to know 
        which (if any) role matched for permission pipeline logging.'''
        if pk in self.owners['actors']:
            return True, None
        for role in self.owners['roles']:
            if self.has_specific_role(role_name=role, pk=pk):
                return True, role
        return False, None

    ###################
    ### Get Methods ###
    ###################

    def get_roles(self):
        '''Gets all roles, including protected roles.'''
        return {**self.custom_roles, 'governors': {**self.governors}, 
            'owners': {**self.owners}, 'members': self.members}

    def get_role_names(self):
        '''Gets names of all roles, including protected roles.'''
        return list(self.custom_roles.keys()) + self.protected_roles

    def get_custom_roles(self):
        '''Gets custom roles only, but not protected roles.'''
        return self.custom_roles

    def get_custom_role_names(self):
        '''Gets the names of custom roles only, but not protected roles.'''
        return self.custom_roles.keys()

    def get_users_given_role(self, role_name):
        all_roles = self.get_roles()
        if role_name not in all_roles.keys():
            print("Role ", role_name, " does not exist")
        if role_name in ["owners", "governors"]:
            return all_roles[role_name][actors]
        return all_roles[role_name]

    def get_roles_given_user(self, pk):
        # NOTE: this does not catch when a user is owner/governor through custom roles
        list_of_user_roles = []
        all_roles = self.get_roles()
        for role_name, role_data in all_roles.items():
            if role_name in ["owners", "governors"]:
                if pk in all_roles[role_name]["actors"]:
                    list_of_user_roles.append(role_name)
            else:
                if pk in all_roles[role_name]:
                    list_of_user_roles.append(role_name)
        return list_of_user_roles

    def get_owners(self, actors_only=False):
        if actors_only:
            return self.owners["actors"]
        return self.owners

    def get_governors(self, actors_only=False):
        if actors_only:
            return self.governors["actors"]
        return self.governors

    def get_members(self):
        return self.members

    #####################
    ### Write Methods ###
    #####################

    # Custom roles

    def add_role(self, role_name):
        # TODO: we should probably check capitalization here
        all_roles = self.get_roles()
        if role_name not in all_roles:
            self.custom_roles.update({role_name: []})
        else:
            print("Role ", role_name, " already exists")

    def remove_role(self, role_name):
        # TODO: we should probably check capitalization here
        if role_name in self.protected_roles:
            raise ValueError("Can't remove role ", role_name, "; role is protected.")
        all_roles = self.get_roles()
        if role_name not in all_roles:
            print("No role ", role_name, " found; therefore it cannot be removed.")
        else:
            del self.custom_roles[role_name]

    def add_people_to_role(self, role_name, people_to_add):
        '''Add people to custom role.  Protected roles are handled separately.'''
        all_roles = self.get_custom_roles()
        if role_name in all_roles:
            merged_people = set(all_roles[role_name]) | set(people_to_add)
            self.custom_roles[role_name] = list(merged_people)
        else:
            print("Role ", role_name, " not in roles")    

    def remove_people_from_role(self, role_name, people_to_remove):
        '''Remove people from custom role.  Protected roles are handled separately.'''
        all_roles = self.get_custom_roles()
        if role_name in all_roles:
            remaining_people = set(all_roles[role_name]) - set(people_to_remove)
            self.custom_roles[role_name] = list(remaining_people)
        else:
            print("Role ", role_name, " not in roles")  

    # Members

    def add_member(self, pk):
        if pk not in self.members:
            self.members.append(pk)
        else:
            print("User ", str(pk), " is already a member.")

    def add_members(self, pk_list):
        for pk in pk_list:
            self.add_member(pk)

    def remove_member(self, pk):
        if pk in self.members:
            self.members.remove(pk)
        else:
            print("User ", str(pk)), " is not a member and cannot be removed."

    def remove_members(self, pk_list):
        for pk in pk_list:
            self.remove_member(pk)

    # Governors

    def add_governor(self, pk):
        if pk not in self.governors['actors']:
            self.governors['actors'].append(pk)
        else:
            print("User ", str(pk), " is already a governor.")

    def add_governor_role(self, role_name):
        if role_name not in self.governors['roles']:
            self.governors['roles'].append(role_name)
        else:
            print("Role ", role_name, " already in governor roles") 

    def remove_governor(self, pk):
        if pk in self.governors['actors']:
            self.governors['actors'].remove(pk)
        else:
            print("User ", str(pk), " is not a governor and can't be removed from governor role.")

    def remove_governor_role(self, role_name):
        if role_name in self.governors['roles']:
            self.governors['roles'].remove(role_name)
        else:
            print("Role ", role_name, " not in governor roles") 

    def add_owner(self, pk):
        if pk not in self.owners['actors']:
            self.owners['actors'].append(pk)
        else:
            print("User ", str(pk), " is already an owner.")

    def add_owner_role(self, role_name):
        if role_name not in self.owners['roles']:
            self.owners['roles'].append(role_name)
        else:
            print("Role ", role_name, " already in owner roles") 

    def remove_owner(self, pk):
        if pk in self.owners['actors']:
            self.owners['actors'].remove(pk)
        else:
            print("User ", str(pk), " is not an owner and can't be removed from owner role.")

    def remove_owner_role(self, role_name):
        if role_name in self.owners['roles']:
            self.owners['roles'].remove(role_name)
        else:
            print("Role ", role_name, " not in roles")


def parse_role_handler_data(role_handler_data):
    role_data = json.loads(role_handler_data)
    return RoleHandler(
        members=role_data['members'],
        owners=role_data['owners'],
        governors=role_data['governors'],
        custom_roles=role_data['custom_roles'])


class RoleField(models.Field):
    """This custom field allows us to access the methods and validation of the RoleHandler
    object."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        return name, path, args, kwargs

    def db_type(self, connection):
        return 'rolehandler'  

    def from_db_value(self, value, expression, connection):
        if value is None:
            return RoleHandler()
        return parse_role_handler_data(value)

    def to_python(self, value):
        if isinstance(value, RoleHandler):
            return value
        if value is None:
            return RoleHandler()
        return parse_role_handler_data(value)

    def get_prep_value(self, value):
        if isinstance(value, RoleHandler):
            return json.dumps({
                'members': value.members,
                'owners': value.owners,
                'governors': value.governors,
                'custom_roles': value.custom_roles
            })
        # # Do we need this at all?  Commenting it out for now.
        # if value in [None, 'null', '{}']:
        #     return json.dumps({
        #         'members': [],
        #         'owners': {'actors': [], 'roles':[]},
        #         'governors': {'actors': [], 'roles':[]},
        #         'custom_roles': {}
        #     })