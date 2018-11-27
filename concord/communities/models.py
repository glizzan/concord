from django.db import models

from actions.models import PermissionedModel

"""
### OWNERSHIP

Communities are a very special type of resource.  Through communities,
individuals may collaboratively own resources and manage their collective
spaces and relationships.

To understand how communities own resources, let's first discuss the
simpler case of an individually owned resource.  An individual who owns
a resource object may attach a permissions resource to that object,
granting other individuals specific abilities regarding it.  For instance,
an individual who owns a post object may grant others the right to edit
it, attach comments to it, etc.  They may even nest permissions on the
object, for instance, an owner might allow a friend to help decide who
else can comment on the post.  But they can always revoke those permissions,
because as owner are the ultimate or foundational authority on what 
happens to the object.

This is instantiated practically through the 'default permission' which
all objects have.  This default permission is used when no permissions
resource is set on an object, or when the a default permissions resource
is set but permissions for a specific action are not set.  (PRs contain
an option, 'ignore_defaults', which when set to true prevents the 
default_permission from being used in the latter case.)  The default
permission for an individually owned object is simple: if the actor is
the owner, they have permission for whatever they want to do, and if the
actor is not the owner, they do not have any permission.

This scheme is complicated by the existence of communities.  If a
community owns a resource, how does the default permission get resolved?
You can't check the action's actor against the object's owner because
the community itself cannot act - only individuals within the community
can do so.  You might ask, do we need to set a default permission?  Can't we
always make sure to set permissions resources?  The problem with this
approach is that permissions resources can themselves be acted upon and
therefore require their own permissions schema, either a nested permissions
resource or a default permission.  You nest as many permissions resources
as you like but they must always terminate in a default permission.  It
cannot be turtles all the way down.

Communities have their own distinct way of handling the default permission
system called the AuthorityHandler.  The AuthorityHandler always specifies
two things.  First, which individuals may respond to actions which
trigger the default permission, which we'll refer to here as 'governors.  
Second, how changes to the AuthorityHandler itself are made.  It's this
latter specification that determines the foundational governance process 
for the group.  

Now, you can set up a community such that Person A is the only governor 
and only the governor can change the AuthorityHandler.  That's the 
'Benevolent Dictator' model of a community and it is configurable within 
our system.  Most groups will prefer a more democratic model.  This is 
achieved by applying Conditionals to either or both of the AuthorityHandler's
functions.  For instance, you could require a review conditional for 
governors responding to default permissions, so that two or more governors
must approve. You could also subject any changes to the AuthorityHandler, 
including replacement of one governor with another, to a majority vote.
Note that this gets recursive: if all changes to the AuthorityHandler 
require a majority vote, then any attempt to change the AuthorityHandler 
so it *doesn't* require a vote would require a vote.

This is all very abstract, so let's talk through a concrete example:

Imagine that you've got a community of 100 people.  They have set their
AuthorityHandler to have a board of five governors who can each, without
condition, resolve default_permission issues how they see fit.  Changes
to the AuthorityHandler itself, however, require a supermajority vote.
Let's look at three actions that could be taken within the community and 
how they would get resolved.

1) Anne wants to add a post to the community discussion forum.  According
to the permissions resource for the discussion forum, all posts must be 
reviewed by a moderator.  When Anne adds the post, it does *not* trigger 
a default permission since the action is covered by the permissions 
resource.  Instead, a moderator reviews and accepts or rejects her post.

2) Betty thinks the rule about posts needing to be moderated is dumb.
She submits a change to the permissions resource itself.  There is no
permission resource set on the permissions resource so it triggers the
default permission. Governor A agrees with Betty and accepts the change.
However the other governors are upset - by informal policy, changes
to the system require consensus among the governors.  In the comments
on Betty's action, they discuss whether or not they actually want to 
keep this change.  They decide not to, and Governor A submits an action
changing the rule back, and approves it himself.

3) Governors B and C are still upset about Governor A's decision to
accept the change and wants their informal consensus system to be
formalized.  Governor B submits a change to the AuthorityHandler adding
a ConsensusConditional to the governor specification.  The majority votes
for this and the AuthorityHandler is changed.  

### ROLES

Another key tool used within communities is something called a 'role set'.
This allows communities to specify roles like 'moderator' or 'admin' and 
assign specific people to those roles.  These roles can then be referenced 
throughout the community via permissions resources. 

A permission resource is made up of individual permissions.  Each permission
has an action that is being permitted. It also has a field which indicates 
*who* has permission to take those actions.  This field can be designate
through either or both of the individual actor list or the role list. 
The individual actor list is a list of unique IDs.  The role list is a list
of tuples indicating a community and a role.  To see if an actor can take 
an action, the PR first looks in the individual list.  If the actor is not
there, it goes through the tuples in the role list, querying each
community to see if the actor in question has the given role, stopping 
and returning 'true/yes' if the answer is ever 'yes', and otherwise 
returning 'false/no'.

There are two types of roles that can be set in a community's role set:

* AssignedRoles: roles + individuals given that role
* AutomatedRoles: roles + rules to test if an  individual fits that 
role, for example "anyone older than X hours"

### COMMUNITY REQUIREMENTS

Given the above, all communities are required to have the following:

* An authority handler with the 'who can change this authority handler'
field set.  Setting up governors is highly recommended, but optional.

* A role set, which may be empty.  Setting up roles is highly 
recommended, but optional.

* A list of members, which may not be empty.

Additionally, most communities have other resources such as discussion 
boards.  Communities can own pretty much any type of resource.

### COMMUNITY DEFAULTS

By default upon creation, the list of members is set to one (the creator),
the governors are set to include one (the creator), and how the authority
handler is changed is set to an unconditioned action of the single 
governor.  That governor can then configure the community to their heart's
content.  That said, there are many other templates provided for people
who want to start off with more complex community configurations.

### OPEN DESIGN QUESTIONS

- permissions resources as levels vs permission individual stacks -- how
do we want to design this?

- should we grant governors the ability to modify permissions resources
by default, instead of just responding to actions?  I guess they can
always trigger the actions they want to respond to.

- should the governor role actually be set in the role_set?  there's
some conceptual duplication here, at least, but the roles have very
different power levels
"""


### TODO: CHANGES ELSEWHERE

# Make sure everything's worked out with communities before actually
# making these changes
#
#    0) switch 'creator' field to 'owner' field - DONE
#    1) add field/method for object to determine if its owner is
#       an individual or community and handle the default permission
#       accordingly.
#    2) on a permission resource item, instead of 'actor' there's
#       a json field containing a list of individuals and/or a
#       set of community + role tuples. 
#    3) if a person creates something *within* a community, the
#       community is the governor, not the person who created this.
#       (How does a thing know it was created with a community?
#       Well. What makes something in a community?  That it's governed
#       by the community.)


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
    Every community has at least one role set which defines roles within
    the community.
    """
    # assigned_roles = # json field, names with lists of people
    # automatedRoles = # jsonfield?

    def user_has_specific_role(self, role_name, user):
        if self.user_has_assigned_role(role_name, user):
            return True
        if self.user_has_automated_role(role_name, user):
            return True
        return False

    def user_has_assigned_role(self, role_name, user):
        ...

    def user_has_automated_role(self, role_name, user):
        ...

    def user_has_any_role(self, user):
        for role in self.assigned_roles:
            if self.user_has_assigned_role(role_name, user):
                return True
        for role in self.automated_roles:
            if self.user_has_automated_role(role_name, user):
                return True
        return False

    def list_roles_given_user(self, user):
        roles = []
        for role in self.assigned_roles:
            if self.user_has_assigned_role(role_name, user):
                roles.append(role)
        for role in self.automated_roles:
            if self.user_has_automated_role(role_name, user):
                roles.append(role)
        return roles


class AuthorityHandler(PermissionedModel):
    """
    The authority handler is the foundational source of authority for a community.
    It has two main functions: responding to the default permission (fallback permission?)
    and changing itself.
    
    All communities have a corresponding authority handler.
    """

    # These should be JSON fields or custom fields eventually
    community = models.OneToOneField(Community, on_delete=models.CASCADE)
    governors = models.CharField(max_length=200)
    rules_for_changing = models.CharField(max_length=200)

    # TODO: Is it worrying that has_default_permission implements logic so similar to
    # check_conditional in actions/permissions.py?  Should we refactor/abstract?

    # TODO: Can we put the authority handler logic as fields on communities?  Yes to
    # 'governors' field probably, since condition is set separately.  What about 
    # 'rules for changing' though?

    # TODO: Don't love that this logic is here in the first place but I don't really 
    # want it in the client either.  Maybe move to actions/permissions.py?

    def has_default_permission(self, action):

        # If actor is not a governor, they definitely don't have permission.
        if action.actor not in self.governors:
            return "rejected"

        # If there's no condition on the governor, they definitely do have permission.
        from conditionals.client import ConditionalClient
        cc = ConditionalClient(actor=action.actor) 
        condition_template = cc.get_condition_template_given_community(
            community_pk=self.community.pk)
        if not condition_template:
            return "approved"

        # Evaluate conditional, creating instance if not already created.    
        condition_item = cc.get_or_create_condition_item(condition_template=condition_template,
            action=action)
        return condition_item.condition_status()
