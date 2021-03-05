"""Profile factory optimizes the previous profile format

In particular, in the new format we propose to merge some regions into
so called resource types, which are dictionaries of persistent less
frequently changed aspects of resources. Moreover, we optimize other
regions and flatten the format.
"""

import collections
import operator
import itertools
import click

import perun.profile.convert as convert
import perun.profile.query as query
import perun.logic.config as config

from perun.check.general_detection import get_filtered_best_models_of
from perun.postprocess.regression_analysis.regression_models import get_supported_models
from perun.postprocess.regressogram.methods import get_supported_nparam_methods

__author__ = 'Tomas Fiedor'


class Profile(collections.MutableMapping):
    """
    :ivar dict _storage: internal storage of the profile
    :ivar dict _tuple_to_resource_type_map: map of tuple of persistent records of resources to
        unique identifier of those resources
    :ivar Counter _uid_counter: counter of how many resources type uid has
    """
    collectable = {
        'amount', 'structure-unit-size', 'call-order', 'order', 'address', 'timestamp', 'exclusive'
    }
    persistent = {'trace', 'type', 'subtype', 'uid'}

    independent = [
        'structure-unit-size', 'snapshot', 'order', 'call-order', 'address', 'timestamp',
        'exclusive'
    ]
    dependent = ['amount']

    def __init__(self, *args, **kwargs):
        """Initializes the internal storage

        :param list args: positional arguments for dictionary
        :param kwargs kwargs: keyword arguments for dictionary
        """
        super().__init__()
        initialization_data = dict(*args, **kwargs)
        global_data = initialization_data.get('global', {'models': []})
        self._storage = {
            'resources': {},
            'resource_type_map': {},
            'models': global_data.get('models', []) if isinstance(global_data, dict) else []
        }
        self._tuple_to_resource_type_map = {}
        self._resource_type_to_flattened_resources_map = {}
        self._uid_counter = collections.Counter()

        for key, value in initialization_data.items():
            if key in ('resources', 'snapshots', 'global'):
                self.update_resources(value, key)
            else:
                self._storage[key] = value
        config.runtime().append('context.profiles', self)

    def update_resources(self, resource_list, resource_type='list', clear_existing_resources=False):
        """Given by @p resource_type updates the storage with new flattened resources

        This calls appropriate functions to translate older formats of resources to the
        new more efficient representation.

        :param list resource_list: either list or dict
        :param str resource_type: type of the resources in the resources list,
            can either be snapshots (then it is list of different snapshots), global
            then it is old type of profile) or it can be resource l
        :param bool clear_existing_resources: if set to true then the actual storage will be cleared
            before updating the resources
        :return:
        """
        if clear_existing_resources:
            self._storage['resources'].clear()
        if resource_type == 'global' and isinstance(resource_list, dict) and resource_list:
            # Resources are in type of {'time': _, 'resources': []}
            self._translate_resources(
                resource_list['resources'], {'time': resource_list.get('time', '0.0')}
            )
        elif resource_type == 'snapshots':
            # Resources are in type of [{'time': _, 'resources': []}
            for i, snapshot in enumerate(resource_list):
                self._translate_resources(
                    snapshot['resources'], {'snapshot': i, 'time': snapshot.get('time', '0.0')}
                )
        elif isinstance(resource_list, (dict, Profile)):
            self._storage['resources'].update(resource_list)
        else:
            self._translate_resources(resource_list, {})

    def _translate_resources(self, resource_list, additional_params):
        """Translate the list of resources to efficient format
        Given a list of resources, this is all flattened into a new format: a dictionary that
        maps unique resource identifiers (set of persistent properties) to list of collectable
        properties (such as amounts, addresses, etc.)

        :param resource_list:
        :param additional_params:
        :return:
        """
        ctx = config.runtime().safe_get('context.workload', {})
        ctx_persistent_properties = [
            (key, value) for (key, value) in ctx.items() if isinstance(value, str)
        ]
        ctx_collectable_properties = [
            (key, value) for (key, value) in ctx.items() if not isinstance(value, str)
        ]

        # Update collectable and persistent keys (needed for merge)
        Profile.persistent.update({key for key, val in ctx.items() if isinstance(val, str)})
        Profile.collectable.update({key for key, val in ctx.items() if not isinstance(val, str)})

        for resource in resource_list:
            persistent_properties = [
                (key, value) for (key, value) in resource.items() if key not in Profile.collectable
            ] + ctx_persistent_properties
            persistent_properties.extend(list(additional_params.items()))
            persistent_properties.sort(key=operator.itemgetter(0))
            collectable_properties = [
                (key, value) for (key, value) in resource.items() if key in Profile.collectable
            ] + ctx_collectable_properties
            resource_type = self.register_resource_type(
                resource['uid'], tuple(persistent_properties)
            )
            if resource_type not in self._storage['resources'].keys():
                self._storage['resources'][resource_type] = {
                    key: [] for (key, _) in collectable_properties
                }
            for (key, value) in collectable_properties:
                self._storage['resources'][resource_type][key].append(value)

    def register_resource_type(self, uid, persistent_properties):
        """Registers tuple of persistent properties under new key or return existing one

        :param str uid: uid of the resource that will be used to describe the resource type
        :param tuple persistent_properties: tuple of persistent properties
        :return: uid corresponding to the tuple of persistent properties
        """
        property_key = str(convert.flatten(persistent_properties))
        uid_key = convert.flatten(uid)
        if property_key not in self._tuple_to_resource_type_map.keys():
            new_type = "{}#{}".format(uid_key, self._uid_counter[uid_key])
            self._tuple_to_resource_type_map[property_key] = new_type
            self._uid_counter[uid_key] += 1
            self._storage['resource_type_map'][new_type] = {
                key: value for (key, value) in persistent_properties
            }
        return self._tuple_to_resource_type_map[property_key]

    def __getitem__(self, item):
        """Returns the item stored in profile

        Note: No translation of resources is performed! Use all_resources instead!

        :param str item: key of the item we are getting
        :return: item stored in the profile
        """
        return self._storage[item]

    def __setitem__(self, key, value):
        """Sets the value into the storage under the key.

        Internally this finds a similar regions and registers them in either
        resource or config map.

        Note: No translation of resources is performed! Use update_resources instead!

        :param str key: key of the value
        :param object value:  object we are setting in the profile
        :return:
        """
        self._storage[key] = value

    def __delitem__(self, key):
        """Deletes the item in the storage

        :param str key: key to be deleted
        """
        del self._storage[key]

    def __iter__(self):
        """Iterates through all of the stuff in storage.

        :return: storage iterator
        """
        return self._storage.__iter__()

    def __len__(self):
        """Returns the size of the internal storage

        :return: size of the internal storage
        """
        return len(self._storage)

    def serialize(self):
        """Returns serializable representation of the profile

        :return: serializable representation (i.e. the actual storage)
        """
        return self._storage

    def _get_flattened_persistent_values_for(self, resource_type):
        """Flattens the nested values of the resources to single level

        E.g. the following resource:

        .. code-block:: json

            {
                "type": "memory",
                "amount": 4,
                "uid": {
                    "source": "../memory_collect_test.c",
                    "function": "main",
                    "line": 22
                }
            }

        is flattened as follows::

            {
                "type": "memory",
                "amount": 4,
                "uid": "../memory_collect_test.c:main:22",
                "uid:eource": "../memory_collect_test.c",
                "uid:function": "main",
                "uid:line": 22
            }

        :param str resource_type: type of the resource
        :return: flattened resource
        """
        if resource_type not in self._resource_type_to_flattened_resources_map.keys():
            persistent_properties = self._storage['resource_type_map'][resource_type]
            flattened_resources = dict(list(query.all_items_of(persistent_properties)))
            self._resource_type_to_flattened_resources_map[resource_type] = flattened_resources
        return self._resource_type_to_flattened_resources_map[resource_type]

    def all_resources(self, flatten_values=False):
        """Generator for iterating through all of the resources contained in the
        performance profile.

        Generator iterates through all of the snapshots, and subsequently yields
        collected resources. For more thorough description of format of resources
        refer to :pkey:`resources`. Resources are not flattened and, thus, can
        contain nested dictionaries (e.g. for `traces` or `uids`).

        :param bool flatten_values: if set to true, then the persistent values will
            be flattened to one level.
        :returns: iterable stream of resources represented as pair ``(int, dict)``
            of snapshot number and the resources w.r.t. the specification of the
            :pkey:`resources`
        """
        for resource_type, resources in self._storage['resources'].items():
            # uid: {...}
            if flatten_values:
                persistent_properties = self._get_flattened_persistent_values_for(resource_type)
            else:
                persistent_properties = self._storage['resource_type_map'][resource_type]

            if resources:
                resource_keys = resources.keys()
                for resource_values in zip(*resources.values()):
                    # collectable values should be flat
                    collectable_properties = dict(zip(resource_keys, resource_values))
                    collectable_properties.update(persistent_properties)
                    snapshot_number = collectable_properties.get('snapshot', 0)
                    yield snapshot_number, collectable_properties
            else:
                # In case we have only persistent properties
                yield persistent_properties.get('snapshot', 0), persistent_properties

    def all_resource_fields(self):
        """Generator for iterating through all of the fields (both flattened and
        original) that are occurring in the resources.

        E.g. considering the example profiles from :pkey:`resources`, the function
        yields the following for `memory`, `time` and `trace` profiles
        respectively (considering we convert the stream to list)::

            memory_resource_fields = [
                'type', 'address', 'amount', 'uid:function', 'uid:source',
                'uid:line', 'uid', 'trace', 'subtype'
            ]
            time_resource_fields = [
                'type', 'amount', 'uid'
            ]
            complexity_resource_fields = [
                'type', 'amount', 'structure-unit-size', 'subtype', 'uid'
            ]

        :returns: iterable stream of resource field keys represented as `str`
        """
        keys = set()
        for resource_type, resources in self._storage['resources'].items():
            # uid: {...}
            persistent_properties = query.all_items_of(
                self._storage['resource_type_map'][resource_type]
            )
            if resources:
                keys.update(resources.keys())
            keys.update({k for (k, v) in persistent_properties})
        return keys

    def all_filtered_models(self, models_strategy):
        """
        The function obtains models according to the given strategy.

        This function according to the given strategy and group derived from it
        obtains the models from the current profile. The function creates the
        relevant dictionary with required models or calls the responded functions,
        that returns the models according to the specifications.

        :param str models_strategy: name of detection models strategy to obtains relevant models
        :return ModelRecord: required models
        """
        group = models_strategy.rsplit('-')[1]
        if models_strategy in ('all-param', 'all-nonparam'):
            return get_filtered_best_models_of(self, group=group, model_filter=None)
        elif models_strategy in ('best-nonparam', 'best-model', 'best-param'):
            return get_filtered_best_models_of(self, group=group)

    def all_models(self, group='model'):
        """Generator of all 'models' records from the performance profile w.r.t.
        :ref:`profile-spec`.

        Form a profile, postprocessed by e.g. :ref:`postprocessors-regression-analysis`
        and iterates through all of its models (for more details about models refer
        to :pkey:`models` or :ref:`postprocessors-regression-analysis`).

        E.g. given some trace profile ``complexity_prof``, we can iterate its
        models as follows:

            >>> gen = complexity_prof.all_models()
            >>> gen.__next__()
            (0, {'x_start': 0, 'model': 'constant', 'method': 'full',
            'coeffs': [{'name': 'b0', 'value': 0.5644496762801648}, {'name': 'b1',
            'value': 0.0}], 'uid': 'SLList_insert(SLList*, int)', 'r_square': 0.0,
            'x_end': 11892})
            >>> gen.__next__()
            (1, {'x_start': 0, 'model': 'exponential', 'method': 'full',
            'coeffs': [{'name': 'b0', 'value': 0.9909792049684152}, {'name': 'b1',
            'value': 1.000004056250301}], 'uid': 'SLList_insert(SLList*, int)',
            'r_square': 0.007076437903106431, 'x_end': 11892})


        :param str group: the kind of requested models to return
        :returns: iterable stream of ``(int, dict)`` pairs, where first yields the
            positional number of model and latter correponds to one 'models'
            record (for more details about models refer to :pkey:`models` or
            :ref:`postprocessors-regression-analysis`)
        """
        for model_idx, model in enumerate(self._storage['models']):
            if group == 'model' or\
               (group == 'param' and model.get('model') in get_supported_models()) or\
               (group == 'nonparam' and model.get('model') in get_supported_nparam_methods()):
                yield model_idx, model

    def get_model_of(self, model_type, uid):
        """
        Finds specific model from profile according to the
        given kind of model and specific unique identification.

        :param str model_type: specific kind of required model (e.g. regressogram, constant, etc.)
        :param str uid: specific unique identification of required model
        :return dict: model with all its relevant items
        """
        for _, model in enumerate(self._storage['models']):
            if model_type == model['model'] and model['uid'] == uid:
                return model

    def all_snapshots(self):
        """Iterates through all the snapshots in resources

        Note this is required e.g. for heap map, which needs to group the resources by
        snapshots.

        :return: iterable of snapshot numbers and snapshot resources
        """
        all_resources = list(self.all_resources())
        all_resources.sort(key=operator.itemgetter(0))
        snapshot_map = collections.defaultdict(list)
        for number_of, res in itertools.groupby(all_resources, operator.itemgetter(0)):
            snapshot_map[number_of] = list(map(operator.itemgetter(1), res))
        maximal_snapshot = max(snapshot_map.keys())
        for i in range(0, maximal_snapshot+1):
            yield i, snapshot_map[i]

    # TODO: discuss the intent of __len__ and possibly merge?
    def resources_size(self):
        """ Returns the number of resources stored in the internal storage.

        :return int: the number of stored resources
        """
        return len(self._storage['resources'])


# Click helper
pass_profile = click.make_pass_decorator(Profile)
