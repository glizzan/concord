from django.db import models, DatabaseError, transaction
from concord.actions.utils import MockAction, replace_fields
from django.contrib.contenttypes.models import ContentType

from concord.actions.serializers import (serialize_state_change, serialize_resolution, serialize_template,
    deserialize_state_change, deserialize_resolution, deserialize_template, serialize_template_context,
    deserialize_template_context)


#################################
### Resolution Object & Field ###
#################################


class Resolution:
    '''The Resolution object stores information about the Action's passage through the permissions
    pipeline.  It has an overall status, as well as status information for each of the three pipelines
    (foundational, governing and specific) along with log information, condition information, and details
    about how the action was approved (if it was approved).
    
    external status: can be draft, implemented, withdrawn or sent - only "sent" can go through permissions pipeline
        (NOTE: currently also accepts rejected, but will change when we move validation out of action)
    
    '''

    def __init__(self, *, foundational_status="not tested", specific_status="not tested", governing_status="not tested",
        conditions=None, log=None, approved_through=None, approved_role=None, approved_condition=None, 
        external_status="draft"):  
        self.external_status = external_status
        self.foundational_status = foundational_status
        self.specific_status = specific_status
        self.governing_status = governing_status
        self.conditions = conditions if conditions else []
        self.log = log if log else ""
        self.approved_through = approved_through
        self.approved_role = approved_role
        self.approved_condition = approved_condition

        # FIXME: the log could grow very long if we keep checking the same waiting conditions over and 
        # over and storing them in the log, probably need to move most of the logging behavior to the actual
        # logging system, but I want some of it accessible to the front end dev who gets the action.
    
    @property
    def status(self):

        # If the resolution is implemented or draft, we can skip the rest of the logic
        if self.external_status in ["implemented", "draft", "withdrawn", "rejected"]:
            return self.external_status
        
        # Action only needs to be approved by one pipeline to be approved
        if "approved" in [self.foundational_status, self.governing_status, self.specific_status]:
            return "approved"
        
        # If any pipeline is waiting, status is waiting
        if "waiting" in [self.foundational_status, self.governing_status, self.specific_status]:
            return "waiting"

        # If any of the pipeline is rejected, status is rejected
        if "rejected" in [self.foundational_status, self.governing_status, self.specific_status]:
            return "rejected"
        
        return "sent"  # We haven't actually run the permissions pipeline yet, so return 'sent' 

    @property
    def is_resolved(self):
        return True if self.status in ["approved", "rejected", "implemented"] else False
        
    @property
    def is_approved(self):
        return True if self.status in ["approved", "implemented"] else False

    @property
    def passed_as(self):
        if self.is_approved:
            return "role" if self.role else "individual"
        return None
    
    def __str__(self):
        return f"Action status {self.status} - {self.get_status_string()}"
        
    def __repr__(self):
        return f"Action Resolution(foundational_status={self.foundational_status}, specific_status={self.specific_status}, " + \
            f"governing_status={self.governing_status}, conditions={self.conditions}, log={self.log}, " + \
            f"approved_through={self.approved_through}, approved_role={self.approved_role}, " + \
            f"approved_condition={self.approved_condition}, external_status={self.external_status})"

    def get_status_string(self):
        """Helper method to get human-readable string displaying action status"""
        if self.is_approved:
            return f"approved through {self.approved_through} with role {self.approved_role} and condition {self.approved_condition}"
        if self.status == "waiting":
            if self.foundational_status == "waiting":
                return f"waiting on condition set on foundational permission"
            pipeline_strings = []
            pipeline_strings.append("governing") if self.governing_status else None
            pipeline_strings.append("specific") if self.specific_status else None
            return f"waiting on condition(s) for { ', '.join(pipeline_strings) }"
        if self.status == "sent":
            return "action has not been put through pipeline yet"
        if self.foundational_status == "rejected":
            return "actor does not have foundational authority"
        else:
           return "action did not meet any permission criteria"

    def approve_action(self, pipeline, approved_role=None, approved_condition=None):
        """Sets the status for the calling pipeline to approved, which will set overall status to approved."""
        setattr(self, pipeline + "_status", "approved")
        self.approved_through = pipeline
        self.approved_role = approved_role
        self.approved_condition = approved_condition
        log_string = f"action approved through {self.approved_through} with role {approved_role} and condition {approved_condition}"
        self.add_to_log(log_string)

    def reject_action(self, pipeline, log=None):
        setattr(self, pipeline + "_status", "rejected")
        if log:
            self.add_to_log(log)

    def set_waiting(self, pipeline, log=None):
        setattr(self, pipeline + "_status", "waiting")
        if log:
            self.add_to_log(log)

    def add_to_log(self, message):
        if not self.log:
            self.log = message
        else:
            self.log += "  " + message


class ResolutionField(models.Field):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        return name, path, args, kwargs

    def db_type(self, connection):
        return 'varchar'

    def from_db_value(self, value, expression, connection):
        if value is None:
            return Resolution()
        return deserialize_resolution(value)

    def to_python(self, value):
        if isinstance(value, Resolution):
            return value
        if value is None:
            return Resolution()
        return deserialize_resolution(value)

    def get_prep_value(self, value):
        if value is None:
            value = Resolution()
        return serialize_resolution(value)


#############################
### Change Object & Field ###
#############################


class StateChangeField(models.Field):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        return name, path, args, kwargs

    def db_type(self, connection):
        return 'varchar'

    def from_db_value(self, value, expression, connection):
        return deserialize_state_change(value)

    def to_python(self, value):

        from action.state_changes import BaseStateChange
        if issubclass(change_class, BaseStateChange):   # BUG: where is change_class coming from????
            return value
        return deserialize_state_change(value)

    def get_prep_value(self, value):

        # If actually given a state change, prep:
        from concord.actions.state_changes import BaseStateChange
        if issubclass(value.__class__, BaseStateChange):
            return serialize_state_change(value)

        # If already prepped for some reason, return as is:
        if type(value) == dict and "change_type" in value.keys() and "change_data" in value.keys():
            return value


###############################
### Template Object & Field ###
###############################


class Template(object):
    """Python object associated with the TemplateField CustomField. Contains action data which can be used
    to create an ActionContainer which will generate a set of related, configured objects."""

    def __init__(self, action_list=None, configurable_fields=None, description=None, system=False):
        self.system = system
        self.action_list = action_list if action_list else []
        self.description = description if description else ""

    def __repr__(self):
        action_changes = ", ".join([str(action) for action in self.action_list])
        return f"Template(action_list={action_changes}, system={self.system})"

    def __str__(self):
        return self.__repr__()

    def has_template(self):
        return True if len(self.action_list) > 0 else False

    def apply_template(self, trigger_action=None, supplied_fields=None):
        from concord.actions.models import ActionContainer
        container = ActionContainer.objects.create()
        container.initialize(template_object=self, trigger_action=trigger_action, supplied_fields=supplied_fields)
        summary_status, log = container.commit_actions()
        return container, log

    def get_mock_action_given_unique_id(self, unique_id):  
        for mock_action in self.action_list:
            if mock_action.unique_id == unique_id:
                return mock_action

    # Simple edit methods

    def add_action(self, action, position=None):
        if position:
            if position > len(self.action_list) - 1:
                raise IndexError(f"Position {position} given when action list is length { len(self.action_list) }")
            self.action_list.insert(action, position)
        else:
            self.action_list.append(action)

    def delete_action(self, action=None, position=None, last=False):
        if position:
            if position > len(self.action_list) - 1:
                raise IndexError(f"Position {position} given when action list is length { len(self.action_list) }")
            self.action_list.pop(position)
        elif last:
            self.action_list.pop(len(self.action_list) - 1)
        elif action:
            self.action_list.remove(action)
        if not action and not position and not last:
            raise ValueError("Must provide action or position or last = True to delete_action.")


class TemplateField(models.Field):

    def __init__(self, system=False, *args, **kwargs):
        self.system = system
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        # only include kwargs if it's not the default
        if self.system:
            kwargs['system'] = self.system
        return name, path, args, kwargs

    def db_type(self, connection):
        return 'varchar'

    def from_db_value(self, value, expression, connection):

        if value is None:
            return Template(system=self.system)  

        return deserialize_template(value)

    def to_python(self, value):

        if value is None:
            return Template(system=self.system)

        if issubclass(value.__class__, Template):
            return value

        if type(value) == list and all([item.__class__ == MockAction for item in value]):
            return Template(action_list=value, system=self.system)

        return deserialize_template(value)

    def get_prep_value(self, value):

        if issubclass(value.__class__, Template):
            if self.system and not value.system:
                # This is a system field (likely a condition) that for some reason got initialized without this setting
                value.system = True
            return serialize_template(value)

        if type(value) == list and all([item.__class__ == MockAction for item in value]):
            return serialize_template(Template(action_list=value, system=self.system))

        # If already prepped for some reason, return as is???



#######################################
### Template Context Object & Field ###
#######################################


class TemplateContext(object):
    """Python object associated with the context supplied to a Template Object/Field.

    supplied_fields is a straightforward dict of literals, with keys as field names and values supplied
    by the user

    trigger_action is the action which triggered the application of the template context.  

    actions_and_results_data is a list of dicts which includes the unique_id of the mock_action in the template, and 
    if they exist, the pk of the associated action and the pk & ct of the result associated with the action.

    condition_data tracks conditions associated with the action container, and has structure like:
    { unique_action_id: { source_id: { pk & ct or None }}} 
    """

    def __repr__(self):
        return f"TemplateContext(trigger_action_pk={self.trigger_action_pk}, actions_and_results={self.actions_and_results}, " + \
            f"supplied_fields={self.supplied_fields}, condition_data={self.condition_data})"

    def __init__(self, trigger_action_pk=None, supplied_fields=None, actions_and_results=None,
        condition_data=None):
        """Typically called when deserializing."""
        self.supplied_fields = supplied_fields if supplied_fields else {}
        self.trigger_action_pk = trigger_action_pk
        self.actions_and_results = actions_and_results if actions_and_results else []
        self.condition_data = condition_data if condition_data else {}
        self.cache = { "actions": {}, "generic_objects": {} }

    def initialize(self, template_object, trigger_action, supplied_fields):
        """Initialize fields given a template object and trigger action, called exactly once by ActionContainer."""
        
        if not template_object:
            raise ValueError("Template object must be supplied when initializing context")
        for action in template_object.action_list:
            self.actions_and_results.append({ "unique_id": action.unique_id, "db_action_pk": None, 
                "result_pk": None, "result_ct": None })

        self.supplied_fields = supplied_fields
        
        if trigger_action:
            self.trigger_action_pk = trigger_action.pk
            self.add_to_cache("action", trigger_action, trigger_action.pk)

    # Cache methods

    def get_action_from_cache_or_db(self, pk):
        """Gets action from cache or DB, returning True if cached and False if from DB"""
        if pk not in self.cache["actions"]:
            from concord.actions.models import Action
            self.cache["actions"][pk] = Action.objects.get(pk=pk)
        return self.cache["actions"][pk]

    def get_generic_obj_from_cache_or_db(self, pk, ct):
        """Gets a generic objet from the cache or DB, returning True if cached and False if from DB"""
        if ct not in self.cache["generic_objects"]:
            self.cache["generic_objects"][ct] = {}
        if pk not in self.cache["generic_objects"][ct]:
            content_type = ContentType.objects.get_for_id(ct)
            model_class = content_type.model_class()
            instance = model_class.objects.get(id=pk)
            self.cache["generic_objects"][ct][pk] = instance
        return self.cache["generic_objects"][ct][pk]

    def add_to_cache(self, action_or_generic, object_to_add, pk, ct=None):
        """Adds a given object to action or generic object cache.  Overrides existing object."""
        if action_or_generic == "action":
            self.cache["actions"][pk] = object_to_add
        if action_or_generic == "generic":
            if ct not in self.cache["generic_objects"]:
                self.cache["generic_objects"][ct] = {}
            self.cache["generic_objects"][ct][pk] = object_to_add

    # Action and result methods

    @property
    def trigger_action(self):
        """Gets trigger action from cache or, if not in cache, from DB."""
        if self.trigger_action_pk:
            action = self.get_action_from_cache_or_db(self.trigger_action_pk)
            return action

    def construct_action(self, container_pk, template_data, unique_id):
        from concord.actions.models import Action
        mock_action = template_data.get_mock_action_given_unique_id(unique_id)
        actor = self.trigger_action.actor
        return Action(
            actor = actor,
            change = mock_action.change,
            container = container_pk,
            target = mock_action.target if mock_action.target and hasattr(mock_action.target, "pk") else None
        )

    def create_actions_in_db(self, container_pk, template_data):
        """Creates actions in the DB, if they haven't been already.  Typically called by ActionContainer's
        initialize method."""
        actions_created = False
        for item in self.actions_and_results:
            if item["db_action_pk"] is None:
                action = self.construct_action(container_pk, template_data, item["unique_id"])
                action.save()
                item["db_action_pk"] = action.pk
                self.add_to_cache("action", action, action.pk)
                actions_created = True
        return actions_created
    
    def get_db_action_pk_given_unique_id(self, unique_id):
        for item in self.actions_and_results:
            if item["unique_id"] == unique_id:
                return item["db_action_pk"]

    def get_action_model_given_unique_id(self, unique_id):
        action_pk = self.get_db_action_pk_given_unique_id(unique_id)
        action = self.get_action_from_cache_or_db(action_pk)
        action.unique_id = unique_id
        return action

    def add_result(self, unique_id, result):
        """Adds a result to the actions and results list."""
        ct_pk = ContentType.objects.get_for_model(result).pk

        # add to actions_and_results
        for item in self.actions_and_results:
            if item["unique_id"] == unique_id:
                item["result_pk"] = result.pk
                item["result_ct"] = ct_pk 

        self.add_to_cache("generic", result, result.pk, ct_pk)

    def get_action_and_result_for_position(self, position):
        action_dict = self.actions_and_results[position]
        action = self.get_action_from_cache_or_db(action_dict["db_action_pk"])
        if action_dict["result_pk"] and action_dict["result_ct"]:
            result = self.get_generic_obj_from_cache_or_db(action_dict["result_pk"], action_dict["result_ct"])
        else:
            result = None
        return action, result

    def get_result(self, position=None, unique_id=None, db_action_pk=None):
        """Attempts to get the instantiated result object given a position in the list, the item's unique ID,
        or the pk of the action."""

        action_dict = None
        
        if position is not None:
            action_dict = self.actions_and_results[position]
        else:
            for item in self.actions_and_results:
                if unique_id and item["unique_id"] == unique_id:
                    action_dict = item
                    continue
                if db_action_pk and item["db_action_pk"] == db_action_pk:
                    action_dict = item
                    continue   
                    
        if action_dict:
            result = self.get_generic_obj_from_cache_or_db(action_dict["result_pk"], action_dict["result_ct"])
            return result

    # Condition methods

    def get_condition(self, unique_action_id, source_id):
        """Instantiates condition item if unique_action_id and source_id have associated pk & ct.  Returns
        None if no pk & ct associated. Creates """
        if unique_action_id not in self.condition_data:
            self.condition_data[unique_action_id] = { source_id : None }  # creates for later
        else:
            condition_dict = self.condition_data[unique_action_id][source_id]
            if condition_dict:
                condition = self.get_generic_obj_from_cache_or_db(condition_dict["pk"], condition_dict["ct"])
                return condition

    def get_conditions(self):
        """Gets the condition models for all conditions associated with container."""
        conditions = []
        for unique_id, data in self.condition_data.items():
            for source_id, condition_dict in data.items():
                condition = self.get_generic_obj_from_cache_or_db(condition_dict["pk"], condition_dict["ct"])
                conditions.append(condition)
        return conditions

    def generate_conditions(self):
        """When called, looks through existing conditions and, if none are associated with a pk & ct of an
        existing condition item, creates them.
        
        Returns True if one or more conditions were created, False if no new conditions were created."""
        from concord.conditionals.client import ConditionalClient
        client = ConditionalClient(system=True)

        generated = False
        for unique_id, action_data in self.condition_data.items():
            for source_id, condition_data in action_data.items():
                if condition_data is None:
                    action = self.get_action_model_given_unique_id(unique_id)
                    condition, container = client.trigger_condition_creation_from_source_id(action=action, 
                        source_id=source_id)
                    if condition:
                        ct = ContentType.objects.get_for_model(condition)
                        self.condition_data[unique_id][source_id] = { "pk": condition.pk, "ct": ct.pk }
                        self.add_to_cache("generic", condition, condition.pk, ct.pk)
                        generated = True
        return generated


class TemplateContextField(models.Field):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        return name, path, args, kwargs

    def db_type(self, connection):
        return 'varchar'

    def from_db_value(self, value, expression, connection):

        if value is None:
            return TemplateContext()

        return deserialize_template_context(value)

    def to_python(self, value):

        if value is None:
            return TemplateContext()

        if issubclass(value.__class__, TemplateContext):
            return value

        return deserialize_template_context(value)

    def get_prep_value(self, value):

        if issubclass(value.__class__, TemplateContext):
            return serialize_template_context(value)
