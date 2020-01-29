Concord introduces a number of new concepts.  It is necessary to understand these concepts to make
most major changes to the codebase.

.. toctree::
   :maxdepth: 2


At the heart of Concord's design is a complex and flexible permissions system.  Every action you
can take in Concord must go through the permissions system.  Only once you have successfully passed
through the system will your action be implemented.

Actions
*******

An action is a Django model with three key fields that we'll talk about here: the actor, the change,
and the target.  The actor is whoever is taking the action, always a user.  The change is the type of
action they are taking, for instance changing something's name.  The target is that 'something' they
are taking the action on.  So, for instance, if Anne is changing the name of a resource, that resource
would be the target.

All targets must be descended from the PermissionedModel found in ``actions/models.py``.  Information
about whether a person can make a change is stored largely in the permissions information associated 
with the target.

Information about changes are stored via StateChange objects.  These can be found in the ``state_changes.py``
modules in the various package directories.  Each StateChange object carries the logic for how the 
change is implemented, as well as any specific information for the change.  (For instance, if you are
make the change 'change the name of the resource', the state_change object stores what you're changing
the resource's name *to*.)  

Three Types of Authority
************************

As mentioned above, information about whether a person can make a change is stored largely in the 
permissions information associated with the target.  There are three types of permissions, or three
types of authority, which are navigated in a specific order via the permissions pipeline found in 
``actions/permissions.py``.

The three kinds of permissions/authority are foundational authority, specific authority, and 
governing authority.

**Foundational authority** derives from ownership.  All resources in the system are owned by 
communities, but these communities can themselves be owned in a variety of ways.  A single user 
may have dictatorial powers.  A small group of people may share ownership and act via consensus.  
A group of tens of thousands may share ownership and act via majority vote. Of course, getting 
thousands of people to approve every change would be very tedious if not impossible, so we provide 
two ways to delegate authority.  In the end, though, the foundational authority can always revoke or 
change these types of delegated authority.

**Specific authority** derives from specific permissions set on a given object (the “PermissionItem” 
model).  For instance, a community may own a discussion board on which community members talk and debate.
The community will often wish to designate specific permissions, such as allowing moderators to delete 
abusive posts.  To do this, they add optional permission items on those owned resources.  When someone 
tries to take an action on a resource, our system checks the permission items associated with it 
(if any exist) and asks, "Has this person been given a specific permission to do what they're asking to 
do?"

Of course, having to explicitly give every person or role specific permissions can also be tedious, 
especially when you have a few people you trust to use their power wisely.  People with **governing 
authority** have wide latitude to make changes to the system, but they are limited in a few ways:

1. the foundational authority controls who has governing authority, so they can revoke it if they feel its being misused
2. certain changes, such as changing who the foundational authority is, may only ever be taken by the foundational authority
3. the foundational authority may apply a “foundational authority override” to anything, which means only they can change the object, prohibiting those acting through the governing or specific permission, essentially “protecting” that object
4. by default, when a specific permission is set on an object, governors are no longer allowed to take that action, though they can be included in the specific permission to re-grant them that permission

Note that specific permissions and governing permissions are both optional.  If, say, the foundational 
authority wanted to create three separate roles with powers that balanced each other, they could create 
those roles and give none of them governing authority, instead assigning each of them unique sets of 
specific permissions.  There is a great deal of flexibility within this system, with sensible defaults 
chosen to limit confusion for those uninterested in exploring the many governance possibilities.

The permissions pipeline can be visualized in terms of which types of authority it checks for in which
order, based on how the permissioned item and the community within it is configured:

**image coming soon**

Specific Permissions
********************

Specific permissions are more complex and thus deserve a bit more detail.  Specific permissions are 
stored in the database as PermissionsItems (found in ``permission_resources/models.py``).  Each
PermissionsItem includes the permitted object (that is, the model that the permissions refer to),
the change type - that is, the specific type of change that someone is being given permission to do,
and the fields 'roles' and 'actors'.

'roles' and 'actors' refer to the people who are being given permission to do something.  An actor
is a specific individual.  If you want Bob and Carlos to have a permission, you can update the 
associated permissions item so that the actors field lists Bob and Carlos specifically.  Alternatively,
or additionally, you can give permission to a role.  We'll talk more about roles in a minute, but 
basically, communities can assign individuals to one or more roles, such as 'moderators', 'suspended users',
'soccer fans' - the possibilities are endless.  You can then assign specific permissions to anyone
with these roles.  This makes it easier to understand who can do what in your system.

Communities
***********

Conditions
**********