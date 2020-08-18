.. toctree::
   :maxdepth: 2

.. _change-objects:

Change Objects
**************

Imagine that your website has forums and the basic actions a user can take on your site include “add a post”, “edit a post”, “delete a post”, “add a comment to a post”, “edit a comment on a post” and “delete a comment from a post”.  (In reality there are a variety of other less obvious actions a site like this would have, but these will do for now.)

A developer working with Concord would create “change objects” (simple Python objects) for each of these actions. The change objects accept both required and optional parameters in their init methods, for example a “delete comment” change object would accept the primary key of the comment.  In the validate method of the change object, the developer can add custom validation - for instance, in an “add comment” change they may want to automatically reject a comment that is too long.  In the implement method, they define the steps to implement the change - for instance, when editing a post, the method would take the steps of looking up the post object from the database, changing the field, and saving it.  The change’s validate method is run just before an Action is created.  If the change is valid, we create the action and run it through the permissions pipeline.  If the permission passes, the implement method is called.

Change objects are part of both Actions and Permissions Items.

.. _permissions:

Permissions
***********

Permission objects have a few different fields. First, they have a specific target they’re set on - always a permissioned model.  Also, as mentioned above, they have a “roles” field and an “actors” field, specifying who has the given permission.  They also have a boolean (true or false) field which, when flipped, allows any user (including those who are not members of the community) to have the permission, overriding whatever roles and actors have been set.

Permission objects also have a change field and a configuration field.  This optional configuration field can be applied to the change field to narrow the permission’s scope.  For instance, take the change “add people to role”.  We may want to grant someone the ability to add people to all roles, or we may want to specify that they can only add people to a given role.  When creating or editing the permission, we add the configuration by specifying the role_name, that is, the name of the role we want to limit the user(s) permission to.

While developers can extend the permissions system to cover a variety of change types, there are some core types that are necessary for the basic structure of Concord to function, such as: add people to role, remove people from role, add role, remove role, add governor, remove governor, etc.

One final note: permissions objects are themselves a permissioned model.  That is, permissions can be the target of actions and be subject to their own permissions.  Communities content to leave the changing of permissions up to their owners and governors will not need to nest permissions (that is, set permissions on permissions) but the functionality can be useful in some cases. 


.. _permissions-pipeline:

Permissions Pipeline
********************

Let’s go through the steps of the permissions pipeline again in more depth, addressing some of the caveats and complexities.

We refer to the three elements of the permissions pipeline as the “foundational pipeline” (aka the owners pipeline), the “governing pipeline”, and the “specific permission pipeline”, and they are tried in that order.

To check if the action should enter the foundational pipeline, we look to see whether the change is of a special type, what we call a “foundational change”, or when the target of the action has “foundational permissions enabled”.  When this simple boolean value is True, all changes of any type on the target must come from owners, although typically the value is set to False.  Once an action enters the foundational pipeline, it passes or fails based on that pipeline - we do not continue on to the governing or specific permission pipeline regardless of the result.

If an action is not foundational, we proceed to the governing pipeline.  Before checking if the owner is a governor, we look to see if the target has the “governing permission enabled”.  The governing permission is enabled by default, but it can be disabled as a way of limiting the discretion of the governors.  If the governing permission is enabled, and the owner is a governor, they pass the permission and exit the pipeline.  However, unlike with the foundational pipeline, if the actor is not a governor we do continue on to the last pipeline, the specific permissions pipeline.

The specific permission pipeline is the most complex of the pipelines.  First, we look up all permissions set on the target and check to see whether the action passes them.  If none do, we continue on to look at parent objects to see if any permissions are set on them which the action passes.  By allowing permissions to be set on parent objects, we can broaden the scope of a permission.  For instance, we may want to give anyone with role “editors” the ability to edit a given post.  But we might also want to give them the ability to edit all posts in a given forum.  We can check for permission to ‘edit post’ on the individual post, or on the forum as a whole.

Although typically we only evaluate zero or one specific permissions per action, an action can match multiple permissions.  In that case, an action only has to pass one permission to be approved.

At the end of the permissions pipeline, the actions will have a status: approved, rejected, or waiting.  “Waiting” is the status an action will have if they passed a permission or permissions (specific permission(s), governing, or foundational) but there was a condition set on it, and the condition is not yet resolved.  If the status is “approved”, the action will be implemented.  If the status is “rejected”, the action will be closed without implementing.


.. _condition-models:

Condition Models
****************

When conditions are set on a permission, the basic information about condition type and configuration are saved in the permission model.  When an action passes that permission, we check and see if a condition is set.  If a condition is set, we’ll create a new condition model object using information from both the permission the condition was set on, and the action that triggered it.  That condition must then be approved before the action can pass.  Every time the condition is updated, we send a signal to the action, which attempts to pass the permissions pipeline again.

All conditions have a status: accepted, rejected, or waiting.  Conditions with a status of “Accepted” or “Rejected” are considered resolved, while those that are “Waiting” are unresolved. How that status is determined is implemented by the individual condition.  For instance, the VoteCondition takes into account the existing votes, whether the voting period has expired, and whether or not the condition is configured to require a majority or a plurality.  More simply, the ApprovalCondition just checks to see whether anyone has approved or rejected it.  Once a condition is resolved, it can no longer be updated.

If an action passes a permission but is rejected by the condition set on the permission, it is as if they were rejected by the permission itself.  The action may pass through some other route, but not via that permission.

Conditions are themselves permissioned models. When setting an Approval Condition on a permission, the community may specify that only those with role “mods” can approve.  When an action runs into a condition, an ApprovalCondition model is created corresponding to that action, along with a permission to approve which only those with role “mods” can take.