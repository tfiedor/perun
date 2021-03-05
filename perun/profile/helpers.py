"""``perun.profile.factory`` specifies collective interface for basic
manipulation with profiles.

The format of profiles is w.r.t. :ref:`profile-spec`. This module contains
helper functions for loading and storing of the profiles either in the
persistent memory or in filesystem (in this case, the profile is in
uncompressed format).

.. _Python JSON library: https://docs.python.org/3.7/library/json.html

For further manipulations refer either to :ref:`profile-conversion-api`
(implemented in ``perun.profile.convert`` module) or :ref:`profile-query-api`
(implemented in ``perun.profile.query module``). For full specification how to
handle the JSON objects in Python refer to `Python JSON library`_.
"""

import json
import os
import time
import re
import operator

import perun.logic.pcs as pcs
import perun.logic.config as config
import perun.logic.store as store
import perun.logic.index as index
import perun.vcs as vcs
import perun.profile.query as query
import perun.utils.log as perun_log
import perun.utils.helpers as helpers

from perun.utils import get_module
from perun.profile.factory import Profile
from perun.utils.exceptions import InvalidParameterException, MissingConfigSectionException, \
                                   TagOutOfRangeException
from perun.utils.structs import Unit, Executable, Job

__author__ = 'Tomas Fiedor'


PROFILE_COUNTER = 0
DEFAULT_SORT_KEY = 'time'


def lookup_value(container, key, missing):
    """Helper function for getting the key from the container. If it is not present in the container
    or it is empty string or empty object, the function should return the missing constant.

    :param dict container: dictionary container
    :param str key: string representation of the key
    :param str missing: string constant that is returned if key is not present in container,
        or is set to empty string or None.
    :return:
    """
    return str(container.get(key, missing)) or missing


def sanitize_filepart(part):
    """Helper function for sanitization of part of the filenames

    :param part: part of the filename, that needs to be sanitized, i.e. we are removing invalid
        characters
    :return: sanitized string representation of the part
    """
    invalid_characters = r"# %&{}\<>*?/ $!'\":@"
    return "".join('_' if c in invalid_characters else c for c in str(part))


def lookup_param(profile, unit, param):
    """Helper function for looking up the unit in the profile (can be either collector or
    postprocessor and finds the value of the param in it

    :param dict profile: dictionary with profile information w.r.t profile specification
    :param str unit: unit in which the parameter is located
    :param str param: parameter we will use in the resulting profile
    :return:
    """
    unit_param_map = {
        post['name']: post['params'] for post in profile.get('postprocessors', [])
    }
    used_collector = profile['collector_info']
    unit_param_map.update({
        used_collector.get('name', '?'): used_collector.get('params', {})
    })

    # Lookup the unit params
    unit_params = unit_param_map.get(unit)
    if unit_params:
        return sanitize_filepart(list(query.all_key_values_of(unit_params, param))[0]) or "_"
    else:
        return "_"


def generate_profile_name(profile):
    """Constructs the profile name with the extension .perf from the job.

    The profile is identified by its binary, collector, workload and the time
    it was run.

    Valid tags:
        `%collector%`:
            Name of the collector
        `%postprocessors%`:
            Joined list of postprocessing phases
        `%<unit>.<param>%`:
            Parameter of the collector given by concrete name
        `%cmd%`:
            Command of the job
        `%args%`:
            Arguments of the job
        `%workload%`:
            Workload of the job
        `%type%`:
            Type of the generated profile
        `%date%`:
            Current date
        `%origin%`:
            Origin of the profile
        `%counter%`:
            Increasing argument

    :param dict profile: generate the corresponding profile for given name
    :returns str: string for the given profile that will be stored
    """
    global PROFILE_COUNTER
    fmt_parser = re.Scanner([
        (r"%collector%", lambda scanner, token:
            lookup_value(profile['collector_info'], 'name', "_")
        ),
        (r"%postprocessors%", lambda scanner, token:
            ("after-" + "-and-".join(map(lambda p: p['name'], profile['postprocessors'])))
                if profile['postprocessors'] else '_'
        ),
        (r"%[^.]+\.[^%]+%", lambda scanner, token:
            lookup_param(profile, *token[1:-1].split('.', maxsplit=1))
        ),
        (r"%cmd%", lambda scanner, token:
            os.path.split(lookup_value(profile['header'], 'cmd', '_'))[-1]
        ),
        (r"%args%", lambda scanner, token:
            "[" + sanitize_filepart(lookup_value(profile['header'], 'args', '_')) + "]"
        ),
        (r"%workload%", lambda scanner, token:
            "[" + sanitize_filepart(
                os.path.split(lookup_value(profile['header'], 'workload', '_'))[-1]
            ) + "]"
        ),
        (r"%type%", lambda scanner, token: lookup_value(profile['header'], 'type', '_')),
        (r"%date%", lambda scanner, token: time.strftime("%Y-%m-%d-%H-%M-%S", time.gmtime())),
        (r"%origin%", lambda scanner, token: lookup_value(profile, 'origin', '_')),
        (r"%counter%", lambda scanner, token: str(PROFILE_COUNTER)),
        (r"%%", lambda scanner, token: token),
        ('[^%]+', lambda scanner, token: token)
    ])
    PROFILE_COUNTER += 1

    # Obtain the formatting template from the configuration
    template = config.lookup_key_recursively('format.output_profile_template')
    tokens, rest = fmt_parser.scan(template)
    if rest:
        perun_log.error("formatting string '{}' could not be parsed\n\n".format(template) +
                        "Run perun config to modify the formatting pattern. "
                        "Refer to documentation for more information about formatting patterns")
    return "".join(tokens) + ".perf"


def load_list_for_minor_version(minor_version):
    """Returns profiles assigned to the given minor version.

    :param str minor_version: identification of the commit (preferably sha1)
    :returns list: list of ProfileInfo parsed from index of the given minor_version
    """
    # Compute the
    profiles = index.get_profile_list_for_minor(pcs.get_object_directory(), minor_version)
    profile_info_list = []
    for index_entry in profiles:
        inside_info = {
            'header': {
                'type': index_entry.type,
                'cmd': index_entry.cmd,
                'args': index_entry.args,
                'workload': index_entry.workload
            },
            'collector_info': {'name': index_entry.collector},
            'postprocessors': [
                {'name': p} for p in index_entry.postprocessors
            ]
        }
        _, profile_name = store.split_object_name(pcs.get_object_directory(), index_entry.checksum)
        profile_info \
            = ProfileInfo(index_entry.path, profile_name, index_entry.time, inside_info)
        profile_info_list.append(profile_info)

    return profile_info_list


@vcs.lookup_minor_version
def get_nth_profile_of(position, minor_version):
    """Returns the profile at nth position in the index

    :param int position: position of the profile we are obtaining
    :param str minor_version: looked up minor version for the wrapped vcs

    :return str: path of the profile at nth position in the index
    """
    registered_profiles = load_list_for_minor_version(minor_version)
    sort_profiles(registered_profiles)
    if 0 <= position < len(registered_profiles):
        return registered_profiles[position].realpath
    else:
        raise TagOutOfRangeException(position, len(registered_profiles) - 1)


@vcs.lookup_minor_version
def find_profile_entry(profile, minor_version):
    """ Finds the profile entry within the index file of the minor version.

    :param str profile: the profile identification, can be given as tag, sha value,
                        sha-path (path to tracked profile in obj) or source-name
    :param str minor_version: the minor version representation or None for HEAD

    :return IndexEntry: the profile entry from the index file
    """

    minor_index = index.find_minor_index(minor_version)

    # If profile is given as tag, obtain the sha-path of the file
    tag_match = store.INDEX_TAG_REGEX.match(profile)
    if tag_match:
        profile = get_nth_profile_of(int(tag_match.group(1)), minor_version)
    # Transform the sha-path (obtained or given) to the sha value
    if not store.is_sha1(profile) and not profile.endswith('.perf'):
        profile = store.version_path_to_sha(profile)

    # Search the minor index for the requested profile
    with open(minor_index, 'rb') as index_handle:
        # The profile can be only sha value or source path now
        if store.is_sha1(profile):
            return index.lookup_entry_within_index(index_handle, lambda x: x.checksum == profile,
                                                   profile)
        else:
            return index.lookup_entry_within_index(index_handle, lambda x: x.path == profile,
                                                   profile)


def generate_units(collector):
    """Generate information about units used by the collector.

    Note that this is mostly placeholder for future extension, how the units will be handled.

    :param module collector: collector module that collected the data
    :returns dict: dictionary with map of resources to units
    """
    return collector.COLLECTOR_DEFAULT_UNITS


def generate_header_for_profile(job):
    """
    :param Job job: job with information about the computed profile
    :returns dict: dictionary in form of {'header': {}} corresponding to the perun specification
    """
    try:
        collector = get_module('.'.join(['perun.collect', job.collector.name]))
    except ImportError:
        perun_log.error("could not find the package for collector {}".format(job.collector.name))

    return {
        'type': collector.COLLECTOR_TYPE,
        'cmd': job.executable.cmd,
        'args': job.executable.args,
        'workload': job.executable.workload,
        'units': generate_units(collector)
    }


def generate_collector_info(job):
    """
    :param Job job: job with information about the computed profile
    :returns dict: dictionary in form of {'collector_info': {}} corresponding to the perun
        specification
    """
    return {
        'name': job.collector.name,
        'params': job.collector.params
    }


def generate_postprocessor_info(job):
    """
    :param Job job: job with information about the computed profile
    :returns dict: dictionary in form of {'postprocess_info': []} corresponding to the perun spec
    """
    return [
        {
            'name': postprocessor.name,
            'params': postprocessor.params
        } for postprocessor in job.postprocessors
    ]


def finalize_profile_for_job(profile, job):
    """
    :param Profile profile: collected profile through some collector
    :param Job job: job with informations about the computed profile
    :returns dict: valid profile JSON file
    """
    profile.update({'origin': vcs.get_minor_head()})
    profile.update({'header': generate_header_for_profile(job)})
    profile.update({'collector_info': generate_collector_info(job)})
    profile.update({'postprocessors': generate_postprocessor_info(job)})
    return profile


def to_string(profile):
    """Converts profile from dictionary to string

    :param Profile profile: profile we are converting to string
    :returns str: string representation of profile
    """
    return json.dumps(profile.serialize())


def to_config_tuple(profile):
    """Converts the profile to the tuple representing its configuration

    :param dict profile: profile we are converting to configuration tuple
    :returns: tuple of (collector.name, cmd, args, workload, [postprocessors])
    """
    profile_header = profile['header']
    return (
        profile['collector_info']['name'],
        profile_header.get('cmd', ''),
        profile_header.get('args', ''),
        profile_header.get('workload', ''),
        [postprocessor['name'] for postprocessor in profile['postprocessors']]
    )


def config_tuple_to_cmdstr(config_tuple):
    """Converts tuple to command string

    :param tuple config_tuple: tuple of (collector, cmd, args, workload, postprocessors)
    :return: string representing the executed command
    """
    return " ".join(filter(lambda x: x, config_tuple[1:4]))


def extract_job_from_profile(profile):
    """Extracts information from profile about job, that was done to generate the profile.

    Fixme: Add assert that profile is profile

    :param dict profile: dictionary with valid profile
    :returns Job: job according to the profile informations
    """
    collector_record = profile['collector_info']
    collector = Unit(collector_record['name'], collector_record['params'])

    posts = []
    for postprocessor in profile['postprocessors']:
        posts.append(Unit(postprocessor['name'], postprocessor['params']))

    cmd = profile['header']['cmd']
    args = helpers.get_key_with_aliases(profile['header'], ('args', 'params'))
    workload = profile['header']['workload']
    executable = Executable(cmd, args, workload)

    return Job(collector, posts, executable)


def is_key_aggregatable_by(profile, func, key, keyname):
    """Check if the key can be aggregated by the function.

    Everything is countable and hence 'count' and 'nunique' (number of unique values) are
    valid aggregation functions for everything. Otherwise (e.g. sum, mean), we need numerical
    values.

    :param dict profile: profile that will be used against in the validation
    :param function func: function used for aggregation of the data
    :param str key: key that will be aggregated in the graph
    :param str keyname: name of the validated key
    :returns bool: true if the key is aggregatable by the function
    :raises InvalidParameterException: if the of_key does not support the given function
    """
    # Everything is countable ;)
    if func in ('count', 'nunique'):
        return True

    # Get all valid numeric keys and validate
    valid_keys = set(query.all_numerical_resource_fields_of(profile))
    if key not in valid_keys:
        choices = "(choose either count/nunique as aggregation function;"
        choices += " or from the following keys: {})".format(
            ", ".join(map(str, valid_keys))
        )
        raise InvalidParameterException(keyname, key, choices)
    return True


def sort_profiles(profile_list, reverse_profiles=True):
    """Sorts the profiles according to the key set in either configuration.

    The key can either be specified in temporary configuration, or in any of the local or global
    configs as the key :ckey:`format.sort_profiles_by` attributes. Be default, profiles are sorted
    by time. In case of any errors (invalid sort key or missing key) the profiles will be sorted by
    default key as well.

    :param list profile_list: list of ProfileInfo object
    :param true reverse_profiles: true if the order of the sorting should be reversed
    """
    sort_order = DEFAULT_SORT_KEY
    try:
        sort_order = config.lookup_key_recursively('format.sort_profiles_by')
        # If the stored key is invalid, we use the default time as well
        if sort_order not in ProfileInfo.valid_attributes:
            perun_log.warn("invalid sort key '{}'".format(sort_order) +
                           " Profiles will be sorted by '{}'\n\n".format(sort_order) +
                           "Please set sort key in config or cli to one"
                           " of ({}".format(", ".join(ProfileInfo.valid_attributes)) + ")")
            sort_order = DEFAULT_SORT_KEY
    except MissingConfigSectionException:
        perun_log.warn("missing set option 'format.sort_profiles_by'!"
                       " Profiles will be sorted by '{}'\n\n".format(sort_order) +
                       "Please run 'perun config edit' and set 'format.sort_profiles_by' to one"
                       " of ({}".format(", ".join(ProfileInfo.valid_attributes)) + ")")

    profile_list.sort(key=operator.attrgetter(sort_order), reverse=reverse_profiles)


def merge_resources_of(lhs, rhs):
    """Merges the resources of lhs and rhs profiles

    :param Profile lhs: left operator of the profile merge
    :param Profile rhs: right operator of the profile merge
    :return: profile with merged resources
    """
    # Not Good: Temporary solution:
    if not isinstance(rhs, Profile):
        rhs = Profile(rhs)

    # Return lhs/rhs if rhs/lhs is empty
    if rhs.resources_size() == 0:
        return lhs
    elif lhs.resources_size() == 0:
        return rhs

    lhs_res = [res[1] for res in lhs.all_resources()] if lhs else []
    rhs_res = [res[1] for res in rhs.all_resources()] if rhs else []
    lhs_res.extend(rhs_res)
    lhs.update_resources(lhs_res, clear_existing_resources=True)

    return lhs


def _get_default_variable(profile, supported_variables):
    """Helper function that determines default variable for profile based on list of supported
    variables.

    Note that this returns the first suitable candidate, so it is expected that supported_variables
    are sorted by their priority.

    :param Profile profile: input profile
    :param tuple supported_variables: list of supported fields
    :return: default key picked from the list of supported fields (either for dependent or
        independent variables)
    """
    resource_fields = list(profile.all_resource_fields())
    candidates = [var for var in supported_variables if var in set(resource_fields)]
    if candidates:
        # Return first suitable candidate, according to the given order
        return candidates[0]
    else:
        perun_log.error(
            "Profile does not contain (in)dependent variable. Has to be one of: {}".format(
                "(" + ", ".join(supported_variables) + ")"
            )
        )


def get_default_independent_variable(profile):
    """Returns default independent variable for the given profile

    :param Profile profile: input profile
    :return: default independent variable
    """
    return _get_default_variable(profile, Profile.independent)


def get_default_dependent_variable(profile):
    """Returns default dependent variable for the given profile

    :param Profile profile: input profile
    :return: default dependent variable
    """
    return _get_default_variable(profile, Profile.dependent)


class ProfileInfo:
    """Structure for storing information about profiles.

    This is mainly used for formatted output of the profile list using
    the command line interface
    """
    def __init__(self, path, real_path, mtime, profile_info, is_raw_profile=False):
        """
        :param str path: contains the name of the file, which identifies it in the index
        :param str real_path: real path to the profile, i.e. how can it really be accessed
            this is either in jobs, in objects or somewhere else
        :param str mtime: time of the modification of the profile
        :param bool is_raw_profile: true if the stored profile is raw, i.e. in json and not
            compressed
        """

        self._is_raw_profile = is_raw_profile
        self.source = path
        self.realpath = os.path.relpath(real_path, os.getcwd())
        self.time = mtime
        self.type = profile_info['header']['type']
        self.cmd = profile_info['header']['cmd']
        self.args = helpers.get_key_with_aliases(profile_info['header'], ('args', 'params'))
        self.workload = profile_info['header']['workload']
        self.collector = profile_info['collector_info']['name']
        self.postprocessors = [
            postprocessor['name'] for postprocessor in profile_info['postprocessors']
        ]
        self.checksum = None
        self.config_tuple = (
            self.collector, self.cmd, self.args, self.workload,
            ",".join(self.postprocessors)
        )

    def load(self):
        """Loads the profile from given file

        This is basically a wrapper that loads the profile, whether it is raw (i.e. in pending)
        or not raw and stored in index

        :return: loaded profile in dictionary format, w.r.t :ref:`profile-spec`
        """
        return store.load_profile_from_file(self.realpath, self._is_raw_profile)

    valid_attributes = [
        "realpath", "type", "time", "cmd", "args", "workload", "collector", "checksum", "source"
    ]
