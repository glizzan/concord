def crawl_objects(crawl_tokens, base):
    """
    Examples passed in:
        actor.created_at
        action.change.permission_data.permission_actors
        target.commented_on.creator   // aka comment.post.creator
    """

    if len(crawl_tokens) == 0:
        return base

    from collections import deque
    crawl_tokens = deque(crawl_tokens)

    while len(crawl_tokens) > 0:
        token = crawl_tokens.popleft()
        base = getattr(base, token)  # FIXME: do differently if we want the field and not just value of field?

    return base


def transform_value(value, transformation):
    if not transformation:
        return value
    if transformation == "to_list":
        return [value]
    if transformation == "from_list":
        return value[0]
    if transformation == "to_pk":
        return value.pk
    if transformation == "to_pk_in_list":
        return [value.pk]
    return


def prep_value_for_parsing(value):
    if isinstance(value, str) and value[0:2] == "{{" and value[-2:] == "}}":
        return value.replace("{{", "").replace("}}", "").strip()


def get_transformation(value):
    """Takes in a value. If it has a transform in it, splits it to value and transform, otherwise returns value
    and None."""
    if "||" in value:
        command, transformation = value.split("||")
        return command, transformation
    return value, None


def check_nested(value):
    """Occasionally (eg when including a condition in a template) we need to protect the 'inner' replace field"""
    if value[0:7] == "nested:":
        return "{{" + value[7:] + "}}"


def get_supplied_field_value(tokens, context):
    """Always two tokens long, with format: supplied_fields.field_name."""
    return context["supplied_fields"][tokens[1]]


def get_context_field_value(tokens, context):
    """Gets the base from context and uses the crawl_objects function to get the specified field."""
    base = context["context"][tokens[1]]
    field = crawl_objects(tokens[2:], base)
    return field


def get_previous_field_value(tokens, context):
    """Always three or four tokens long, with format previous.position.action_or_result, for example:
    previous.0.action, or previous.position.action_or_result.attribute, for example previous.1.result.pk"""
    position = int(tokens[1])
    action_and_result_dict = context["actions_and_results"][position]
    source = action_and_result_dict["action"] if tokens[2] == "action" else action_and_result_dict["result"]
    return getattr(source, tokens[3]) if len(tokens) == 4 else source


def replacer(value, context):
    """Given the value provided by mock_action, looks for fields that need replacing by finding strings with the right
    format, those that begin and end with {{ }}. Uses information in context object to replace those fields. In
    the special case of finding something referencing nested_trigger_action (always(?) in the context of a
    condition being set) it replaces nested_trigger_action with trigger_action."""

    value = prep_value_for_parsing(value)

    if not value: return ...
    if check_nested(value): return check_nested(value)

    command, transformation = get_transformation(value)

    tokens = command.split(".")

    if tokens[0] == "supplied_fields":
        new_value = get_supplied_field_value(tokens, context)

    if tokens[0] == "context":
        new_value = get_context_field_value(tokens, context)

    if tokens[0] == "previous":
        new_value = get_previous_field_value(tokens, context)

    if transformation:
        return transform_value(new_value, transformation)

    return new_value


def replace_fields(*, action, mock_action, context):
    """Takes in the action to change and the mock_action, and looks for field on the mock_action which indicate
    that fields on the action need to be replaced.  For the change field, and the change field only,
    also look for fields to replace within."""

    for key, value in vars(mock_action).items():

        # For each attribute on mock action, check to see if they need replacing
        new_value = replacer(value, context)
        if new_value is not ...: action.replace_value(field_name=key, value=new_value)

        # Check the parameters of the change obj as well
        if key == "change":

            for change_field_name, change_field in value.get_concord_field_instances().items():

                change_field_value = getattr(value, change_field_name)
                new_value = replacer(change_field_value, context)

                if new_value is not ...:
                    action.replace_value(obj=action.change, field_name=change_field_name, value=new_value)

                if change_field_name == "condition_data":
                    for dict_key, dict_value in change_field_value.items():
                        new_value = replacer(dict_value, context)
                        if new_value is not ...: action.change.condition_data[dict_key] = new_value

                if change_field_name == "permission_data":
                    for index, permission_dict in enumerate(change_field_value):
                        for perm_key, perm_value in permission_dict.items():
                            new_value = replacer(perm_value, context)
                            if new_value is not ...:
                                action.change.permission_data[index][perm_key] = new_value

    action.fields_replaced = True  # indicates action has passed through replace_fields and is safe to use
    return action
