import json

from django.db import models

from actions.models import PermissionedModel


################################
### Community Resource/Items ###
################################

class BaseCommunityModel(PermissionedModel):

    name = models.CharField(max_length=200)
    
    class Meta:
        abstract = True

    def get_owner(self):
        """
        Communities own themselves by default, unless they are subcommunities.
        """
        return self.name


class Community(BaseCommunityModel):
    """
    A community is, at heart, a collection of users.  Communities 
    govern resources that determine how these users interact, either
    moderating discussion spaces, like a community forum, setting
    restrictions on membership lists, or by setting access rules for
    resources owned by the community, such as saying only admins
    may edit data added to a dataset.
    """
    ...
    

class SubCommunity(BaseCommunityModel):
    """
    A community can have one or more subcommunity associated with it.
    Although subcommittees can set internal self-governance rules,
    their authority ultimately comes from the containing community,
    which can override their decisions.  So, ultimately, everything
    within a subcommunity is governed by the containing community,
    in contrast to a super community.
    """
    ...


class SuperCommunity(BaseCommunityModel):
    """
    Two or more communities may participate in a supercommunity.  
    Only resources which are explicitly created *in the supercommunity*
    are governed by the supercommunity, otherwise the participating
    communities remain separate and have full internal self-governance.
    """
    ...


class RoleSet(PermissionedModel):
    """
    Roles are set community-wide.

    An assigned role just has a list of usernames (user IDs) and the name of the role.  You
    can add to the role by doing a statechange to the role list.  You reference the role in
    the permission item by listing the unique role name and the community it's set on.

    An automated role has a logical statement to apply to the actor to see if they fit.
    You can change the paramters of the role or remove it entirely but you can't assign people
    to it.  Again, you reference the role in the permission item by listing the unique role name 
    and the community it's set on.

    With AuthorityHandlers, the role is not set in the roleset but on the authorityhandler itself,
    but the logic otherwise works the same.
    NOTE: could potentially make governors and owners a field on the roleset?
    """

    community = models.OneToOneField(Community, on_delete=models.CASCADE)
    assigned = models.CharField(max_length=1000)  # Replace with custom field
    automated = models.CharField(max_length=200)  # Replace with custom field

    def get_assigned_roles(self):
        return json.loads(self.assigned) if self.assigned else { "members": [] }

    def get_automated_roles(self):
        if not self.automated:
            return {}
        return json.loads(self.automated)

    def get_role_names(self, merged=False):
        assigned_roles = self.get_assigned_roles()
        automated_roles = self.get_automated_roles()
        if merged:
            return assigned_roles.keys() + automated_roles.keys()
        return { "assigned_roles": assigned_roles.keys(), "automated_roles": automated_roles.keys() }

    def user_has_specific_role(self, role_name, user):
        if self.user_has_assigned_role(role_name, user):
            return True
        if self.user_has_automated_role(role_name, user):
            return True
        return False

    def user_has_assigned_role(self, role_name, user):
        assigned_roles = self.get_assigned_roles()
        if role_name in assigned_roles:
            return user in assigned_roles[role_name]
        else:
            print("Assigned role ", role_name, " does not exist")

    def user_has_automated_role(self, role_name, user):
        ...
        # Need to instantiate object and check whether user applies

    def user_has_any_role(self, user):
        for role in self.get_assigned_roles():
            if self.user_has_assigned_role(role.key(), user):
                return True
        for role in self.get_automated_roles():
            if self.user_has_automated_role(role.key(), user):
                return True
        return False

    def list_users_given_role(self, role):
        roles = self.get_assigned_roles()
        if role in roles:
            return roles[role]
        print("No role ", role, " specified")

    def list_roles_given_user(self, user):
        roles = []
        for role in self.get_assigned_roles():
            if self.user_has_assigned_role(role.key(), user):
                roles.append(role)
        for role in self.get_automated_roles():
            if self.user_has_automated_role(role.key(), user):
                roles.append(role)
        return roles

    def add_assigned_role(self, role_name):
        assigned_roles = self.get_assigned_roles()
        if role_name not in assigned_roles:
            assigned_roles[role_name] = []
        else:
            print("Role ", role_name, " already exists")
        self.assigned = json.dumps(assigned_roles)

    def remove_assigned_role(self, role_name):
        if role_name.lower() == "members":
            print("Can't remove 'members' role")
            return
        assigned_roles = self.get_assigned_roles()
        if role_name not in assigned_roles:
            print("No role ", role_name, " found")
        else:
            del(assigned_roles[role_name])
        self.assigned = json.dumps(assigned_roles)

    def add_people_to_role(self, role_name, people_to_add):
        assigned_roles = self.get_assigned_roles()
        if role_name in assigned_roles:
            merged_roles = set(assigned_roles[role_name]) | set(people_to_add)
            assigned_roles[role_name] = list(merged_roles)
        else:
            print("Role ", role_name, " not in roles")
        self.assigned = json.dumps(assigned_roles)        

    def remove_people_from_role(self, role_name, people_to_remove):
        assigned_roles = self.get_assigned_roles()
        if role_name in assigned_roles:
            existing_people_set = set(assigned_roles[role_name])
            for person in people_to_remove:
                existing_people_set.remove(person)
            assigned_roles[role_name] = list(existing_people_set)
        else:
            print("Role ", role_name, " not in roles")
        self.assigned = json.dumps(assigned_roles)  


# FIXME: should AuthorityHandler descend from PermissionedModel if no PR can be set?
class AuthorityHandler(PermissionedModel):
    """
    All communities have an AuthorityHandler which is created when
    the community is created.

    The authority handler has two fields.  The 'owners' field is
    required and sets the foundational authority for the community.
    The 'governors' field is optional and sets the governors authority
    for the community.  
    
    Both individuals and roles can be assigned to the 'owners' and
    'governors' field.
    """

    # These should be JSON fields or custom fields eventually
    community = models.OneToOneField(Community, on_delete=models.CASCADE)
    governors = models.CharField(max_length=200)
    owners = models.CharField(max_length=200)

    # TODO: add checks re: duplication

    def add_governor(self, governor):
        governors = json.loads(self.governors)
        governors['actors'].append(governor)
        self.governors = json.dumps(governors)

    def add_governor_role(self, role, community):
        new_role = str(community) + "_" + role
        governors = json.loads(self.governors)
        governors['roles'].append(new_role)
        self.governors = json.dumps(governors)

    def remove_governor(self, governor):
        governors = json.loads(self.governors)
        governors['actors'].remove(governor)
        self.governors = json.dumps(governors)

    def remove_governor_role(self, role, community):
        role_to_remove = str(community) + "_" + role
        governors['roles'].remove(role_to_remove)
        self.governors = json.dumps(governors)

    def get_governors(self):
        if not self.governors:
            return { 'actors': [], 'roles': [] }
        return json.loads(self.governors)

    def is_governor(self, actor):
        governors = self.get_governors()
        if actor in governors['actors']: 
            return True

        # FIXME: copied from permission_resources.models and also duplicated for owners
        from communities.client import CommunityClient
        cc = CommunityClient(actor="system")
        for pair in governors['roles']:
            community, role = pair.split("_")  # FIXME: bit hacky
            result = cc.has_role_in_community(community_pk=community, role=role, actor=actor)
            if result:
                return True

        return False

    def add_owner(self, owner):
        owners = json.loads(self.owners)
        owners['actors'].append(owner)
        self.owners = json.dumps(owners)

    def add_owner_role(self, role, community):
        new_role = str(community) + "_" + role
        owners = json.loads(self.owners)
        owners['roles'].append(new_role)
        self.owners = json.dumps(owners)

    def remove_owner(self, owner):
        owners = json.loads(self.owners)
        owners['actors'].remove(owner)
        self.owners = json.dumps(owners)

    def remove_governor_role(self, role, community):
        role_to_remove = str(community) + "_" + role
        owners['roles'].remove(role_to_remove)
        self.owners = json.dumps(owners)

    def get_owners(self):
        if not self.owners:
            return { 'actors': [], 'roles': [] }
        return json.loads(self.owners)

    def is_owner(self, actor):
        
        owners = self.get_owners()

        if actor in owners['actors']:
            return True

        from communities.client import CommunityClient
        cc = CommunityClient(actor="system")

        for pair in owners['roles']:
            community, role = pair.split("_")  # FIXME: bit hacky
            result = cc.has_role_in_community(community_pk=community, role=role, actor=actor)
            if result:
                return True
                
        return False