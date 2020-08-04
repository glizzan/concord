import logging

from django.db import models, DatabaseError, transaction
from concord.actions.utils import MockAction, replace_fields
from django.contrib.contenttypes.models import ContentType

from concord.actions.serializers import (serialize_state_change, serialize_resolution, serialize_template,
    deserialize_state_change, deserialize_resolution, deserialize_template, serialize_template_context,
    deserialize_template_context)


logger = logging.getLogger(__name__)


#################################
### Resolution Object & Field ###
#################################


class Resolution:
    '''The Resolution object stores information about the Action's passage through the permissions
    pipeline.  It has an overall status, as well as status information for each of the three pipelines
    (foundational, governing and specific) along with log information, condition information, and details
    about how the action was approved (if it was approved).'''

    def __init__(self, *, foundational_status="not tested", specific_status="not tested", governing_status="not tested",
        conditions=None, log=None, approved_through=None, approved_role=None, approved_condition=None):
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
    
    def generate_status(self):
        """Generates an overall status given the three sub-statuses."""
        
        # Action only needs to be approved by one pipeline to be approved
        if "approved" in [self.foundational_status, self.governing_status, self.specific_status]:
            return "approved"
        
        # If any pipeline is waiting, status is waiting
        if "waiting" in [self.foundational_status, self.governing_status, self.specific_status]:
            return "waiting"

        # If any of the pipeline is rejected, status is rejected
        if "rejected" in [self.foundational_status, self.governing_status, self.specific_status]:
            return "rejected"
        
        return "created"  # We haven't actually run the permissions pipeline yet 

    @property
    def is_resolved(self):
        return True if self.generate_status() in ["approved", "rejected", "implemented"] else False
        
    @property
    def is_approved(self):
        return True if self.generate_status() in ["approved", "implemented"] else False

    @property
    def passed_as(self):
        if self.is_approved:
            return "role" if self.role else "individual"
        return None
    
    def __str__(self):
        return f"Action status {self.generate_status()} - {self.get_status_string()}"
        
    def __repr__(self):
        return f"Action Resolution(foundational_status={self.foundational_status}, specific_status={self.specific_status}, " + \
            f"governing_status={self.governing_status}, conditions={self.conditions}, log={self.log}, " + \
            f"approved_through={self.approved_through}, approved_role={self.approved_role}, " + \
            f"approved_condition={self.approved_condition})"

    def get_status_string(self):
        """Helper method to get human-readable string displaying action status"""
        if self.is_approved:
            return f"approved through {self.approved_through} with role {self.approved_role} and condition {self.approved_condition}"
        if self.generate_status() == "waiting":
            if self.foundational_status == "waiting":
                return f"waiting on condition set on foundational permission"
            pipeline_strings = []
            pipeline_strings.append("governing") if self.governing_status else None
            pipeline_strings.append("specific") if self.specific_status else None
            return f"waiting on condition(s) for { ', '.join(pipeline_strings) }"
        if self.generate_status()  == "created":
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
        container.save()
        status = container.commit_actions()
        return container, status

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
    { unique_id: { source_id: { pk & ct or None }}} 
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

    def refresh_from_db(self):
        for item in self.actions_and_results:
            item["result_pk"], item["result_ct"] = None, None

    def create_actions_in_db(self, container_pk, template_data):
        """Creates actions in the DB, if they haven't been already.  Typically called by ActionContainer's
        initialize method."""
        from concord.actions.models import Action

        action_pks = []
        for item in self.actions_and_results:
            if item["db_action_pk"] is None:
                mock_action = template_data.get_mock_action_given_unique_id(item["unique_id"])
                actor = self.trigger_action.actor
                target = mock_action.target if mock_action.target and hasattr(mock_action.target, "pk") else None
                action = Action.objects.create(actor=actor, change=mock_action.change, container=container_pk, 
                                               target=target, is_draft=True)
                item["db_action_pk"] = action.pk
                action_pks.append(action.pk)

        logging.debug(f"Actions created in container {container_pk}: {action_pks}")

    # db retrieval methods

    def get_action_model_given_pk(self, pk):
        if not pk:
            return None
        from concord.actions.models import Action
        return Action.objects.get(pk=pk)

    def get_generic_object(self, pk, ct):
        if not pk or not ct:
            return None
        content_type = ContentType.objects.get_for_id(ct)
        model_class = content_type.model_class()
        return model_class.objects.get(id=pk)

    def get_action_and_result_models(self, data_dict):
        action = self.get_action_model_given_pk(data_dict["db_action_pk"])
        result = self.get_generic_object(data_dict["result_pk"], data_dict["result_ct"])
        return action, result

    @property
    def trigger_action(self):
        """Gets trigger action from DB."""
        if self.trigger_action_pk:
            return self.get_action_model_given_pk(self.trigger_action_pk)

    # Action and result methods

    def get_item_dict_given_unique_id(self, unique_id):
        for item in self.actions_and_results:
            if str(item["unique_id"]) == str(unique_id):
                return item

    def get_action_model_given_unique_id(self, unique_id):
        item_dict = self.get_item_dict_given_unique_id(unique_id)
        action = self.get_action_model_given_pk(item_dict["db_action_pk"])
        action.unique_id = unique_id
        return action

    def get_result_model_given_unique_id(self, unique_id):
        item_dict = self.get_item_dict_given_unique_id(unique_id)
        return self.get_generic_object(item_dict["result_pk"], item_dict["result_ct"])

    def get_actions(self):
        """Gets action models for all actions associated with containers. May return Nones if called before
        initialize()."""
        return [self.get_action_model_given_pk(item["db_action_pk"]) for item in self.actions_and_results]

    def get_action_and_result_for_position(self, position):
        action_dict = self.actions_and_results[position]
        return self.get_action_and_result_models(action_dict)

    def get_result(self, position=None, unique_id=None, db_action_pk=None):
        """Attempts to get the instantiated result object given a position in the list, the item's unique ID,
        or the pk of the action."""

        if position or position == 0:
            action_dict = self.actions_and_results[position]
            return self.get_generic_object(action_dict["result_pk"],action_dict["result_ct"])

        if db_action_pk:
            # get uniqe_id given db_action_pk
            for item in self.actions_and_results:
                if item["db_action_pk"] == db_action_pk:
                    unique_id = item["unique_id"]

        if unique_id:
            return self.get_result_model_given_unique_id(unique_id)

        logging.warn("Failed attempt to get result - position, db_action_pk, or unique_id must be supplied")
        
    def add_result(self, unique_id, result):
        """Adds a result to the actions and results list."""
        ct_pk = ContentType.objects.get_for_model(result).pk

        # add to actions_and_results
        for item in self.actions_and_results:
            if str(item["unique_id"]) == str(unique_id):
                item["result_pk"] = result.pk
                item["result_ct"] = ct_pk 

    # Condition methods

    def add_condition_data(self, unique_id, source_id):
        unique_id = str(unique_id)
        if unique_id not in self.condition_data:
            self.condition_data[unique_id] = {}
        if source_id not in self.condition_data[unique_id]:
            self.condition_data[unique_id][source_id] = {"ct": None, "pk": None}

    def get_condition_given_dict(self, condition_dict):
        if condition_dict["pk"] and condition_dict["ct"]:
            return self.get_generic_object(condition_dict["pk"], condition_dict["ct"])
        return None

    def get_condition(self, unique_id, source_id):
        return self.get_condition_given_dict(self.condition_data[str(unique_id)][source_id])

    def get_conditions(self):
        """Get all condition models associated with container"""
        conditions = []
        for unique_id, data in self.condition_data.items():
            for source_id, condition_dict in data.items():
                condition = self.get_condition(unique_id, source_id)
                conditions.append(condition)
        return conditions

    def get_conditions_for_action(self, unique_id):
        """Get all condition models on a given action in the container."""
        conditions = []
        if unique_id in self.condition_data.items():
            for source_id, condition_dict in self.condition_data[unique_id].items():
                conditions.append(self.get_generic_object(condition_dict))
        return conditions

    def get_condition_dicts_for_action(self, unique_id):
        """Gets condition dict (pk and content type pk (aka 'ct')) associated with action."""
        unique_id = str(unique_id)
        conditions = []
        if unique_id in self.condition_data:
            for source_id, condition_dict in self.condition_data[unique_id].items():
                conditions.append(condition_dict)
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
                if not condition_data["pk"] and not condition_data["ct"]:
                    # Create condition
                    action = self.get_action_model_given_unique_id(unique_id)
                    condition, container = client.trigger_condition_creation_from_source_id(action=action, 
                        source_id=source_id)
                    if condition:
                        ct = ContentType.objects.get_for_model(condition)
                        self.condition_data[unique_id][source_id] = { "pk": condition.pk, "ct": ct.pk }
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
