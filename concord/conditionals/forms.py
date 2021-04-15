import inspect

from concord.conditionals import utils


# functions for getting individual condition forms with or without data


def get_permission_from_data(permission_type, permission_data):
    if not permission_data:
        return None
    for permission in permission_data:
        if permission["permission_type"] == permission_type:
            return permission


def get_value_from_permission_data(field_type, permission):
    if not permission:
        return None
    roles, actors = permission.get("permission_roles", None), permission.get("permission_actors", None)
    if field_type in ["RoleField", "RoleListField"]:
        return roles
    if field_type in ["ActorField", "ActorListField"]:
        return actors


def update_permission_field_dict(field_name, field_dict, permission_data):
    permission = get_permission_from_data(field_dict["full_name"], permission_data)
    value = get_value_from_permission_data(field_dict["type"], permission)
    return {"can_depend": True, "field_name": field_name, "type": field_dict["type"],
            "required": field_dict.get("required", False), "full_name": field_dict["full_name"],
            "display": field_dict["display"], "value": value, "for_permission": True}


def form_dict_for_field(field):
    """Get dictionary with form data for supplied field."""
    return {
        'field_name': field.name,
        'type': field.__class__.__name__,
        'required': "required" if field.blank else "",
        'value': field.default
    }


def update_regular_field_dict(field_name, field_dict, condition):
    field = condition._meta.get_field(field_name)
    form_dict = form_dict_for_field(field)
    value = field.default if inspect.isclass(condition) else getattr(condition, field_name)
    form_dict.update({"value": value, "can_depend": False, "display": field_dict["display"]})
    return form_dict


def form_dict_for_fields_with_data(condition, permission_data=None):
    """Returns form_dict with condition data set as value."""

    fields_dict = condition.configurable_fields()
    combined_form_dict = {}

    for field_name, field_dict in fields_dict.items():

        if field_dict.get("for_permission", None):
            combined_form_dict[field_name] = update_permission_field_dict(field_name, field_dict, permission_data)
        else:
            combined_form_dict[field_name] = update_regular_field_dict(field_name, field_dict, condition)

    return combined_form_dict


# def form_dict_for_filter_condition(condition):
#     combined_form_dict = {}
#     for field_name, field in condition.get_concord_fields_with_names().items():
#         form_dict = field.to_form_field()
#         form_dict.update({"field_name": field_name, "can_depend": False, "display": field.label})
#         combined_form_dict.update({field_name: form_dict})
#     return combined_form_dict


# Condition Manager Forms


def get_for_acceptance_condition(condition_object, data):

    field_data = form_dict_for_fields_with_data(condition_object, data.permission_data)
    how_to_pass = condition_object.description_for_passing_condition(permission_data=data.permission_data)

    field_form = {"type": condition_object.__class__.__name__, "display_name": condition_object.descriptive_name,
                  "how_to_pass": how_to_pass, "fields": field_data, "element_id": data.element_id}

    return field_form, how_to_pass


def get_for_filter_condition(condition_object, data, permission):

    field_data = condition_object.get_form_fields_with_data()
    how_to_pass = condition_object.get_configured_name()

    field_form = {"type": data.condition_type, "display_name": condition_object.descriptive_name,
                  "fields": field_data, "how_to_pass": how_to_pass, "element_id": data.element_id}

    return field_form, how_to_pass


def condition_manager_form(manager, permission):

    form = {}
    how_to_pass_overall = []

    for data in manager.get_conditions_as_data():

        condition_object = data.get_unsaved_condition_object()

        if data.mode == "acceptance":
            field_form, how_to_pass = get_for_acceptance_condition(condition_object, data)
        else:
            field_form, how_to_pass = get_for_filter_condition(condition_object, data, permission)

        form.update({data.element_id: field_form})
        how_to_pass_overall.append(how_to_pass)

    form["how_to_pass_overall"] = ", and ".join(how_to_pass_overall)

    return form
