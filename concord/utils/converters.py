import inspect, json
from django.contrib.contenttypes.models import ContentType
from concord.utils.lookups import get_concord_class


def recursively_serialize(field):
    """Tests if a field can be serialized. If this causes an error, crawls through structure and keeps attempting
    to serialize things."""

    try:  # maybe the field is already serializable
        json.dumps(field)
        return field
    except TypeError:
        pass

    try:  # maybe the field is directly serializable
        field = field.serialize()
        return field
    except AttributeError:
        pass

    if field.__class__.__name__  == "User":  # inbuilt user model needs special handling
        return {"class": field.__class__.__name__, "concord_dict": True, "pk": field.pk}

    # crawl through structures to find the unserializable thing

    if type(field) == list:
        new_field = []
        for item in field:
            new_item = recursively_serialize(item)
            new_field.append(new_item)
        return new_field

    if type(field) == dict:
        new_field = {}
        for key, value in field.items():
            new_value = recursively_serialize(value)
            new_field.update({key:new_value})
        return new_field


def get_class_name(cls, field_dict):

    class_name = field_dict.pop("class", None)
    if class_name:
        return class_name

    if cls and hasattr(cls, "__name__") and cls.__name__ != "ConcordConverterMixin":
        return cls.__name__

    raise ValueError(f"Need class information to deserialize.")


def recursively_deserialize(field):

    if type(field) == dict and "concord_dict" in field:

        if "pk" in field and field["pk"] is not None:  # this is an existing Django model - fetch it
            class_name = get_class_name(None, field)
            object_class = get_concord_class(class_name)
            return object_class.objects.get(pk=int(field["pk"]))
        else:                                          # create it from scratch
            return ConcordConverterMixin.deserialize(field)

    if type(field) == list:
        new_field = []
        for item in field:
            new_item = recursively_deserialize(item)
            new_field.append(new_item)
        return new_field

    if type(field) == dict:
        new_field = {}
        for key, value in field.items():
            new_value = recursively_deserialize(value)
            new_field.update({key:new_value})
        return new_field

    return field


class ConcordConverterMixin(object):
    """This object is designed to be mixed in with any Concord object that may have to convert between formats.
    This includes non-permissioned models like Action and objects that aren't directly associated with a DB table,
    like change objects."""
    is_convertible = True

    def _serialize_fields(self, serializable_fields):
        """Given a list of field names on the object, looks up their serializable values and returns them as a dict with
        field names as keys.  If a given field is itself a serializable object, calls serialize() on it."""

        object_dict = {"class": self.__class__.__name__, "concord_dict": True}

        for field_name in serializable_fields:
            field = recursively_serialize(getattr(self, field_name))
            object_dict.update({field_name: field})

        json.dumps(object_dict)  # will raise exception if this doesn't work - better to catch it here
        return object_dict

    def serialize(self, **kwargs):
        """Takes in an object and returns all data from it in json-seraliazable form. Used in conjunction with
        deserialize.

        Determines what fields to serialize by checking, in order: if a serializable_fields keyword arg is passed
        in; if "serializable_fields" attribute exists on the instance; checking if the instance is a Django model and
        getting the list of field names, and, finally, if it's a regular Python object, gets the non-self parametters
        in the __init__ signature."""

        serializable_fields = kwargs.get("serializable_fields", None)

        if not serializable_fields:
            serializable_fields = getattr(self, "serializable_fields", None)

        if not serializable_fields and hasattr(self, "DoesNotExist"):
            serializable_fields = [f.name for f in self._meta.fields]

        if not serializable_fields and not hasattr(self, "DoesNotExist"):
            params = dict(inspect.signature(self.__init__).parameters)
            params.pop("self", None)
            serializable_fields = [param_name for param_name, value in params.items()]

        if kwargs.pop("to_json", None):
            return json.dumps(self._serialize_fields(serializable_fields))

        return self._serialize_fields(serializable_fields)

    @classmethod
    def _deserialize_fields(cls, field_dict):

        if not isinstance(field_dict, dict): return field_dict

        class_name = get_class_name(cls, field_dict)

        field_dict.pop("concord_dict", None)
        new_dict = {}
        for field_name, field in field_dict.items():
            new_field = recursively_deserialize(field)
            new_dict.update({field_name: new_field})

        object_class = get_concord_class(class_name)
        return object_class(**new_dict)

    @classmethod
    def deserialize(cls, serialized_value=None, **kwargs):
        """Takes in a serialized dict and returns an instantiated Python object.  Used in conjunction with
        serialize.

        Determines what Python class to deserialize into based on, first, the class kwarg passed in via serialized
        dict. This should almost always be passed in, however if it's not we can try to see what class is calling it, and
        if it's a non-mixin class we assume this is the class we want to instantiate.  Otherwise we raise an exception.

        If a given field is itself a concord_dict, calls deserialize on it.

        # FIXME: does this create a new target in the DB every time we deserialize an action with the same target?
        # or create a new user?
        """

        # If kwargs accidentally passed in as a positional dict
        if type(serialized_value) == dict and "concord_dict" in serialized_value:
            kwargs = serialized_value

        # Or if it's accidentally passed in as Json...
        if serialized_value is not None:
            try:
                kwargs = json.loads(serialized_value)
            except TypeError:
                pass

        return cls._deserialize_fields(kwargs)

    def db_lookup_info(self, **kwargs):
        """Takes a Django model and returns the content type and pk, allowing us to look up the correct row
        in database. Used in conjunction with get_from_db."""
        if hasattr(self, "pk"):
            content_type = ContentType.objects.get_for_model(self.__class__)
            return {"pk": self.pk, "content_type_pk": content_type.pk}
        return {}

    def get_from_db(self, **kwargs):
        """Takes in a content type and pk, allowing us to look up the correct row in the db. Returns the model
        with data retrieved from that row."""
        pk = kwargs.pop("pk")
        content_type_pk = kwargs.pop("content_type_pk")
        model_type = ContentType.objects.get(pk=content_type_pk)
        return model_type.get_object_for_this_type(pk=pk)

    def to_form_field(self, **kwargs):
        """Given data about the object, generate form fields."""
        ...

    def from_form_field(self, **kwargs):
        """Given form fields, generate a dictionary of data."""
        ...

    @classmethod
    def get_concord_fields(cls):
        return cls.get_concord_fields_with_names().values()

    @classmethod
    def get_concord_fields_with_names(cls):
        return {field_name: field for field_name, field in cls.__dict__.items() if hasattr(field, "value")}

    def get_concord_field_instances(self):
        return {field_name: field for field_name, field in self.__dict__.items() if hasattr(field, "value")}

    def concord_fields(self):
        """If the object is a Django model, gets the map of Django model fields to Concord fields for the object.
        This system facilitates transferring model fields.

        eg on a Django model:

        @classmethod
        def concord_fields(cls):
            return {cls.commented_object: 'PermissionedModelField', cls.text: 'CharField', cls.created_at: 'DateTimeField'}
        """
        if hasattr(self, "DoesNotExist"):
            print(f"Warning! Django model {self} does not have a concord_fields method implemented.")

    def get_full_field(self, field_name):
        return self.__dict__[field_name]

    def replace_value(self, *, field_name, value, allow_falsy=True, obj=None):

        transformed_value = self.transform_value(field_name, value)
        if (transformed_value is not None and allow_falsy) or transformed_value:
            value = transformed_value

        obj = obj if obj else self
        setattr(obj, field_name, value)

    def transform_value(self, field_name, value):

        # if a dependent field, skip and just use replace_string
        from concord.utils.dependent_fields import prep_value_for_parsing
        if prep_value_for_parsing(value):
            return value

        # otherwise, transform!
        try:
            field = self.get_full_field(field_name)
        except KeyError:
            try:
                field = self._meta.get_field(field_name)
            except:
                return

        if hasattr(field, "transform_to_valid_value"):
            return field.transform_to_valid_value(value)
        return value

    def convert_field(self, field_to_convert, type_to_convert_to: str):
        method_to_call = "to_" + type_to_convert_to
        if hasattr(field_to_convert, method_to_call):
            return get_attr(field_to_convert, method_to_call)()

    def move_data_between_fields(self, from_field, to_field):
        if type(from_field) == type(to_field):
            to_field.value = from_field.value
        new_value = self.convert_field(from_field, to_field.__class__.__name__)
        if new_value:
            to_field.value = new_value
        return to_field


"""
Potential extensions:

- creating this in DB, updating them in DB

- validating?
"""

def deserialize_convertible(data):
    return ConcordConverterMixin.deserialize(data)

