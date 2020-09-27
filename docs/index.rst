.. Concord documentation master file, created by
   sphinx-quickstart on Wed Jan 29 13:25:13 2020.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

About Concord
&&&&&&&&&&&&&

Concord is a Python (Django) library that can be used by developers to build sites with comprehensive,
customizable, dynamic, and most importantly *user-determined* community governance.  It can be added to existing
websites with Django backends or used to create a new site from scratch.

.. contents::

Motivation
**********

At its heart, governance revolves around a single question: who gets to do what? Take the United States Constitution. Article 1, Section 8, Clause 2 says Congress can “borrow Money on the credit of the United States”. Congress is the who.  Borrowing money is the what. The more famous First Amendment says Congress can’t establish a religion. Congress, again, is the who, and establishing a religion is the what - something they don’t get to do.

There’s more to governance than simply laying out these rules: there’s wrangling over definitions, questions of fair and unfair enforcement, new rules to be made and old rules to be changed, as time and circumstances and beliefs about right and wrong shift. But “who gets to do what” describes a lot of the most important questions we ask about governance.

We learn about governance from the society we’re born into, and every culture has different models of governance it emphasizes.  In the United States, the two most common models of governance are representative democracy and dictatorship.  Although other governance models exist (for example, in jury selection, or in the oligarchical structure of many non-profits), representative democracy and dictatorship are most commonly found in our institutions and our culture.  It may seem odd to claim we can commonly find dictatorships in the United States, but most for-profit corporations in the United States are run as dictatorships, and many informal projects run by their founders use a structure that the open source community calls “benevolent dictator for life”.

Given the dictator-like governance structure of most corporations, it’s no surprise that most digital platforms - designed and run by corporations - implement only dictatorships.  Sure, a Facebook group or a subreddit may allow the owner to delegate many rights to individual users, but there is always one person who has ultimate control.  While this structure reflects the values of the corporate platform, it does not reflect the values of American society, as they offer no ability to implement representative democracy.  Nor does it give users access to the vast and fascinating variety of governance structures that have been tried and tested, or even just imagined, across the history of the world.

Concord seeks to enable communities to experiment with a variety of forms of self-governance, to find which structures best suit their needs.  They may end up with a structure very like a dictatorship, but it will be their choice and require their consent.  Or they may end up with a managed commons, or a sortition-based system like in ancient Athens, or a consensus model like those practiced by Quakers and radical activists, or, or, or…

Design Overview
***************

The fundamental design units in Concord are actions and permissions.  Actions contain information about who is taking the action, what they’re taking the action on, and what, specifically, they want to do.  These objects concretize the question highlighted above: *who* can do *what* to *what*?  Permissions are the answer to that question.

Changes of state within a web app can be “wrapped” within an Action object. Action objects are then applied against zero, one, or many permissions.  If any of the permissions are granted, the Action “passes” and is implemented.  Users may be granted permissions individually or based on the “role” they hold, and conditions may be placed on permissions so that additional steps (approval, a vote, etc) must be taken after the permission passes but before the Action is implemented.  The flexibility of this system can lead to quite complex configurations, and so we also offer templates, which allow users to implement a complex configuration with the click of a button.

Actions and Permissions
-----------------------

Action objects are Django models. The three most important fields on an Action object are “actor”, “target”, and ":ref:`change <change-objects>`".  The actor is whoever is taking the action (always a user); the target is any Django model within the system that accepts actions (called a ‘permissioned model’); and the change field details the specific changes that the user wants to make.

Once the change has been validated the Action is run through the ‘permissions pipeline’.  The pipeline checks to see if any ":ref:`Permissions <permissions>`" have been set on the Action’s target.  These Permissions also have change fields which are nearly identical to those set on actions.  We compare the change fields of the Action and the Permission and, if they match, we check to see if the Action actually passes the Permission.

We determine if an Action passes a Permission by checking its “roles” and “actors” fields.  A permission may be granted to individuals (“actors”) or to roles (simple names associated with a list of actors).  If a user is either listed as an individual actor in the Permission, or if they are assigned a role listed in the Permission, they will pass the Permission.

Communities and Roles
---------------------

All Actions in the Concord system take place within Communities.  There can be a single large Community covering all actions on the site or, more commonly, users can choose to create their own communities on a platform.

All permissioned models are owned by a community.  When we say that, for example, all users with role “administrators” have permission to make a certain type of change, we are referring to the role set on the owning community.  (Our long term goals include allowing for federations of communities and sub-communities, at which point we will likely allow permissions to reference roles set on other communities.)

Communities can have an arbitrary number of roles and those roles can be included in an arbitrary number of permissions.  There are three special types of roles, which all communities have: members, owners, and governors.

The member role is more or less self-explanatory: all members of the community are given the “member” role.  This may grant them many permissions, or none, or something in between.  But a user may not be granted any additional roles until they have the member role.

People with the “owner” role are the foundational source of authority within the system.  They may do whatever they want with the community - for instance, kick out all the members or even delete it.  Given this power, there should always be conditions set on their actions.  We will talk about conditions in more detail soon, but for now, just imagine a community where all members are also owners.  The condition set on them taking action might be, for instance, a supermajority vote.

But holding a vote every time someone wants to make a change in the system will quickly get very tedious.  This is especially true when communities are young and don’t have an established, stable system of roles and permissions yet.  Communities may want to grant a broad discretion to certain trusted individuals.  These are “governors”.  Governors may also have conditions set on their actions, but these conditions if they exist are almost always less onerous than those set on owners.  However, if governors abuse their discretion, they can be removed by the owners.

With this added context, we can better understand the “:ref:`permissions pipeline<permissions-pipeline>`” that actions go through.  When an action enters the pipeline, we first check whether or not the change is of a special type (eg “delete the community”, “change owner of community”, “change governor of community”) that only the owners can take.  If this is the case, we check only to see if the actor is an owner - if they are, the action passes; if not, the action is rejected.  If the change is not of a special type, we proceed to checking whether the actor is a governor - if they are; the action passes; if not, the action continues through the pipeline.  Finally, we look for specific permissions set on the target of the action.  Once again, we check if an actor matches and passes those permissions.  If they pass a permission, the action as a whole passes, otherwise it is rejected.

Conditions
----------

If someone has a permission to do something, they will be immediately able to do it.  But communities may want to grant permissions while still providing a check on their actions. For this, we use conditions. Conditions may be set on individual permissions or on the roles of “owner” and “governor” as a whole. In the later case, conditions would apply to every action a user took as an owner or as a governor.

There are currently two types of conditions available: ‘Approval’ and ‘Voting’.  When an approval condition is applied to a permission, someone trying to take an action that triggers that permission will require one person’s approval.  When a voting condition is applied to a permission, someone trying to take an action that triggers that permission will need to wait for people to vote on whether their action should pass.

Conditions always require configuration when they’re set.  That’s because we always need to know who can take action on the condition.  Conditions also usually have additional configuration.  For instance, the voting condition lets you set a voting period, let voters abstain or not, and lets you pick whether a majority or only a plurality is needed to pass.

We have designed Concord so that it is relatively easy to plug in new condition types.  We hope to add soon a Consensus condition as well as various other voting conditions like Ranked Choice, Quadratic, and Liquid.

On our roadmap is the incorporation of ‘filter’ conditions.  As opposed to decision-making conditions, which require interactions from the community to resolve, ‘filter’ conditions would automatically apply existing information to determine whether the action can proceed, eg “this action may be taken if the user was created over one week ago” or “this action may be taken if the user has taken no other similar actions in the last twenty-four hours”.  As with decision-making conditions, they would be configured by the community and could be adjusted over time.

Learn more about “:ref:`how condition models work<condition-models>`” or learn :doc:`how to add a condition<how_to_add_condition>`.

Templates
---------

The system described provides the building blocks for a large variety of governance systems. But it may be difficult for new users to build such systems from scratch, and even experienced governance-framers can benefit from access to the innovations of others.  As such, we have a template system which allows users to apply pre-defined sets of permissions to their communities.

Templates have a variety of “scopes”, which allow users to narrow their search within the template library. A template with “community” scope will likely make broad changes, for example by creating a role ‘voting members’ and making them owners, with a condition of a three-day-long majority vote.  A template with a more narrow “membership” scope will only set permissions related to membership, for example by specifying that anyone may request to be a member of the community but they must get two approvals from role “membership admins”.  Each template has a “plain English” name and description, along with a detailed list of the actual changes a template will make when you apply it.

Currently, templates must be defined by developers behind the scenes, but on our roadmap is the creation of an interface for users to develop templates themselves.

Want to contribute to our templates library? Learn :doc:`how to add templates<how_to_add_template>`.

Development Guide
*****************

Using and Extending Concord
---------------------------

Concord is build to be resuable and extensible. Currently, the three main ways to extend Concord are by adding conditions, adding permissioned models, and adding templates.  These can be done as part of building a new site, or can be contributed back to the Concord project core.

When you add a new condition, it will be added to the list of conditions which may be set on permissions or on the "owner" and "governor" roles.  Users will be able to configure and set it, and when an action triggers it a link to it will be created in the action history view.  Adding a new condition requires: defining the condition model and the required methods (such as how the status of the condition is determined); creating change objects corresponding to actions taken on that condition, such as AddVote or Approve; creating a simple client to expose the change objects; and creating a default template for interacting with the condition on the front end.  Depending on the complexity of the condition and the experience of the developer creating it, we estimate that adding new conditions takes a day or two of worker. To learn more, read the guide on :doc:`how to add a condition<how_to_add_condition>`.

Creating new permissioned models (also refered to as resources) is a similar process to adding conditions (after all, a condition is a type of permissioned model).  Developers will create a new Django model which inherits from PermissionedModel and define their own custom fields on it.  They must then add change objects and corresponding client methods to control when an instance's data can be changed.  It is up to the developer how to add the permissioned model as a template - the default is "create a Vue component for this Django model" but in practice the template design will be driven by the data model. To learn more, read the guide on :doc:`how to add a permissioned model/resource<how_to_add_resource>`.

Currently we add templates by writing a template function in template_library.py.  Adding templates can be very quick (under an hour) with the bulk of the work largely coming from adding tests to make sure the template is doing what you expect it to do. To learn more, read the guide on :doc:`how to add a template<how_to_add_template>`.

Tools and Frameworks Used
-------------------------

Concord currently relies heavily on two languages and two frameworks. Concord's back end logic is implemented as a Django (Python) package, and made avaialble through AJAX views, which return data as JSON for the front end to use. Developers may implement a completely custom front end, but Concord provides some default templates using the Javascript framework Vue. We are working on making the templates as modular as possible, so developers can create their own front end but re-use, for instance, the interface for interacting with permissions and conditions, or the inteface for viewing action history.


.. toctree::
   :hidden:
   :maxdepth: 2
   :caption: More Info

   index
   deep_dives
   how_to_add_template
   how_to_add_condition
   how_to_add_resource
   example_implementation

.. toctree::
   :hidden:
   :maxdepth: 2
   :caption: Autodocs

   Actions <autodocs/actions>
   Communities <autodocs/communities>
   Conditionals <autodocs/conditionals>
   Permissions <autodocs/permission_resources>
   Resources <autodocs/resources>

.. toctree::
   :hidden:
   :maxdepth: 2
   :caption: Search Utilities

   genindex