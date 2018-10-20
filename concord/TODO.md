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
IN PROGRESS


- maybe each permission has a "conditional" field? 
then what is the "condition"?

-- the condition itself needs to resolve into yes or no eventually
-- ideally it's easily extensible
-- options:
----- check if user has attribute (maintainer label)
----- check if enough time has expired
----- check if user not on blocklist
----- check if something has a particular value (can be used for various votes, also
potentially for chaining actions?  but the condition is on the permission not the action)

where is this set?  it seems like it ought to be set on the action, since we'll need to apply it to each action, and yet the specifics would be on the permission, no?  but maybe it's in the change_data somehow.

or maybe an additional "conditional" field, linked to status?

okay, so theoretically you could have a permission that sets the conditional data within the change field.

ooooooookay what if the condition is orthogonal to permissions?  no but then if the condition is "user has attribute" it's getting conceptual separated from permission

no I think it ought to be defined in permissions so that you can look at the full list of rules for changing state.  

What does a user *see* when a condition has been activated though?

1) a permission is set on a resource that says all new items need mod approval.
2) buffy attempts to add an item, this causes her action to be set to "waiting" because
her change object (created by the client) "has a conditional field" (something on the base change, default = false)
3) how does the mod approve the action?

options:
- conditional actions resource [or maybe generic action resource?]?  but then do you have to set the permissions on that separately?  and how does the action know to check the action resource?
- change the action itself with another action?  but action models aren't themselves governed by permissions

Ideally we could reuse permissions, so that we could set "approval from has label 'mod'" to like five different permissions rather than redoing it constantly.

Also... how does "has label 'mod'" fit into the context?  I guess all resources belong to a community.


Okay, options *again*:

- create a conditions model, with a type and data.  when a permission has a condition create a new instance/row of the condition and link it to the action.

Okay:
--- where is the info coming from?
--- who needs access to the info?

The info is coming from:
--- what kind of actions should have the condition apply to them?  permissions resource
--- what the specific condition is?  permissions resource

Who needs access to the info:
--- whether the condition is met?  the action itself

*****

Okay, IF there is a condition on the action THEN we check for its existence in the ConditionalActions Resource for a given resource/item.  (ConditionalActions Resource and Items are part of the core, like Permissions Resource.)

A conditional actions item has a condition_met() method which returns yes/no/waiting and that's the thing that the action itself queries.

The specifics of the conditional action are specified by, what?  Condition Object?  Referenced by permission?  Sure.  Like, "condition_type, condition_data".

How are permissions on a conditional action set tho?  By the condition itself?

1) a permission is set on a resource with a condition that says all new items need mod approval.
2) buffy attempts to add an item.  due to the condition, her action is set to "waiting" and linked to a ConditionalActionResource.
3) a mod for the resource checks the conditionalactionresource and sees an active action.  
4) the mod wants to set "approved" to true on the conditionalactionresource item.
option 1: that item gets "permission condition change label = mod" set on it, ugh yet another layer
option 2: the condition itself checks for the mod label 

pros of option 2: seems simpler for now, but less able to recurse?  well let's try it















100. Possible extentensions:
- complex action (adding label, for instance)
- improve separateness of client
- different options for default permissions system?
- make a display


# Open Questions

1.  How should we name client methods?  For instance, with permissions_resource, should we use add_item or add_permission or both or set add_item to call add_permission?

Right now, using add_item for both RC and PRC, they take different parameters in which is confusing.

2.  What should we do about complex actions?

3.  How do we "short-circuit" the permissions resource system?  We don't want to recursively create prs for prs for prs forever. 

We could say, if not otherwise specified, the PR system is the "default" system, which
is completely private to the creator.  So you only create a permissions resource if you
want to override that completely private system (which you can do on object creation in the UI, which means users don't have to think about this).



# Architectural Notes

- Generally speaking, apps only intereact with each other through their clients and you can only import things from appname/client.py.

- There are certain 'core' apps that are re-used by each other, for instance, all apps rely on the action app, which return relies on the permissions_resources app.  [Make dependency map?]




# A Complete List of Valid State Changes

CREATION:

- new objects can be created (but not updated) directly in their respective clients without using actions

- action objects are created by the base client in actions.client

UPDATING:

- for all models except those explicitly stated below, they can only be updated via the implement method of a change object instantiated on an action model

- action models: can save their own status in methods called by the take_action meta-method

OTHER:

- user account data is created and saved separately

- notifications/settings/email data is created and saved separately