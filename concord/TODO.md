# To Do

1. Re-implement stuff from most recent attempt (ananke) using actual Django models
DONE

2. Once you've implemented permission_resources try to sub out the stuff in permissions for that.
DONE

3. Set permissions on permissions
DONE

4. Action data/history
DONE

5. Manual Approval
DONE (see write up below - 'About Conditionals')

6. Toy Front End
IN PROGRESS - pausing for now because it annoys me

7. Communities
IN PROGRESS - 


# Open Questions

1.  How should we name client methods?  For instance, with permissions_resource, should we use add_item or add_permission or both or set add_item to call add_permission?

Right now, using add_item for both RC and PRC, they take different parameters in which is confusing.

2.  What should we do about complex actions?

3.  How do we "short-circuit" the permissions resource system?  We don't want to recursively create prs for prs for prs forever. 

The default permission system is how permissions are handled in the absence of a PR.  For 
individually owned objects, the default permission is that the owner has all permissions 
and everyone else has none.  For community owned objects, the default permission depends
on how the community is configured.  

This system assumes that all PermissionedModel objects have an owner.  This is easy enough
to assign for resource-like objects, we can just make the creator the default owner, but what about things like permission resources, actions, and conditionalactions?  These are set automatically by the system.  They can be overridden, but by default:

The owner of a permission resource is the actor who created the resource.
The owner of a permission item is the actor who set the permission item on the resource.
The owner of a ConditionalTemplate is the actor who set the condition on the permission.
The owner of the conditional action is the actor who set the condition on the permission, aka the owner of the condition template.
The owner of the permission set on the conditional action which is set on a permission
which is set on a target is (JESUS CHRIST) is the actor who set the condition on the permission (aka the owner of the conditional action which the permission is set on).


# Architectural Notes

- Generally speaking, apps only intereact with each other through their clients and you can only import things from appname/client.py.

- There are certain 'core' apps that are re-used by each other, for instance, all apps rely on the action app, which return relies on the permissions_resources app.  [Make dependency map?]


# A Complete List of Valid State Changes

CREATION:

- new objects can be created (but not updated) directly in their respective clients without using actions

- action objects are created by the base client in actions.client

UPDATING:

- for all models except those explicitly stated below, they can only be updated via the implement method of a StatusChange object instantiated on an action model

- action models: can save their own status in methods called by the take_action meta-method

- NOTE: creating an object with a relationship to an existing object counts as a state change, for instance adding an item to a resource or a permission to a condition

OTHER:

- peripheral data is created and saved separately, for instance user account data, notifications/email, etc.


# How to create a new app with permissioned resources in it

1.  Create the standard app using django startapp, add to settings, etc.

2.  Model should subclass PermissionedModel from actions.py

3.  Need to create a client.py to allow other apps to interact with it

4.  Need to create a state_changes.py to allow models to change state.




