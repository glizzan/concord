How to Add a Condition
######################

Conditions are placed on permissions and come into effect when a user wants to take an action. If a person has permission to take the action, either through a specific permission being set or because they're an owner or governor, and a condition is set, they must also pass the terms of that condition.

The output of a condition is always one of three things: "approved", "rejected" and "waiting".  Additional data can be created by the condition, but that output is what the permissions system actually uses.

Right now, the only kind of condition that exists is a *decision* condition. Decision conditions require a decision - that is, at least one more action - by members of the community. The simplest decision condition is the Approval Condition, which requires a person to approve. Eventually, we will be adding automatic conditions, like "this person must have been in the group for two weeks" or "this person does not have the flag 'suspended'", and compound conditions, which allow us to specify a combination of conditions to be satisfied.

But that's getting ahead of ourselves. For now, let's stick to what we have.

Step 1: Planning Out Your Condition
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

It's always helpful to take some time to think through what you want the condition to do before you start coding.

Our condition is going to allow people to decide things by consensus. The options for people participating in the consensus condition will be "support", "support with reservations", "block" and "stand aside".

We'll also have two modes that the person setting the condition can choose from, "strict" and "loose". With strict consensus, all participants in the consensus process must actively choose one of the four options listed above for the condition to be resolved. With loose consensus, the only requirement is that no one block. But in that case, how do we know when a loose consensus process is finished? For that matter, how do we know if a "strict" consensus process is finished - what if, even though everyone's given an initial response, people want to keep discussing?

We'll have a special "resolve" action that can be taken on our consensus. When the resolve action is taken, no more responses can be added. Instead, we figure out the result with whatever responses are there at the moment of resolution.

If you've got a devious brain, you may have noticed some potential for abuse: what if someone prompts a loose consensus action and then immediate resolves it? No one will have blocked because no one will have had a chance to see it! So let's also add a minimum duration, before which the condition cannot be resolved.

Finally, let's require that in order for any consensus item to pass, at least one person actively supports it, either with reservations or without - we can't have all "stand asides" (or "no responses" and "stand asides", for loose consensus).
m_duration field
Step 2: Creating A Condition Model
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The heart of a condition is the Condition Model, where all the Condition's logic lives.  New conditions are added in ``concord.conditionals.models.py`` and all condition model objects must descend from the ``ConditionModel`` defined in that module.

We'll start by specifying the fields we'll need for the condition to function:

.. code-block:: python

    class ConsensusCondition(ConditionModel):

        resolved = models.BooleanField(default=False)

        is_strict = models.BooleanField(default=False)
        responses = models.CharField(max_length=500, default="[]")

        minimum_duration = models.IntegerField(default=48)
        discussion_starts = models.DateTimeField(default=timezone.now)

        response_choices = ["support", "support with reservations", "stand aside", "block"]

The ``resolved`` field stores whether or not the resolved action has been taken.  ``is_strict`` stores the mode a particular consensus process is in. The ``responses`` field stores the responses of individual participants. The ``minimum_duration`` field stores the minimum length of the decision-making process while the ``discussion_starts`` stores when the discussion started, so the 'okay' point can be calculated from it using the duration. The ``response_choices`` field is not a model field, and technically could be specified elsewhere, but we'll keep it here where it's easy to find.

This seems good enough for now - we can always come back to add more fields later.

ConditionModel has a variety of abstract methods on it that *must* be implemented by any condition model descending from it. Let's start with ``condition_status``.  This is the method which returns "approved", "rejected" or "waiting".

.. code-block:: python

    def condition_status(self):
        """This method returns one of status 'approved', 'rejected', or 'waiting', after checking the condition
        for its unqiue status logic."""

``condition_status`` should never take in any parameters. The status should be inferrable from information contained on the condition itself.  Let's try to think through the logic of our condition status:

* if the condition is not resolved, we should return "waiting"
* if the condition is resolved, and the mode is strict, and people haven't participated, we should "reject"
* if the condition is resolved, and the mode is strict, and everyone's participated, and there's a block or no supporters, we should "reject"
* if the condition is resolved, and the mode is strict, and everyone has participated, and there's no block and some supporters, we should "approve"
* if the condition is resolved, and the mode is loose, and there's a block or no supporters, we should "reject"
* if the condition is resolved, and the mode is loose, and there's no blocks and some supporters, we should "approve"

We can instantiate this logic in our condition status method:

.. code-block:: python

    def condition_status(self):

        if not self.resolved:
            return "waiting"
        if self.is_strict:
            if self.full_participation():
                if self.has_blocks() or not self.has_support():
                    return "rejected"
                return "approved"
            return "rejected"
        if self.has_blocks() or not self.has_support():
            return "rejected"
        return "approved"

When building this method we want to take special care that we're always returning one of those three terms. The most common error here is to accidentally return None by making a mistake with the code.  Here, though, we can see that there's no way to go through this code without returning one of our strings - every if/else ends with a return statement.

Let's actually split up this method into two, so we can, separately, check what the current result is:

.. code-block:: python

    def condition_status(self):

        if not self.resolved:
            return "waiting"
        return self.current_result()

    def current_result(self):
        if self.is_strict:
            if self.full_participation():
                if self.has_blocks() or not self.has_support():
                    return "rejected"
                return "approved"
            rreturn "rejected"
        if self.has_blocks() or not self.has_support():
            return "rejected"
        return "approved"

It's the exact same logic, just separated into two methods.  In addition to relying on our existing fields (``resolved`` and ``is_strict``), this method relies on three helper methods, ``full_participation``, ``has_blocks`` and ``has_support``.  Let's fill those out.

To work on these methods, we need a better sense of what that ``responses`` field looks like.  Let's imagine it's a dictionary with participants' unique IDs as keys and their response as a value.  If the value is null, that means they haven't responded yet.

Let's start by creating a helper method which generates this dictionary given a list of users, which will be supplied when creating the condition.

.. code-block:: python

    def create_response_dictionary(self, participant_pk_list):
        response_dict = {pk: "no response for pk in participant_pk_list}
        self.responses = json.dumps(response_dict)

Because we're storing the data as JSON, we'll need another helper method just to access the data:

.. code-block:: python

    def get_responses(self):
        return json.loads(self.responses)

Now we're ready to build our ``full_participation`` and ``has_blocks`` methods:

.. code-block:: python

    def full_participation(self):
        for user, response in self.get_responses().items():
            if response == "no response":
                return False
        return True

    def has_blocks(self):
        for user, response in self.get_responses().items():
            if response == "block":
                return True
        return False

    def has_support(self):
        for user, response in self.get_responses().items():
            if response in ["support", "support with reservations"]:
                return True
        return False

Let's tackle that ``resolve`` field next.  We need a helper method that determines whether the condition can be resolved.  We'll use this later to determine whether a person's "resolve" action is valid.

.. code-block:: python

    def time_until_duration_passed(self):
        seconds_passed = (timezone.now() - self.discussion_starts).total_seconds()
        hours_passed = seconds_passed / 360
        return self.minimum_duration - hours_passed

    def ready_to_resolve(self):
        if self.time_until_duration_passed() <= 0:
            return True
        return False

We moved the ``time_until_duration_passed`` calculations into a separate method because we will likely want to access it on the front end, to show users how much time remains until the condition can be resolved.

We will be coming back and adding more to our model, but for now this is enough to be getting on with.

Step 3: Writing State Changes for Your Condition
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The next step is to write state changes which control how the condition can be updated. All state changes should be placed in a file named ``state_changes.py`` and should descend from ``BaseStateChange`` which can be imported from ``concord.actions.state_changes``.

 Let's create a stub for our first state change, which will control how people add responses to the consensus condition:

.. code-block:: python

    class RespondStateChange(BaseStateChange):
        """State change for responding to a consensus condition"""
        description = ""
        section = ""
        verb_name = ""
        input_fields = []

        def __init__(self, response):
            ...

        @classmethod
        def get_allowable_targets(cls):
            ...

        def description_present_tense(self):
            ...

        def description_past_tense(self):
            ...

        def validate(self, actor, target):
            ...

        def implement(self, actor, target):
            ...

The set of attributes above are there to allow the state change to be used and displayed in various ways by the system, and can occasionally seem a little redundant. ``description`` is a short, simple description of what the state change does, in this case "Respond" will do just fine. ``preposition`` helps us correctly use the state change in an English sentence. The default preposition if none is specified is "to" which works for this state change, so we can remove that attribute. Next is ``section`` - this helps the front end group permission options when offering them to the user. We'll put it as "Consensus". ``verb_name`` is an all-lower-case term again used for providing human-readable descriptions of what's happening, so "respond" works here.

Finally, ``input_fields``, which is a bit more complex. It helps us provide metadata for the parameters supplied to init, in this case "response". To do this, we import InputField, which is just a named tuple with four fields: name, type, required, and validate. Name should exactly correspond to the input parameter's name; type should be one of a dozen or so options for field types, including standard Django field types like BooleanField and CharField as well as Concord-specific field like ActorListField or RoleListFild; required indicates whether the field is required; and validate indicates whether the field should be checked when the change object is being validated.

Putting it all together, we fill out the attributes & init like this:

.. code-block:: python

    class RespondStateChange(BaseStateChange):
        """State change for responding to a consensus condition"""
        description = "Respond"
        preposition = ""
        section = "Consensus"
        verb_name = "respond"
        input_fields = [InputField(name="response", type="CharField", required=True, validate=False)]

        def __init__(self, response):
            self.response = response

The ``description_past_tense`` and ``description_present_tense`` are two additional methods helping us display English langauge descriptions of the actions. They can reference data supplied in ``__init__`` so can be more precise. ``get_allowable_targets`` lists the permissioned models that the state change can be applied to. In this case, the only valid option is the ConsensusCondition.

.. code-block:: python

    @classmethod
    def get_allowable_targets(cls):
        return [ConsensusCondition]

    def description_present_tense(self):
        return f"respond with {self.response}"

    def description_past_tense(self):
        return f"responded with {self.response}"

Next let's fill out our validation method.  We start by calling the super() method which checks that the target of the action is one of the allowable targets, and also validates any input_fields that have validate=True. Then we provide validation specific to this action:

.. code-block:: python

    def validate(self, actor, target):
        """Checks that the actor is a participant."""
        if not super().validate(actor=actor, target=target):
            return False

        if self.response not in target.response_choices:
            self.set_validation_error(
                f"Response must be one of {', '.join(target.response_choices)}, not {self.response}")
            return False

        return True

Finally, we tell the state change how to actually implement the action in the database:

.. code-block:: python

    def implement(self, actor, target):
        target.add_response(actor, self.response)
        target.save()
        return self.response

Again, we need a helper method:

.. code-block:: python

    def add_response(self, actor, new_response):
        responses = self.get_responses()
        for user, response in responses.items():
            if user == actor.pk:
                responses[user] = new_response
        self.responses = json.dumps(responses)

Note that we never save the condition model from the condition model. In fact, we can't - the system will raise an error if we try.  Instead, we always save from the implement method of a state change.

Putting it all together, our state change looks like this:

.. code-block:: python

    class RespondStateChange(BaseStateChange):
        """State change for responding to a consensus condition"""
        description = "Respond"
        preposition = ""
        section = "Consensus"
        verb_name = "respond"
        input_fields = [InputField(name="response", type="CharField", required=True, validate=False)]

        def __init__(self, response):
            self.response = response

        @classmethod
        def get_allowable_targets(cls):
            return [ConsensusCondition]

        def description_present_tense(self):
            return f"respond with {self.response}"

        def description_past_tense(self):
            return f"responded with {self.response}"

        def validate(self, actor, target):
            """Checks that the actor is a participant."""
            if not super().validate(actor=actor, target=target):
                return False

            if self.response not in target.response_choices:
                self.set_validation_error(
                    f"Response must be one of {', '.join(target.response_choices)}, not {self.response}")
                return False

            return True

        def implement(self, actor, target):
            target.add_response(actor, self.response)
            target.save()
            return self.response

The other change a user will want to make to a consensus condition is to resolve it. That state change will look like this:

.. code-block:: python

    class ResolveConsensusStateChange(BaseStateChange):
        """State change for resolving a consensus condition."""
        description = "Resolve"
        preposition = ""
        section = "Consensus"
        verb_name = "resolve"

        @classmethod
        def get_allowable_targets(cls):
            return [ConsensusCondition]

        def description_present_tense(self):
            return f"resolve"

        def description_past_tense(self):
            return f"resolved"

        def validate(self, actor, target):
            """Checks that the actor is a participant."""
            if not super().validate(actor=actor, target=target):
                return False

            if not target.ready_to_resovlve():
                self.set_validation_error("The minimum duration of discussion has not yet passed.")
                return False

            return True

        def implement(self, actor, target):
            target.resolved = True
            target.save()
            return target

Step 4: Condition Creation
^^^^^^^^^^^^^^^^^^^^^^^^^^

Some condition types don't require any special data on creation, but in our case, we want to specify a set of participants in the discussion. (We might also want to give people the ability to add new participants later, in which case we'd need a third state change - AddParticipant - but we'll leave that as an exercise for the reader.)

Instances of Conditions are created by code in ``SetConditionOnActionStateChange`` in the ``conditionals.state_changes.py``. That code calls a method ``initialize_condition`` on that condition model that we can customize for our model. That method takes in parameters ``target``, ``condition_data``, and ``permission_data``.

What we're looking for here is ``permission_data``, which determines who can take action on our consensus condition. We want to find the permission associated with the RespondConsensusStateChange, and use the actors and roles specified there to populate our list of participants.

The condition may also be set not on a specific permission but on a leadership type. The leadership type will be one of two options: owner or governor. We should only ever be grabbing our participants from the permission *or* owners *or* governors.

As we create our participants we store them as a set (a data type with no duplicates) so each participant has one response, even if they qualify through multiple roles.

.. code-block:: python

    def initialize_condition(self, target, condition_data, permission_data, leadership_type):
        """Called when creating the condition, and passed condition_data and permission data."""

        client = Client(target=target.target.get_owner())
        participants = set([])

        for permission in permission_data:
            if permission["permission_type"] == Changes().Conditionals.RespondConsensus:
                if permission["permission_roles"]:
                    for role in permission["permission_roles"]:
                        for user in client.Community.get_users_given_role(role_name=role):
                            participants.add(user)
                if permission["permission_actors"]:
                    for actor in permission["permission_actors"]:
                        participants.add(int(actor))

        if leadership_type == "owner":
            for action in client.get_users_with_ownership_privileges():
                participants.add(int(actor))

        if leadership_type == "governor":
            for action in client.get_users_with_governorship_privileges():
                participants.add(int(actor))

        self.create_response_dictionary(participant_pk_list=list(participants))

Step 5: Interacting Via Client & Views
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

We need to create mechanisms for interacting with our consensus condition. We'll start by creating a client for people to call:

.. code-block:: python

    class ConsensusConditionClient(BaseClient):
        """The target of the ConsensusConditionClient must always be a ConsensusCondition instance."""

        # Read only

        def get_current_results(self) -> Dict:
            """Gets current results of vote condition."""
            return self.target.get_responses()

        # State changes

        def respond(self, *, response: str) -> Tuple[int, Any]:
            """Add response to consensus condition."""
            change = sc.RespondStateChange(response=response)
            return self.create_and_take_action(change)

        def resolve(self) -> Tuple[int, Any]:
            """Resolve consensus condition."""
            change = sc.ResolveConsensusStateChange()
            return self.create_and_take_action(change)

We'll also add some views that call the client, so that we can interact with our condition via an API:

.. code-block:: python

    @login_required
    def update_consensus_condition(request):

        request_data = json.loads(request.body.decode('utf-8'))
        condition_pk = request_data.get("condition_pk", None)
        action_to_take = request_data.get("action_to_take", None)
        response = request_data.get("response", None)

        consensusClient = Client(actor=request.user).Conditional.\
            get_condition_as_client(condition_type="ConsensusCondition", pk=condition_pk)

        if action_to_take == "respond":
            action, result = consensusClient.respond(response=response)
        elif action_to_take == "resolve":
            action, result = consensusClient.resolve()

        return JsonResponse(get_action_dict(action))

And of course we need to add a reference in urls.py so it actually works:

.. code-block:: python

    path('api/update_consensus_condition/', views.update_consensus_condition, name='update_consensus_condition'),

Finally, we're going to add a signal for our condition, so that when it updates, we check and see if the action it's set on now passes:

.. code-block:: python

    for conditionModel in [ApprovalCondition, VoteCondition, ConsensusCondition]:
        post_save.connect(retry_action, sender=conditionModel)


Step 6: Default Front-End Implementation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The next thing we want to do is build a front-end implementation of this condition so it can be used on actual websites. Projects may end up override some or all of this implementation, but we want to give them a plug-and-play solution to use by default, and the process of doing this will also explain a few additional fields and methods we'll be adding to our Consensus Condition model.

The default system is built using the Vue framework. Most condition interfaces are a single Vue component on a single page, which are including in the detail view for the action that triggers the condition.  That view has a place for discussion, which is where we assume the discussion necessary to reach consensus will take place.

So we don't need to build an interface for discussion, just a way for users to see the current status of the condition and make any changes they want to.  We'll start by building the html part of our component:

.. code-block:: html

    <script type="text/x-template" id="consensus_condition_template">

        <span>

            <!-- Information about the discussion. -->

            <h5 class="my-2">Discussion Status</h5>

            <span v-if="is_resolved">The condition was resolved with resolution [[ condition_resolution_status]].
                <span v-if="response_selected">Your response was <b>[[response_selected]]</b>.</span>
            </span>
            <span v-else>
                <span v-if="can_be_resolved">The minimum duration of [[ minimum_duration ]] has passed. If the discussion
                    was resolved right now, the result would be: [[ current_result ]].
                    <b-button v-if="can_resolve" class="btn-sm" variant="outline-secondary" @click="resolve_condition()">
                        Resolve this discussion?</b-button>
                </span>
                <span v-else>The discussion cannot be resolved until the minimum duration of [[ minimum_duration]] has passed.
                    This will happen in [[ time_remaining ]].
                </span>
            </span>

            <b-container class="bv-example-row border border-info my-2 p-2" id="consensus_responses">
                <b-row><b-col class="text-center my-2">Current Responses</b-col></b-row>
                <b-row class="font-weight-bold">
                    <b-col>Support</b-col><b-col>Support With Reservations</b-col><b-col>Stand Aside</b-col><b-col>Block</b-col>
                    <b-col>No Response</b-col>
                </b-row>
                <b-row>
                    <b-col>[[get_names(response_data.support)]]</b-col>
                    <b-col>[[get_names(response_data.support_with_reservations)]]</b-col>
                    <b-col>[[get_names(response_data.stand_aside)]]</b-col>
                    <b-col>[[get_names(response_data.block)]]</b-col>
                    <b-col>[[get_names(response_data.no_response)]]</b-col>
                </b-row>
            </b-container>

            <!-- Interface for changes -->

            <div v-if="!is_resolved" class="my-3">
                <span v-if="can_respond">
                    <b-form-group label="Your Response">
                        <b-form-radio-group id="user_response_radio_buttons" v-model="response_selected" :options="response_options"
                            button-variant="outline-info" buttons name="user_response_radio_buttons"></b-form-radio-group>
                    </b-form-group>
                    <b-button class="btn-sm" @click="submit_response()">Submit</b-button>
                </span>
                <span v-else>You are not a participant in this consensus discussion.</span>
            </div>

            <span v-if="error_message" class="text-danger">[[ error_message ]]</span>

        </span>
    </script>

There's a bunch of different logic here, and we're using a lot of variables that we still need to define on our component. But for now, notice how the template falls into three main sections:

The top-most section provides information about the overall status of the resolution. We show the user different things based on whether the condition is resolved, able to be resolved, or not able to be resolved. If it can be resolved and the user has permission to resolve it, we give them the option to do so, along with the helpful information of what the result will be if the condition resolves right now.

The next section displays the list of current responses. Our responses are stored as a list of pks, so we call the ``get_names`` method to look up their username and turn them into a comma-separated list.

Finally, in the bottom section, if the user has permission to respond they are given the option to do so. Their current response (which defaults to 'no response' is pre-selected for them).

Now let's go ahead and make our component.  We'll start from the template that all components have, with only the name of the component changed:

.. code-block:: javascript

    consensusConditionComponent = Vue.component('consensus-condition-ui', {
        delimiters: ['[[', ']]'],
        template: '#consensus_condition_template',
        props: ['condition_type', 'condition_pk', 'action_details'],
        store,
        data: function() {
            return {
                error_message: null,
                permission_details: null,
                condition_details: null,
            }
        },
        computed: {
        },
        created () {
            this.get_conditional_data()
        },
        methods: {
            ...Vuex.mapActions(['addOrUpdateAction']),
            get_axios() {
                axios.defaults.xsrfCookieName = 'csrftoken';
                axios.defaults.xsrfHeaderName = 'X-CSRFTOKEN';
                axios.defaults.headers = { "headers": { 'Content-Type': "application/json" } }
                return axios
            },
            get_conditional_data() {
                axios = this.get_axios()
                url = "{% url 'get_conditional_data' %}"
                params = { condition_pk: this.condition_pk, condition_type: this.condition_type }
                return axios.post(url, params).then(response => {
                    this.permission_details = response.data.permission_details
                    this.condition_details = response.data.condition_details
                    for (field in this.condition_details.fields) {
                        name = this.condition_details.fields[field]["field_name"]
                        value = this.condition_details.fields[field]["field_value"]
                        Vue.set(this, name, value)
                    }
                    this.set_user_response()
                }).catch(error => {  console.log(error)  })
            },
            update_action(new_action_pk) {
                // update action this was a condition on
                this.addOrUpdateAction({ action_pk: this.action_details["action_pk"] })
                // also call vuex to record this as an action (need to do this for all actions)
                this.addOrUpdateAction({ action_pk: new_action_pk })
            },

        }
    })

Most of the above needs to be wrapped into a mixin so you don't need to define it yourself, sorry.  But, quickly: ``get_condition_data`` gets data on the condition from the backend, and adds all the fields on the condition to the component for easy access. ``update_action`` handles making sure data about the actions we're taking (or influencing, through the condition) makes it back to the action vuex store so it can be referenced elsewhere on the site. The rest is configuration for axios, which we use to talk to the backend.

Now let's create the variables and methods for all the things we listed in our template. The data section is very straightforward, everything is populated elsewhere in the component so we can just set everything to null:

.. code-block:: javascript

    data: function() {
        return {
            error_message: null,
            permission_details: null,
            condition_details: null,
            // select data
            response_selected: null,
            // fields that will be automatically filled by getConditionData
            minimum_duration: null,
            time_remaining: null,
            can_be_resolved: null,
            responses: null,
            response_options: null,
            current_result: null
        }
    },

The computed section has a bit more going on:

.. code-block:: javascript

    computed: {
        ...Vuex.mapGetters(['getUserName']),
        can_respond: function() {
            if (this.permission_details) {
                return this.permission_details["concord.conditionals.state_changes.RespondConsensusStateChange"][0]
            }
        },
        can_resolve: function() {
            if (this.permission_details) {
                return this.permission_details["concord.conditionals.state_changes.ResolveConsensusStateChange"][0]
            }
        },
        is_resolved: function() {
            if (this.condition_details) {
                if (["approved", "rejected", "implemented"].includes(this.condition_details.status)) {
                    return true
                } else { return false }
            }
        },
        response_data: function() {
            response_dict = {}
            if (this.response_options) {
                this.response_options.forEach(response_option => response_dict[response_option.replace(/\s/g, "_")] = [])
                for (user in this.responses) {
                    response_dict[this.responses[user].replace(/\s/g, "_")].push(user)
                }
            }
            return response_dict
        },
        condition_resolution_status: function() { if (this.condition_details) { return this.condition_details.status }}
    },

``can_respond`` and ``can resolve`` look up whether the user has the corresponding permissions associated with the condition. This information is automatically supplied by the back end, we just need to know which permission we're looking for.  The status attribute on ``condition_details`` is also automatically supplied. The only complex thing happening here is in ``response_data``, where we're reformatting from the dictionary of user pk keys and response values to make 'collections' of values for us to display. When we do this, we're turing "No Response" into no_response so we can access it in our template.

Let's move on to the methods.  We've got two little helper methods here:

.. code-block:: javascript

        get_names(pk_list) {
            if (pk_list) {
                name_list = []
                pk_list.forEach(pk => name_list.push(this.getUserName(parseInt(pk))))
                return name_list.join(", ")
            } else { return "" }

        },
        set_user_response() {
            user_pk = parseInt("{{request.user.pk}}")
            for (user in this.responses) {
                if (user == user_pk) { this.response_selected = this.responses[user] }
            }
        },

``get_names`` is looking up user names using the ``getUserName`` method defined in the Governance Vuex include and imported in the computed section like so:

.. code-block:: javascript

    computed: {
        ...Vuex.mapGetters(['getUserName']),

``set_user_response`` gets the logged in user and looks for their response in the response dictionary. We use this primarily to pre-select the right radio button.

The two final methods are the calls to the backend. Let's look at ``submit_response`` first:

.. code-block:: javascript

    submit_response() {
        if (!this.response_selected) { this.error_message = "Please select a response" }
        if (this.response_selected == this.user_response) { this.error_message = "Your response has not changed"; return }
        url = "{% url 'update_consensus_condition' %}"
        params = { condition_pk: this.condition_pk, action_to_take: "respond", response: this.response_selected }
        axios.post(url, params).then(response => {
            if (["implemented", "waiting"].indexOf(response.data.action_status) > -1) {
                this.update_action(response.data.action_pk)
                this.get_conditional_data().catch(error => { this.error_message = error })
            } else {
                this.error_message = response.data.action_log
            }
        }).catch(error => {  console.log("Error updating condition: ", error); this.error_message = error })
    },

We do a little bit of client-side validation, checking that a response has been selected and it's different from what their current response in the back end.  Then we submit that data to our backend and do some more error handling on the response.  Note that on success we update all the actions and refresh the condition data from the backend.

``resolve_condition`` looks very similar:

.. code-block:: javascript

    resolve_condition() {
        url = "{% url 'update_consensus_condition' %}"
        params = { condition_pk: this.condition_pk, action_to_take: "resolve" }
        axios.post(url, params).then(response => {
            if (["implemented", "waiting"].indexOf(response.data.action_status) > -1) {
                this.update_action(response.data.action_pk)
                this.get_conditional_data().catch(error => { this.error_message = error })
            } else {
                this.error_message = response.data.action_log
            }
        }).catch(error => {  console.log("Error updating condition: ", error); this.error_message = error })
    }

The last thing we need to do is make sure our new component is hooked up.  We need to add the file itself to the list of includes imported in ``html_templates_to_include.html`` with the line: ``{% include 'groups/actions/consensus_condition_component.html' %}``

We also need to add a reference in the ``action_detail`` template:

.. code-block:: html

    <b-card border-variant="secondary" class="my-3" v-if="condition_type">

            This action has a condition on it.  To pass the condition, [[ condition_pass ]].

            <approve-condition-ui v-if="condition_type=='ApprovalCondition'" :condition_pk=condition_pk
                :condition_type=condition_type :action_details=action></approve-condition-ui>

            <vote-condition-ui v-if="condition_type=='VoteCondition'" :condition_pk=condition_pk
                :condition_type=condition_type :action_details=action></vote-condition-ui>

            <consensus-condition-ui v-if="condition_type=='ConsensusCondition'" :condition_pk=condition_pk
                :condition_type=condition_type :action_details=action></consensus-condition-ui>

    </b-card>

Finishing Up in the Back End
@@@@@@@@@@@@@@@@@@@@@@@@@@@@

This is all the code we need on the front end, but if we try to run it like this it will break, because we still need to do some work to supply some of these fields from the back end for the front end to use. So let's go back to our ``models.py`` and add a few more methods to our condition.

.. code-block:: python

    def display_fields(self):
        """Gets condition fields in form dict format, for displaying in the condition component."""
        return [
            {"field_name": "minimum_duration", "field_value": self.duration_display(), "hidden": False},
            {"field_name": "time_remaining", "field_value": self.time_remaining_display(), "hidden": False},
            {"field_name": "responses", "field_value": self.get_responses(), "hidden": False},
            {"field_name": "response_options", "field_value": self.response_choices, "hidden": False},
            {"field_name": "can_be_resolved", "field_value": self.ready_to_resolve(), "hidden": False},
            {"field_name": "current_result", "field_value": self.current_result(), "hidden": False}
        ]

The field names all correspond to things etiher used directly in our component template or used in one of the component methods. Whatever field_name you define here is how you'll access it in the component. There's a few new helper methods here, ``duration_display`` and ``time_remaining_display``, in addition to the methods we've already defined (``get_responses``, ``ready_to_resoleve`` and ``current_result``).

.. code-block:: python

    def time_remaining_display(self):
        time_remaining = self.time_until_duration_passed()
        units = utils.parse_duration_into_units(time_remaining)
        return utils.display_duration_units(**units)

    def duration_display(self):
        units = utils.parse_duration_into_units(self.minimum_duration)
        return utils.display_duration_units(**units)

We've got two utility function, the first of which takes a duration of time in hours and turns it into a dictionary of weeks, days, hours and minutes, and the second of which displays that as a string.  This makes it easy for us to pass human-readable durations to the front end.

Two other methods we need to add are ``display_status`` and ``description_for_passing_condition``. Display status is used in our template, but ``description_for_passing_condition`` is additionally used when displaying conditions that have been set on permissions.

.. code-block:: python

    def display_status(self):
        """Gets 'plain English' display of status."""
        consensus_type = "strict" if self.is_strict else "loose"
        if self.resolved:
            return f"The discussion has ended with result {self.condition_status} under {consensus_type} consensus"
        return f"The discussion is ongoing with {self.time_remaining_display()}. If the discussion ended now, " + \
               f"the result would be: {self.current_result()}"

    def description_for_passing_condition(self, fill_dict=None):
        """Gets plain English description of what must be done to pass the condition."""
        return utils.description_for_passing_consensus_condition(self, fill_dict)

The descriptions for passing conditions are stored in the utils file, since they can get lengthy, although this one isn't too bad:

.. code-block:: python

    def description_for_passing_consensus_condition(condition, fill_dict=None):
        """Generate a 'plain English' description for passing the consensus condtion."""

        participate_actors = fill_dict.get("participate_actors", []) if fill_dict else None
        participate_roles = fill_dict.get("participate_roles", []) if fill_dict else None

        if not fill_dict or (not participate_roles and not participate_actors):
            consensus_type = "strict" if condition.is_strict else "loose"
            return f"a group of people must agree to it through {consensus_type} consensus"

        participate_str = roles_and_actors({"roles": participate_roles, "actors": participate_actors})

        if condition.is_strict:
            return f"{participate_str} must agree to it with everyone participating and no one blocking"
        else:
            return f"{participate_str} must agree to it with no one blocking"

There's one other place our condition shows up on the front end, besides the template we created and besides the display of existing conditions, and that's when a person is *creating* or *editing* a condition. We need to let the front end know what parts of the condition model are available to configure. To do that, we set a method called ``get_configuration_fields``, which are used to populate the condition creation/editing form:

.. code-block:: python

    @classmethod
    def configurable_fields(cls):
        """Gets fields on condition which may be configured by user."""
        return {
            "is_strict": {
                "display": "Use strict consensus mode? (Defaults to loose.)", "can_depend": False,
                **cls.get_form_dict_for_field(cls._meta.get_field("is_strict"))
            },
            "minimum_duration": {
                "display": "What is the minimum amount of time for discussion?", "can_depend": False,
                **cls.get_form_dict_for_field(cls._meta.get_field("minimum_duration"))
            },
            "participant_roles": {
                "display": "Roles who can participate in the discussion", "type": "RoleListField",
                "can_depend": True, "required": False, "value": None, "field_name": "participant_roles",
                "full_name": Changes().Conditionals.RespondConsensus
            },
            "participant_actors": {
                "display": "People who can participate in the discussion", "type": "ActorListField",
                "can_depend": True, "required": False, "value": None, "field_name": "participant_actors",
                "full_name": Changes().Conditionals.RespondConsensus
            },
            "resolver_roles": {
                "display": "Roles who can end discussion", "type": "RoleListField",
                "can_depend": True, "required": False, "value": None, "field_name": "resolver_roles",
                "full_name": Changes().Conditionals.ResolveConsensus
            },
            "resolver_actors": {
                "display": "People who can end discussion", "type": "ActorListField", "can_depend": True,
                "required": False, "value": None, "field_name": "resolver_actors",
                "full_name": Changes().Conditionals.ResolveConsensus
            }
        }

And that's it!

When it's all done, the condition should work like this:

.. image:: images/consensus_example.gif
