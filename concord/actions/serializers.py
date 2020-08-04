import json
from django.utils.module_loading import import_string
from django.contrib.contenttypes.models import ContentType


# decorater to use in deserializers, to handle when json hasn't been loaded yet
def load_json_as_needed(func):
    def inner(data):
        if type(data) != dict:
            data = json.loads(data)
        return func(data)
    return inner



### State changes ###


def serialize_state_change(state_change_object, dump_to_json=True):
    obj_dict = {
        "change_type": state_change_object.get_change_type(),
        "change_data": state_change_object.get_change_data()
    }
    return json.dumps(obj_dict) if dump_to_json else obj_dict


@load_json_as_needed
def deserialize_state_change(state_change_dict):
    """
    Finds change object using change_type and instantiates with change_data.
    """
    change_type = state_change_dict["change_type"]
    change_data = state_change_dict["change_data"]
    changeClass = import_string(change_type)
    if type(change_data) != dict:
        change_data = json.loads(change_data)
    return changeClass(**change_data)


### Resolutions ###


def serialize_resolution(resolution, dump_to_json=True):
    obj_dict = {
        "foundational_status": resolution.foundational_status,
        "specific_status": resolution.specific_status,
        "governing_status": resolution.governing_status,
        "conditions": resolution.conditions,
        "log": resolution.log,
        "approved_through": resolution.approved_through,
        "approved_role": resolution.approved_role,
        "approved_condition": resolution.approved_condition
    }
    return json.dumps(obj_dict) if dump_to_json else obj_dict


@load_json_as_needed
def deserialize_resolution(resolution_data):
    from concord.actions.customfields import Resolution
    return Resolution(foundational_status=resolution_data["foundational_status"], specific_status=resolution_data["specific_status"], 
        governing_status=resolution_data["governing_status"], conditions=resolution_data["conditions"],
        log=resolution_data["log"], approved_through=resolution_data["approved_through"], 
        approved_role=resolution_data["approved_role"], approved_condition=resolution_data["approved_condition"])


### Mock Actions ###


def serialize_mock_action_target(mock_action_target):
    """For now, targets are the only replaceable mock action fields, so we'll just have a helper method
    to handle them."""
    if mock_action_target:
        if hasattr(mock_action_target, "pk"):
            return { "pk": mock_action_target.pk, 
                "content_type_pk": ContentType.objects.get_for_model(mock_action_target).id}
        return mock_action_target
    return None


def deserialize_mock_action_target(mock_action_target_data):
    if mock_action_target_data is not None:
        if "pk" in mock_action_target_data:
            ct = ContentType.objects.get(pk=mock_action_target_data["content_type_pk"])
            return ct.get_object_for_this_type(pk=mock_action_target_data["pk"])
    return mock_action_target_data


def serialize_mock_action(mock_action, dump_to_json=True):
    obj_dict = {
        "change": serialize_state_change(mock_action.change, dump_to_json=False),
        "target": serialize_mock_action_target(mock_action.target),
        "actor": mock_action.actor.pk,
        "resolution": serialize_resolution(mock_action.resolution, dump_to_json=False),
        "unique_id": mock_action.unique_id
    }
    return json.dumps(obj_dict) if dump_to_json else obj_dict


@load_json_as_needed
def deserialize_mock_action(mock_action_data):
    from concord.actions.utils import MockAction
    from django.contrib.auth.models import User
    change = deserialize_state_change(mock_action_data["change"])
    actor = User.objects.get(pk=mock_action_data["actor"])
    target = deserialize_mock_action_target(mock_action_data["target"])
    resolution = deserialize_resolution(mock_action_data["resolution"])
    mock_action = MockAction(change, actor, target, resolution)
    mock_action.unique_id = mock_action_data["unique_id"]
    return mock_action


### Templates ###


def serialize_template(template, dump_to_json=True):
    actions = []
    for action in template.action_list:
        actions.append(serialize_mock_action(action, dump_to_json=False))
    obj_dict = {"actions": actions, "system": template.system, "description": template.description }
    return json.dumps(obj_dict) if dump_to_json else obj_dict


@load_json_as_needed
def deserialize_template(template_data):
    action_list = []
    for action in template_data["actions"]:
        action_list.append(deserialize_mock_action(action))
    from concord.actions.customfields import Template
    return Template(action_list=action_list, system=template_data["system"], 
        description=template_data["description"])


def serialize_template_context(template_context, dump_to_json=True):
    obj_dict = {
        "trigger_action_pk": template_context.trigger_action_pk,
        "supplied_fields": template_context.supplied_fields,
        "actions_and_results": template_context.actions_and_results,
        "condition_data": template_context.condition_data
    }
    return json.dumps(obj_dict) if dump_to_json else obj_dict


@load_json_as_needed
def deserialize_template_context(template_context_data):
    from concord.actions.customfields import TemplateContext
    return TemplateContext(trigger_action_pk=template_context_data["trigger_action_pk"],
        supplied_fields=template_context_data["supplied_fields"], 
        actions_and_results=template_context_data["actions_and_results"],
        condition_data=template_context_data["condition_data"])

    