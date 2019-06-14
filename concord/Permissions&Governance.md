# Conceptual Overview

There are three kinds of authority in the system: foundational authority, specified authority, and governing authority.

The first and only required type of authority is the 'foundational authority', that is, the source of authority from which all other authority flows.  This authority is based on ownership.  This ownership is straightforward for an individual but much more complex for a community.  A community can specify a variety of ownership structures.  For instance a community may be owned by its entire membership, with authority exercised through a majority vote.  Or a community may be owned by a single individual with no conditions on what they can do.  It will doubtless be tedious for the community to vote on every single state change within the system, so we provide two ways to delegate authority.

The first way to delegate authority is through the creation of specific permissions.  We call this 'specified authority'.  For instance, a community may own a discussion board on which community members talk and debate.  The community will often wish to designate specific permissions, such as allowing moderaters to delete abusive posts.  To do this, they add optional permission items on those owned resources.  When someone tries to take an action on a resource, our system checks the permission items associated with it (if any exist) and asks, "Does this person have permission to do what they're asking to do?"

The second way to delegate authority is through the designation of governors that are granted authority by default.  We call this 'governoring authority'.  Governors frequently are given wide lattitude to make changes across communities, especially with newer and smaller communities.  

Governing authority is very helpful for communities with high trust, but you may not *want* governors to be able to override or change certain permissions.  While foundational authority can always retroactively override governing authority, it can be too much work to be practically useful.  So we let foundational authority *proactively* override governing authority as well.  Details on how this is done are discussed below.

It's worth noting that conditions can be set on foundational, specific, and governing authority.  For instance, a foundational authority may be expressed through the will of any individual member conditioned on a majority vote of all other members.  A specific authority may be expressed by an individual condition on approval by another individual.  A governing authority may do whatever they like but only when seconded by another governor or perhaps after a 24 hour wait.

# Technical Overview

How is this structure implemented in our system architecture?

Nearly every model in our system inherits from PermissionedModel, an abstract base class.  All PermissionedModels have an owner specified, either an individual or a community.  When an actor wants to change a Permissioned object, it sends an action to the object with the details of the change it wants to make.

The permission system takes three steps, in order:

1) Check that foundational authority override is set to true.  If it is, initiate the foundational permission pipeline, and set the action's status to 'accepted, rejected, waiting'.  If not found, continue to the next step.

2) Check for a specific permission relevant to the action.  If found, initiate the specific permission pipeline, and set the action's status to 'accepted, rejected, waiting'.  If not found, continue to the next step.

3) Check that governer authority is set to true.  If it is, initiate the governing permission pipepline, and set the action's status to 'accepted, rejected, waiting'.  If set to no, set the action's status to 'rejected'.

(By default, permissioned models have foundational override set to false and governor authority set to true.)

The foundational permission pipeline and the governing permission pipeline work by querying the AuthorityHandler of the Community which owns the object.  For a query about foundational authority,the AuthorityHandler checks to see if the actor is listed in the field foundational_authority (either explicitly or through a role like IsMemberRole) and what, if any, conditions apply to the foundational authority.  For a query about governing authority, the AuthorityHandler checks to see if the actor is listed in the field governing_authority (either explicitly or through a role) and what, if any, conditions apply to governing authority.

When checking for specific permissions, the system gets all permission items where the target is the object and the permission type is the action type specified in the specific action.  This should only return zero or one permission items.

It's worth noting that only foundational authority can change the AuthorityHandler.  This is not something that can be changed by the user - the system itself checks when making changes whether it is acting on an Authority Handler or an AuthorityHandlerCondition and, if so, sends the action through the foundational permission pipeline and the foundational permission pipeline *only*.

We've talked about 'setting a permission item' but permission items are themselved permissioned models regulated by the permission systems.  Typically, people will just leave permission items to use their defaults, aka governing authority.  However we might occasionally want to 'stack' permission items on top of each other.

Take the example of the moderator who can delete posts from a board.  What if you want to give a 'moderator manager' the ability to add and remove new post-moderators, rather than just letting anybody do this?  You would have:

a) Permission item A set on board X, with the action_type RemovePosts.  All individuals named in A would be moderators.
b) Permission item B set on permission item A, with the action_type, with the action_type AddActor.  All individuals named in B would be 'moderator managers'.  

If a moderator manager wanted to add a new moderator, they'd send a state change to permission item A.  The permissions system would check for permission items set on A and find B.  It would check the actor against the list of moderator managers on B and approve the action.

The community can halt the stacking of permissions by turning on the foundational_override.  Theoretically, you could add a Permission item C to Permission Item B, creating a 'moderator manager manager' who can add or remove 'moderator managers'.  But let's say you want to make sure that 'moderator managers' can only be changed by exercising foundational authority.  Simply turn the foundational_authority_override on Permission item B.  Then, efforts to change Permission item B will automatically be routed through the foundational permission pipeline, and any specific permissions set will be ignored.

It's worth noting that the foundational authority field, which exists on all permissioned objects, can only be changed by the foundational authority.  If a given action changes this field, it will be routed through the foundational permission pipeline and only the foundational permission pipeline.

Here's the overall pipeline system, in pseudocode:

    def has_permission(action):

        if action.action_type == "change foundational authority field" or 
                                        object.foundational_override is True:
            return has_foundational_permission(action)

        if specific_permissions_exist(action) is True:
            return has_specific_permission(action)

        if object.use_governors_as_defaults is True:
            return has_default_permission(action)

        return "rejected"

# A Concrete Example

Imagine that you've got a community of 100 people.  The full membership owns the community and has foundational authority via a supermajority (2/3rds) vote.  To make life easier, they have elected a group of 5 governors who function as an executive council, handling a lot of stuff that's not explicitly specified in the PRs.  Unlike the owners, there are no conditions set on the governors.

Let's look at some actions that could be taken within the community and how they would get resolved.

1) Anne wants to add a post to the community discussion forum.  There is a permission item set on the forum which says that anyone can AddPost but with the condition that it be approved by a moderator.  When Anne adds her post, it skips the foundational_authority pipeline because the override has not been turned on and because her change is not ChangeFoundationalAuthorityOverride. It also never reaches the governors pipeline.  Instead it matches the specific permission that is set and gets set to 'waiting', and eventually a moderator reviews and accepts or rejects her post.

2) Betty thinks the rule about posts needing to be moderated is dumb.  She submits a change to the specific permission item to RemoveConditional.  There is no permission item set on the targetted permission item, so it ends up in the default permission pipeline and gets set to waiting.  Governor Charles agrees with Betty and accepts the change.  However the other governors are upset - by informal policy, changes to the system require consensus among the governors.  In the comments
on Betty's action, they discuss whether or not they actually want to keep this change.  They decide not to, and Charles submits an action changing the rule back, and approves it himself.

3) Governors Diego and Elsa are still upset about Charles' decision to accept the change and wants their informal consensus system to be formalized.  Diego submits a change to the AuthorityHandler adding a ConsensusConditional to the governor specification.  Once again, the action is set to waiting.  The community votes on Diego's action and the majority agree, so the AuthorityHandler is changed.

4) The community decides to re-add the forum moderation system and wants to be responsible for picking moderators, rather than delegating that power to the governors.  They submit a change to the permission item (the one with action AddPost) to toggle ChangeFoundationalAuthorityOverride.  The community votes to do this, and now they control the permission item.  They send a follow-up action to re-create the conditional, with FoundationalAuthorityOverride set to True for the conditional as well.

# Concepts to Ease Usability

## Roles

A key tool used within communities is something called a 'role set'.  This allows communities to specify roles like 'moderator' or 'admin' and assign specific people to those roles.  These roles can then be referenced throughout the community via permissions resources. 

Each permission has an action that is being permitted. It also has a field which indicates *who* has permission to take those actions.  This field can be designated through either or both of the individual actor list or the role list. The individual actor list is a list of unique IDs.  The role list is a list of tuples indicating a community and a role.  To see if an actor can take an action, the PR first looks in the individual list.  If the actor is not there, it goes through the tuples in the role list, querying each community to see if the actor in question has the given role, stopping and returning 'true/yes' if the answer is ever 'yes', and otherwise returning 'false/no'.

There are two types of roles that can be set in a community's role set:

* AssignedRoles: roles + individuals given that role
* AutomatedRoles: roles + rules to test if an  individual fits that role, for example "anyone older than X hours"

## Batched Actions 

[When you submit multiple things that require the same exact permissions (foundational OR specific permission match OR governors) you can request that they be processed in a batch all at at once, helpful for things like votes.]

## Community Defaults

By default upon creation, the foundational authority is set to the creator unconditioned, and the govering authority is set to the creator unconditioned. That governor can then configure the community to their heart's content.  That said, there are many other templates provided for people who want to start off with more complex community configurations.

# Implementation To-Dos

NEW PIPELINE:
- change permissions app to use items instead of resources - DONE
- change permissioned model to have override field - DONE
- reconfigure pipeline to match the description above (need to also incorporate check of individual vs community) - DONE

FOUNDATIONAL STUFF:
- check that authorityhandlerconditional works for governors - DONE
- check that it works for founders/owners
- check that foundation override works
- check that authorityhandler and authorityhandlerconditional can only be changed by foundational authority 

- check that creating something within a community assigns ownership to community rather than individual

EXTENSIONS:
- roles
- batched actions







