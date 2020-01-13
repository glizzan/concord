import json

from concord.permission_resources.client import PermissionResourceClient

"""
Data can be stored in a few different ways:

- as Concord objects with relationships to each other
- as JSON, using custom encoding methods on each object
- as CTN, using only the template-relevant elements of the Concord objects/JSON

CTN stands for Concord Template Notation, which stores information about Concord objects, relationships, 
permissions, etc.  All encode methods on Concord objects accept a Template boolean which, if true,
encodes only the template-relevant information.

Common things that ConcordCoder is used for:

- taking a list of objects and generating a template out of them 
- taking a template and making it human-readable with CTN
- taking a human-edited CTN and adjusting the corresponding template accordingly, or creating a new template
- given a template or CTN, generating a set of actions to create the new objects

We can't do this yet, but eventually, we'd like to be able to apply a template/CTN to an exisiting
set of objects, merging in new changes.
"""


class ConcordCoder(object):

    def encode(self, object_list, template=False):

        prc = PermissionResourceClient(actor="system")
        encoded_objects = []
        encoded_object_pks = []

        while len(object_list) > 0:

            if obj.pk in encoded_object_pks:
                continue    # Skip already encoded object

            encoded_objects.append(obj.encode(template))
            encoded_object_pks.append(obj.pk)

            # Get any permissions & add to objects to encode
            permissions = prc.get_permissions_on_object(obj)
            object_list += permissions

            # TODO: get conditions on permissions or other related objects?

        return json.dumps(encoded_objects)

    def decode(self, encoded_objects, template=False):

        object_list = json.loads(encoded_objects)

        for obj in object_list:

            new_obj = obj.decode(template)

    def generate_template(self, object_list):
        return self.encode(object_list, template=True)

    def generate_objects_from_template(self):
        ...

    def translate_to_english(self, object_list):
        ...

    def english_to_objects(self, object_list):
        ...





