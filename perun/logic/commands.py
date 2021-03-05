"""Commands is a core of the perun implementation containing the basic commands.

Commands contains implementation of the basic commands of perun pcs. It is meant
to be run both from GUI applications and from CLI, where each of the function is
possible to be run in isolation.
"""

import collections
import os
import re

from operator import itemgetter

import colorama

import perun.logic.pcs as pcs
import perun.logic.config as perun_config
import perun.logic.store as store
import perun.logic.index as index
import perun.profile.helpers as profile
import perun.utils as utils
import perun.utils.helpers as helpers
import perun.utils.log as perun_log
import perun.utils.timestamps as timestamp
import perun.vcs as vcs
import perun.logic.temp as temp
import perun.logic.stats as stats

from perun.utils.exceptions import NotPerunRepositoryException, \
    ExternalEditorErrorException, MissingConfigSectionException, InvalidTempPathException, \
    ProtectedTempException
from perun.utils.helpers import \
    TEXT_EMPH_COLOUR, TEXT_ATTRS, TEXT_WARN_COLOUR, \
    PROFILE_TYPE_COLOURS, SUPPORTED_PROFILE_TYPES, HEADER_ATTRS, HEADER_COMMIT_COLOUR, \
    HEADER_INFO_COLOUR, HEADER_SLASH_COLOUR, PROFILE_DELIMITER, MinorVersion
from perun.utils.log import cprint, cprintln
from perun.utils.structs import ProfileListConfig

# Init colorama for multiplatform colours
colorama.init()
UNTRACKED_REGEX = \
    re.compile(r"([^\\]+)-([0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{2}-[0-9]{2}-[0-9]{2}).perf")
# Regex for parsing the formating tag [<tag>:<size>f<fill_char>]
FMT_REGEX = re.compile(r"%([a-zA-Z]+)(:[0-9]+)?(f.)?%")


def config_get(store_type, key):
    """Gets from the store_type configuration the value of the given key.

    :param str store_type: type of the store lookup (local, shared of recursive)
    :param str key: list of section delimited by dot (.)
    """
    config_store = pcs.global_config() if store_type in ('shared', 'global') else pcs.local_config()

    if store_type == 'recursive':
        value = perun_config.lookup_key_recursively(key)
    else:
        value = config_store.get(key)
    perun_log.info("{}: {}".format(key, value))


def config_set(store_type, key, value):
    """Sets in the store_type configuration the key to the given value.

    :param str store_type: type of the store lookup (local, shared of recursive)
    :param str key: list of section delimited by dot (.)
    :param object value: arbitrary value that will be set in the configuration
    """
    config_store = pcs.global_config() if store_type in ('shared', 'global') else pcs.local_config()

    config_store.set(key, value)
    perun_log.info("Value '{1}' set for key '{0}'".format(key, value))


def config_edit(store_type):
    """Runs the external editor stored in general.editor key in order to edit the config file.

    :param str store_type: type of the store (local, shared, or recursive)
    :raises MissingConfigSectionException: when the general.editor is not found in any config
    :raises ExternalEditorErrorException: raised if there are any problems during invoking of
        external editor during the 'edit' operation
    """
    # Lookup the editor in the config and run it as external command
    editor = perun_config.lookup_key_recursively('general.editor')
    config_file = pcs.get_config_file(store_type)
    try:
        utils.run_external_command([editor, config_file])
    except Exception as inner_exception:
        raise ExternalEditorErrorException(editor, str(inner_exception))


def config_reset(store_type, config_template):
    """Resets the given store_type to a default type (or to a selected configuration template)

    For more information about configuration templates see :ref:`config-templates`.

    :param str store_type: name of the store (local or global) which we are resetting
    :param str config_template: name of the template that we are resetting to
    :raises NotPerunRepositoryException: raised when we are outside of any perun scope
    """
    if store_type in ('shared', 'global'):
        shared_location = perun_config.lookup_shared_config_dir()
        perun_config.init_shared_config_at(shared_location)
    else:
        vcs_config = {
            'vcs': {
                'url': pcs.get_vcs_path(),
                'type': pcs.get_vcs_type()
            }
        }
        perun_config.init_local_config_at(pcs.get_path(), vcs_config, config_template)
    perun_log.info("{} configuration reset{}".format(
        'global' if store_type in ('shared', 'global') else 'local',
        " to {}".format(config_template) if store not in ("shared", "global") else ""
    ))


def init_perun_at(perun_path, is_reinit, vcs_config, config_template='master'):
    """Initialize the .perun directory at given path

    Initializes or reinitializes the .perun directory at the given path.

    :param path perun_path: path where new perun performance control system will be stored
    :param bool is_reinit: true if this is existing perun, that will be reinitialized
    :param dict vcs_config: dictionary of form {'vcs': {'type', 'url'}} for local config init
    :param str config_template: name of the configuration template
    """
    # Initialize the basic structure of the .perun directory
    perun_full_path = os.path.join(perun_path, '.perun')
    helpers.touch_dir(perun_full_path)
    helpers.touch_dir(os.path.join(perun_full_path, 'objects'))
    helpers.touch_dir(os.path.join(perun_full_path, 'jobs'))
    helpers.touch_dir(os.path.join(perun_full_path, 'logs'))
    helpers.touch_dir(os.path.join(perun_full_path, 'cache'))
    helpers.touch_dir(os.path.join(perun_full_path, 'stats'))
    helpers.touch_dir(os.path.join(perun_full_path, 'tmp'))
    # If the config does not exist, we initialize the new version
    if not os.path.exists(os.path.join(perun_full_path, 'local.yml')):
        perun_config.init_local_config_at(perun_full_path, vcs_config, config_template)
    else:
        perun_log.info('configuration file already exists. Run ``perun config reset`` to reset'
                       ' configuration to default state.')

    # Perun successfully created
    msg_prefix = "Reinitialized existing" if is_reinit else "Initialized empty"
    perun_log.msg_to_stdout(msg_prefix + " Perun repository in {}".format(perun_path), 0)


def init(dst, configuration_template='master', **kwargs):
    """Initializes the performance and version control systems

    Inits the performance control system at a given directory. Optionally inits the
    wrapper of the Version Control System that is used as tracking point.

    :param path dst: path where the pcs will be initialized
    :param dict kwargs: keyword arguments of the initialization
    :param str configuration_template: name of the template that will be used for initialization
        of local configuration
    """
    perun_log.msg_to_stdout("call init({}, {})".format(dst, kwargs), 2)

    # First init the wrapping repository well
    vcs_type = kwargs['vcs_type']
    vcs_path = kwargs['vcs_path'] or dst
    vcs_params = kwargs['vcs_params']

    # Construct local config
    vcs_config = {
        'vcs': {
            'url': vcs_path,
            'type': vcs_type
        }
    }

    # Check if there exists perun directory above and initialize the new pcs
    try:
        super_perun_dir = helpers.locate_perun_dir_on(dst)
        is_pcs_reinitialized = (super_perun_dir == dst)
        if not is_pcs_reinitialized:
            perun_log.warn("There exists super perun directory at {}".format(super_perun_dir))
    except NotPerunRepositoryException:
        is_pcs_reinitialized = False

    init_perun_at(dst, is_pcs_reinitialized, vcs_config, configuration_template)

    # If the wrapped repo could not be initialized we end with error. The user should adjust this
    # himself and fix it in the config. Note that this decision was made after tagit design,
    # where one needs to further adjust some options in initialized directory.
    if vcs_type and not vcs.init(vcs_params):
        err_msg = "Could not initialize empty {0} repository at {1}.\n".format(vcs_type, vcs_path)
        err_msg += "Either reinitialize perun with 'perun init' or initialize {0} repository"
        err_msg += "manually and fix the path to vcs in 'perun config --edit'"
        perun_log.error(err_msg)


@vcs.lookup_minor_version
def add(profile_names, minor_version, keep_profile=False, force=False):
    """Appends @p profile to the @p minor_version inside the @p pcs

    :param generator profile_names: generator of profiles that will be stored for the minor version
    :param str minor_version: SHA-1 representation of the minor version
    :param bool keep_profile: if true, then the profile that is about to be added will be not
        deleted, and will be kept as it is. By default false, i.e. profile is deleted.
    :param bool force: if set to true, then the add will be forced, i.e. the check for origin will
        not be performed.
    """
    added_profile_count = 0
    for profile_name in profile_names:
        # Test if the given profile exists (This should hold always, or not?)
        if not os.path.exists(profile_name):
            perun_log.error("profile {} does not exists".format(profile_name), recoverable=True)
            continue

        # Load profile content
        # Unpack to JSON representation
        unpacked_profile = store.load_profile_from_file(profile_name, True)

        if not force and unpacked_profile['origin'] != minor_version:
            error_msg = "cannot add profile '{}' to minor index of '{}':".format(
                profile_name, minor_version
            )
            error_msg += "profile originates from minor version '{}'".format(
                unpacked_profile['origin']
            )
            perun_log.error(error_msg, recoverable=True)
            continue

        # Remove origin from file
        unpacked_profile.pop('origin')
        profile_content = profile.to_string(unpacked_profile)

        # Append header to the content of the file
        header = "profile {} {}\0".format(unpacked_profile['header']['type'], len(profile_content))
        profile_content = (header + profile_content).encode('utf-8')

        # Transform to internal representation - file as sha1 checksum and content packed with zlib
        profile_sum = store.compute_checksum(profile_content)
        compressed_content = store.pack_content(profile_content)

        # Add to control
        object_dir = pcs.get_object_directory()
        store.add_loose_object_to_dir(object_dir, profile_sum, compressed_content)

        # Register in the minor_version index
        index.register_in_minor_index(
            object_dir, minor_version, profile_name, profile_sum, unpacked_profile
        )

        # Remove the file
        if not keep_profile:
            os.remove(profile_name)

        added_profile_count += 1

    profile_names_len = len(profile_names)
    if added_profile_count != profile_names_len:
        perun_log.error("could not register {} in index: {} failed".format(
            helpers.str_to_plural(added_profile_count, "profile"),
            added_profile_count - profile_names_len
        ))
    perun_log.info("successfully registered {} profiles in index".format(added_profile_count))


@vcs.lookup_minor_version
def remove_from_index(profile_generator, minor_version):
    """Removes @p profile from the @p minor_version inside the @p pcs

    :param generator profile_generator: profile that will be stored for the minor version
    :param str minor_version: SHA-1 representation of the minor version
    :raisesEntryNotFoundException: when the given profile_generator points to non-tracked profile
    """
    object_directory = pcs.get_object_directory()
    index.remove_from_index(object_directory, minor_version, profile_generator)


def remove_from_pending(profile_generator):
    """Removes profiles from the pending jobs directory (i.e, `.perun/jobs`

    :param generator profile_generator: generator of profiles that will be removed from pending jobs
    """
    removed_profile_number = len(profile_generator)
    for i, pending_file in enumerate(profile_generator):
        os.remove(pending_file)
        perun_log.info("{}/{} deleted {} from pending jobs".format(
            helpers.format_counter_number(i+1, removed_profile_number),
            removed_profile_number,
            perun_log.in_color(os.path.split(pending_file)[1], 'grey'),
        ))

    if removed_profile_number:
        result_string = perun_log.in_color("{}".format(
            helpers.str_to_plural(removed_profile_number, "profile")
        ), 'white', 'bold')
        perun_log.info("successfully removed {} from pending jobs".format(
            result_string
        ))


def calculate_profile_numbers_per_type(profile_list):
    """Calculates how many profiles of given type are in the profile type.

    Returns dictionary mapping types of profiles (i.e. memory, time, ...) to the
    number of profiles that are occurring in the profile list. Used for statistics
    about profiles corresponding to minor versions.

    :param list profile_list: list of ProfileInfo with information about profiles
    :returns dict: dictionary mapping profile types to number of profiles of given type in the list
    """
    profile_numbers = collections.defaultdict(int)
    for profile_info in profile_list:
        profile_numbers[profile_info.type] += 1
    profile_numbers['all'] = len(profile_list)
    return profile_numbers


def print_profile_numbers(profile_numbers, profile_types, line_ending='\n'):
    """Helper function for printing the numbers of profile to output.

    :param dict profile_numbers: dictionary of number of profiles grouped by type
    :param str profile_types: type of the profiles (tracked, untracked, etc.)
    :param str line_ending: ending of the print (for different outputs of log and status)
    """
    if profile_numbers['all']:
        print("{0[all]} {1} profiles (".format(profile_numbers, profile_types), end='')
        first_printed = False
        for profile_type in SUPPORTED_PROFILE_TYPES:
            if not profile_numbers[profile_type]:
                continue
            print(', ' if first_printed else '', end='')
            first_printed = True
            type_colour = PROFILE_TYPE_COLOURS[profile_type]
            cprint("{0} {1}".format(profile_numbers[profile_type], profile_type), type_colour)
        print(')', end=line_ending)
    else:
        cprintln('(no {} profiles)'.format(profile_types), TEXT_WARN_COLOUR, attrs=TEXT_ATTRS)


def turn_off_paging_wrt_config(paged_function):
    """Helper function for checking if the function should be paged or not according to the config
    setting ``general.paging``.

    If in global config the ``genera.paging`` is set to ``always``, then any function should be
    paged. Otherwise we check if ``general.paging`` contains either ``only-log`` or ``only-status``.

    :param str paged_function: name of the paged function, which will be looked up in config
    :return: true if the function should be paged (unless --no-pager is set)
    """
    try:
        paging_option = perun_config.shared().get('general.paging')
    # Test for backward compatibility with old instances of Perun and possible issues
    except MissingConfigSectionException:
        perun_log.warn("""corrupted shared configuration file: missing ``general.paging`` option.

Run ``perun config --shared --edit`` and set the ``general.paging`` to one of following:
    always, only-log, only-status, never

Consult the documentation (Configuration and Logs) for more information about paging of
output of status, log and others.
        """)
        return True
    return paging_option == 'always' or \
        (paging_option.startswith('only-') and paging_option.endswith(paged_function))


@perun_log.paged_function(paging_switch=turn_off_paging_wrt_config('log'))
@vcs.lookup_minor_version
def log(minor_version, short=False, **_):
    """Prints the log of the performance control system

    Either prints the short or longer version. In short version, only header and short
    list according to the formatting string from stored in the configuration. Prints
    the number of profiles associated with each of the minor version and some basic
    information about minor versions, like e.g. description, hash, etc.

    :param str minor_version: representation of the head version
    :param bool short: true if the log should be in short format
    """
    perun_log.msg_to_stdout("Running inner wrapper of the 'perun log '", 2)

    # Print header for --short-minors
    if short:
        minor_versions = list(vcs.walk_minor_versions(minor_version))
        # Reduce the descriptions of minor version to one liners
        for mv_no, minor in enumerate(minor_versions):
            minor_versions[mv_no] = minor._replace(desc=minor.desc.split("\n")[0])
        minor_version_maxima = calculate_maximal_lengths_for_object_list(
            minor_versions, MinorVersion._fields
        )
        # Update manually the maxima for the printed supported profile types, each requires two
        # characters and 9 stands for " profiles" string

        def minor_stat_retriever(minor_v):
            """Helper function for picking stats of the given minor version

            :param MinorVersion minor_v: minor version for which we are retrieving the stats
            :return: dictionary with stats for minor version
            """
            return index.get_profile_number_for_minor(
                pcs.get_object_directory(), minor_v.checksum
            )

        def deg_count_retriever(minor_v):
            """Helper function for picking stats of the degradation strings of form ++--

            :param MinorVersion minor_v: minor version for which we are retrieving the stats
            :return: dictionary with stats for minor version
            """
            counts = perun_log.count_degradations_per_group(
                store.load_degradation_list_for(pcs.get_object_directory(), minor_v.checksum)
            )
            return {'changes': counts.get('Optimization', 0)*'+' + counts.get('Degradation', 0)*'-'}

        minor_version_maxima.update(
            calculate_maximal_lengths_for_stats(minor_versions, minor_stat_retriever)
        )
        minor_version_maxima.update(
            calculate_maximal_lengths_for_stats(minor_versions, deg_count_retriever, " changes ")
        )
        print_shortlog_minor_version_info_list(minor_versions, minor_version_maxima)
    else:
        # Walk the minor versions and print them
        for minor in vcs.walk_minor_versions(minor_version):
            cprintln("Minor Version {}".format(minor.checksum), TEXT_EMPH_COLOUR, attrs=TEXT_ATTRS)
            base_dir = pcs.get_object_directory()
            tracked_profiles = index.get_profile_number_for_minor(base_dir, minor.checksum)
            print_profile_numbers(tracked_profiles, 'tracked')
            print_minor_version_info(minor, indent=1)


def adjust_limit(limit, attr_type, maxima, padding=0):
    """Returns the adjusted value of the limit for the given field output in status or log

    Takes into the account the limit, which is specified in the field (e.g. as checksum:6),
    the maximal values of the given fields. Additionally, one can add a padding, e.g. for
    the type tag.

    :param match limit: matched string from the formatting string specifying the limit
    :param str attr_type: string name of the attribute, which we are limiting
    :param dict maxima: maximas of values of given attribute types
    :param int padding: additional padding of the limit not contributed to maxima
    :return: adjusted value of the limit w.r.t. attribute type and maxima
    """
    return max(int(limit[1:]), len(attr_type)) if limit else maxima[attr_type] + padding


def print_shortlog_minor_version_info_list(minor_version_list, max_lengths):
    """Prints list of profiles and counts per type of tracked/untracked profiles.

    Prints the list of profiles, trims the sizes of each information according to the
    computed maximal lengths If the output is short, the list itself is not printed,
    just the information about counts. Tracked and untracked differs in colours.

    Example of the output:

    checksum ( a|m|x|t profiles)                  desc                        changes
    aac4d21a (24|0|0|0 profiles) Bump version and changelog to 0.17.2
    91373c43 ( 2|0|0|2 profiles) Bump version and changelog to 0.16.8

    :param list minor_version_list: list of profiles of MinorVersionInfo objects
    :param dict max_lengths: dictionary with maximal sizes for the output of profiles
    """

    # Load formating string for profile
    minor_version_info_fmt = perun_config.lookup_key_recursively('format.shortlog')
    fmt_tokens = perun_log.scan_formatting_string(
        minor_version_info_fmt, {}, default_fmt_callback=lambda token: "%" + token + "%"
    )

    # Print header (2 is padding for id), e.g.:
    # checksum ( a|m|x|t profiles)                  desc                        changes
    print_shortlog_profile_list_header(fmt_tokens, max_lengths)

    # Print profiles, e.g.:
    # aac4d21a (24|0|0|0 profiles) Bump version and changelog to 0.17.2
    # 91373c43 ( 2|0|0|2 profiles) Bump version and changelog to 0.16.8
    print_shortlog_profile_list(fmt_tokens, max_lengths, minor_version_info_fmt, minor_version_list)


def print_shortlog_profile_list(tokens, max_lengths, fmt_string, minor_versions):
    """For each minor versions, prints the stats w.r.t to the formatting tokens specified in
    @p tokens.

    Iterates through all of the minor versions, and then outputs one row according to the formatting
    tokens and their values in the specified versions. Each column is adjusted according to its
    maximal widths.

    The example of output is:

    aac4d21a (24|0|0|0 profiles) Bump version and changelog to 0.17.2
    91373c43 ( 2|0|0|2 profiles) Bump version and changelog to 0.16.8
    <token->  <-----token----->  <--------------token--------------->

    :param list tokens: list of formatting tokens
    :param dict max_lengths: dictionary mapping the maximal lengths of each value corresponding to
        column of the formatting token
    :param str fmt_string: formatting string
    :param list minor_versions: list of profiles of MinorVersionInfo objects
    """
    stat_length = sum([
        max_lengths['all'], max_lengths['time'], max_lengths['mixed'], max_lengths['memory']
    ]) + 3 + len(" profiles")

    for minor_version in minor_versions:
        for (token_type, token) in tokens:
            if token_type == 'fmt_string':
                print_shortlog_token(fmt_string, max_lengths, minor_version, stat_length, token)
            # Non-token parts of the formatting string are printed as they are
            else:
                cprint(token, 'white')
        perun_log.info("")


def print_shortlog_token(fmt_string, max_lengths, minor_version, stat_len, token):
    """Prints token of the formatting string.

    Example of tokens are highlighted below:

    aac4d21a (24|0|0|0 profiles) Bump version and changelog to 0.17.2
    91373c43 ( 2|0|0|2 profiles) Bump version and changelog to 0.16.8
    <token->  <-----token----->  <--------------token--------------->

    :param dict max_lengths: dictionary mapping the maximal lengths of each value corresponding to
        column of the formatting token
    :param str fmt_string: formating string
    :param MinorVersionInfo minor_version: MinorVersionInfo objects
    :param int stat_len: the whole length of the formatting header
    :param string token: one given token of formatting string
    """
    attr_type, limit, fill = FMT_REGEX.match(token).groups()
    limit = max(int(limit[1:]), len(attr_type)) if limit else max_lengths[attr_type]
    if attr_type == 'stats':
        # (24|0|0|0 profiles)
        print_stats_token(max_lengths, minor_version, stat_len)
    elif attr_type == 'changes':
        # +++---
        print_changes_token(max_lengths, minor_version)
    else:
        # "91373c43",  "Bump version and changelog to 0.16.8"
        print_other_formatting_string(
            fmt_string, minor_version, attr_type, limit, value_fill=fill or ' '
        )


def print_changes_token(max_lengths, minor_version):
    """Prints information about changes in the minor version, i.e. optimizations and degradations.

    The example of changes token is: "+++---"

    :param dict max_lengths: dictionary mapping the maximal lengths of each value corresponding to
        column of the formatting token
    :param MinorVersionInfo minor_version: MinorVersionInfo objects
    """
    degradations = store.load_degradation_list_for(
        pcs.get_object_directory(), minor_version.checksum
    )
    change_string = perun_log.change_counts_to_string(
        perun_log.count_degradations_per_group(degradations),
        width=max_lengths['changes']
    )
    perun_log.info(change_string, end='')


def print_stats_token(max_lengths, minor_version, stat_length):
    """Prints the statistic of profiles for the given minor versions.

    The example of stats token is: "(24|0|0|0 profiles)"

    :param dict max_lengths: dictionary mapping the maximal lengths of each value corresponding to
        column of the formatting token
    :param MinorVersionInfo minor_version: MinorVersionInfo objects
    :param int stat_length: the whole length of the formatting header
    """
    tracked_profiles = index.get_profile_number_for_minor(
        pcs.get_object_directory(), minor_version.checksum
    )
    if tracked_profiles['all']:
        perun_log.info(perun_log.in_color("{:{}}".format(
            tracked_profiles['all'], max_lengths['all']
        ), TEXT_EMPH_COLOUR, TEXT_ATTRS), end='')

        # Print the coloured numbers
        for profile_type in SUPPORTED_PROFILE_TYPES:
            perun_log.info("{}{}".format(
                perun_log.in_color(PROFILE_DELIMITER, HEADER_SLASH_COLOUR),
                perun_log.in_color("{:{}}".format(
                    tracked_profiles[profile_type], max_lengths[profile_type]
                ), PROFILE_TYPE_COLOURS[profile_type])
            ), end='')

        perun_log.info(
            perun_log.in_color(
                " profiles", HEADER_INFO_COLOUR, TEXT_ATTRS
            ), end=''
        )
    else:
        perun_log.info(
            perun_log.in_color(
                '--no--profiles--'.center(stat_length), TEXT_WARN_COLOUR, TEXT_ATTRS
            ), end=''
        )


def print_shortlog_profile_list_header(fmt_tokens, max_lengths):
    """Prints the header of the output of the minor version information

    The example of shortlog header is:

    checksum ( a|m|x|t profiles)                  desc                        changes

    :param list fmt_tokens: list of formatting tokens
    :param dict max_lengths: dictionary of maximal values of columns corresponding to the tokens
    """
    for (token_type, token) in fmt_tokens:
        if token_type == 'fmt_string':
            attr_type, limit, _ = FMT_REGEX.match(token).groups()
            if attr_type == 'stats':
                print_shortlog_stats_header(max_lengths)
            else:
                limit = adjust_limit(limit, attr_type, max_lengths)
                token_string = attr_type.center(limit, ' ')
                cprint(token_string, 'white', HEADER_ATTRS)
        else:
            # Print the rest (non token stuff)
            cprint(token, 'white', HEADER_ATTRS)
    perun_log.info("")


def print_shortlog_stats_header(max_lengths):
    """Prints header for the stats, adjusted according to the lengths of each profile info

    The stats header is in form of: a|m|x|t profiles

    :param dict max_lengths: dictionary that computes the maximal lengths of each column
    """
    slash = perun_log.in_color(PROFILE_DELIMITER, HEADER_SLASH_COLOUR, HEADER_ATTRS)
    end_msg = perun_log.in_color(' profiles', HEADER_SLASH_COLOUR, HEADER_ATTRS)
    perun_log.info(perun_log.in_color("{0}{4}{1}{4}{2}{4}{3}{5}".format(
        perun_log.in_color(
            'a'.rjust(max_lengths['all']), HEADER_COMMIT_COLOUR, HEADER_ATTRS
        ),
        perun_log.in_color(
            'm'.rjust(max_lengths['memory']),
            PROFILE_TYPE_COLOURS['memory'], HEADER_ATTRS
        ),
        perun_log.in_color(
            'x'.rjust(max_lengths['mixed']),
            PROFILE_TYPE_COLOURS['mixed'], HEADER_ATTRS),
        perun_log.in_color(
            't'.rjust(max_lengths['time']),
            PROFILE_TYPE_COLOURS['time'], HEADER_ATTRS),
        slash,
        end_msg
    ), HEADER_SLASH_COLOUR, HEADER_ATTRS), end='')


def print_minor_version_info(head_minor_version, indent=0):
    """Prints the information about given minor version both in log and status

    In particular, it lists the author, email, date, parents and description.
    Example of minor version info is:

    Author: Tomas Fiedor <ifiedortom@fit.vutbr.cz> 2021-02-18 12:21:35
    Parent: 7b5ec3496c0c4b5b048950ed230e7084e511938c

    Refactor commands and cli_helpers

    :param MinorVersion head_minor_version: identification of the commit (preferably sha1)
    :param int indent: indent of the description part
    """
    perun_log.info("Author: {0.author} <{0.email}> {0.date}".format(head_minor_version))
    for parent in head_minor_version.parents:
        perun_log.info("Parent: {}".format(parent))
    perun_log.info("")
    indented_desc = '\n'.join(map(
        lambda line: ' '*(indent*4) + line, head_minor_version.desc.split('\n')
    ))
    perun_log.info(indented_desc)


def print_other_formatting_string(fmt_string, info_object, info_attr, size_limit,
                                  colour='white', value_fill=' '):
    """Prints the token from the fmt_string, according to the values stored in info_object

    info_attr is one of the tokens from fmt_string, which is extracted from the info_object,
    that stores the real value. This value is then output to stdout with colours, fills,
    and is trimmed to the given size.

    :param str fmt_string: formatting string for the given token
    :param object info_object: object with stored information (ProfileInfo or MinorVersion)
    :param int size_limit: will limit the output of the value of the info_object to this size
    :param str info_attr: attribute we are looking up in the info_object
    :param str colour: default colour of the formatting token that will be printed out
    :param char value_fill: will fill the string with this
    """
    # Check if encountered incorrect token in the formatting string
    if not hasattr(info_object, info_attr):
        perun_log.error(
            "invalid formatting string '{}': object does not contain '{}' attribute".format(
                fmt_string, info_attr
            )
        )

    # Obtain the value for the printing
    raw_value = getattr(info_object, info_attr)
    info_value = raw_value[:size_limit].ljust(size_limit, value_fill)

    # Print the actual token
    if info_attr == 'type':
        cprint("[{}]".format(info_value), PROFILE_TYPE_COLOURS[raw_value])
    else:
        cprint(info_value, colour)


def calculate_maximal_lengths_for_stats(obj_list, stat_function, stat_header=""):
    """For given object lists and stat_function compute maximal lengths of the stats

    :param list obj_list: list of object, for which the stat function will be applied
    :param function stat_function: function returning the dictionary of keys
    :param str stat_header: header of the stats
    :return: dictionary of maximal lenghts for various stats
    """
    maxima = collections.defaultdict(int)
    for obj in obj_list:
        object_stats = stat_function(obj)
        for key in object_stats.keys():
            maxima[key] = max(len(stat_header), maxima[key], len(str(object_stats[key])))
    return maxima


def calculate_maximal_lengths_for_object_list(object_list, valid_attributes):
    """For given object list, will calculate the maximal sizes for its values for table view.

    :param list object_list: list of objects (e.g. ProfileInfo or MinorVersion) information
    :param list valid_attributes: list of valid attributes of objects from list
    :returns dict: dictionary with maximal lengths for profiles
    """
    # Measure the maxima for the lengths of the object info
    max_lengths = collections.defaultdict(int)
    for object_info in object_list:
        for attr in valid_attributes:
            if hasattr(object_info, attr):
                max_lengths[attr] \
                    = max(len(attr), max_lengths[attr], len(str(getattr(object_info, attr))))
    return max_lengths


def print_status_profile_list(profiles, max_lengths, short, list_type='tracked'):
    """Prints list of profiles and counts per type of tracked/untracked profiles.

    Prints the list of profiles, trims the sizes of each information according to the
    computed maximal lengths If the output is short, the list itself is not printed,
    just the information about counts. Tracked and untracked differs in colours.
    The example of output is as follows:

    17 untracked profiles (6 memory, 8 mixed, 3 time):

    ═════════════════════════════════════════════════════════════════════════▣
      id  ┃   type   ┃                         source                        ┃
    ═════════════════════════════════════════════════════════════════════════▣
      0@p ┃ [time  ] ┃ time-example.perf                                     ┃
    ═════════════════════════════════════════════════════════════════════════▣
      1@p ┃ [mixed ] ┃ complexity-quicksort-[_]-[_]-2018-03-26-13-52-58.perf ┃
      2@p ┃ [memory] ┃ memory-mct-[_]-[_]-2018-03-26-12-16-36.perf           ┃
      3@p ┃ [mixed ] ┃ complexity-gif2bmp-[_]-[_]-2018-03-26-12-12-15.perf   ┃
      4@p ┃ [memory] ┃ memory-mct-[_]-[_]-2018-03-26-10-07-47.perf           ┃
      5@p ┃ [mixed ] ┃ complexity-quicksort-[_]-[_]-2018-03-22-17-04-52.perf ┃
    ═════════════════════════════════════════════════════════════════════════▣

    :param list profiles: list of profiles of ProfileInfo objects
    :param dict max_lengths: dictionary with maximal sizes for the output of profiles
    :param bool short: true if the output should be short
    :param str list_type: type of the profile list (either untracked or tracked)
    """
    # Sort the profiles w.r.t time of creation
    list_config = ProfileListConfig(list_type, short, profiles)
    profile.sort_profiles(profiles)

    # Print with padding
    profile_numbers = calculate_profile_numbers_per_type(profiles)
    print_profile_numbers(profile_numbers, list_type, list_config.ending)

    # Skip empty profile list or shortlist
    if not list_config.list_len or short:
        return

    # Load formating string for profile
    fmt_string = perun_config.lookup_key_recursively('format.status')
    fmt_tokens = perun_log.scan_formatting_string(
        fmt_string, {}, default_fmt_callback=lambda token: "%" + token + "%"
    )
    adjust_header_length(fmt_tokens, max_lengths, list_config)

    # Print header (2 is padding for id)
    print_status_profile_list_header(fmt_tokens, list_config, max_lengths)

    # Print profiles
    print_status_profiles(fmt_tokens, list_config, max_lengths, fmt_string, profiles)


def print_status_profiles(fmt_tokens, list_config, max_lengths, fmt_string, profiles):
    """Prints each of the profiles, formatted according to the formatting string

    The first profile, and every fifth profile is separated by horizontal line.

      0@p ┃ [time  ] ┃ time-example.perf                                     ┃
    ═════════════════════════════════════════════════════════════════════════▣
      1@p ┃ [mixed ] ┃ complexity-quicksort-[_]-[_]-2018-03-26-13-52-58.perf ┃
      2@p ┃ [memory] ┃ memory-mct-[_]-[_]-2018-03-26-12-16-36.perf           ┃
      3@p ┃ [mixed ] ┃ complexity-gif2bmp-[_]-[_]-2018-03-26-12-12-15.perf   ┃
      4@p ┃ [memory] ┃ memory-mct-[_]-[_]-2018-03-26-10-07-47.perf           ┃
      5@p ┃ [mixed ] ┃ complexity-quicksort-[_]-[_]-2018-03-22-17-04-52.perf ┃
    ═════════════════════════════════════════════════════════════════════════▣

    :param list fmt_tokens: list of pairs of (token type, token)
    :param ProfileInfoConfig list_config: configuration of the output profile list
    :param dict max_lengths: mapping of token types ot their maximal lengths for alignment
    :param str fmt_string: formatting string for error handling
    :param list profiles: list of profiles
    """
    for profile_no, profile_info in enumerate(profiles):
        perun_log.info(" ", end='')
        cprint("{}@{}".format(profile_no, list_config.id_char).rjust(list_config.id_width + 2, ' '),
               list_config.colour)
        perun_log.info(" ", end='')
        for (token_type, token) in fmt_tokens:
            if token_type == 'fmt_string':
                attr_type, limit, fill = FMT_REGEX.match(token).groups()
                limit = adjust_limit(limit, attr_type, max_lengths)
                print_other_formatting_string(
                    fmt_string, profile_info, attr_type, limit,
                    colour=list_config.colour, value_fill=fill or ' '
                )
            else:
                cprint(token, list_config.colour)
        perun_log.info("")
        if profile_no % 5 == 0 or profile_no == list_config.list_len - 1:
            cprintln("\u2550" * list_config.header_width + "\u25A3", list_config.colour)


def print_status_profile_list_header(fmt_tokens, list_config, max_lengths):
    """Prints the header of the profile list, printing each token aligned by maximal lengths.

    The example of header is as follows:

    ═════════════════════════════════════════════════════════════════════════▣
      id  ┃   type   ┃                         source                        ┃
    ═════════════════════════════════════════════════════════════════════════▣

    :param list fmt_tokens: list of pairs of (token type, token)
    :param ProfileInfoConfig list_config: configuration of the output profile list
    :param dict max_lengths: mapping of token types ot their maximal lengths for alignment
    """
    cprintln("\u2550" * list_config.header_width + "\u25A3", list_config.colour)
    perun_log.info(" ", end='')
    cprint("id".center(list_config.id_width + 2, ' '), list_config.colour)
    perun_log.info(" ", end='')
    for (token_type, token) in fmt_tokens:
        if token_type == 'fmt_string':
            attr_type, limit, _ = FMT_REGEX.match(token).groups()
            limit = adjust_limit(limit, attr_type, max_lengths, (2 if attr_type == 'type' else 0))
            token_string = attr_type.center(limit, ' ')
            cprint(token_string, list_config.colour)
        else:
            # Print the rest (non token stuff)
            cprint(token, list_config.colour)
    perun_log.info("")
    cprintln("\u2550" * list_config.header_width + "\u25A3", list_config.colour)


def adjust_header_length(fmt_tokens, max_lengths, list_config):
    """Ajdust the length of the header stored in configuration

    :param list fmt_tokens: list of tokens
    :param dict max_lengths: maximal lengths of individual tokens
    :param ProfileListConfig list_config: configuration of the printed list
    """
    # the magic constant three is for 3 border columns
    for (token_type, token) in fmt_tokens:
        if token_type == 'fmt_string':
            attr_type, limit, _ = FMT_REGEX.match(token).groups()
            limit = adjust_limit(limit, attr_type, max_lengths, (2 if attr_type == 'type' else 0))
            list_config.header_width += limit
        else:
            list_config.header_width += len(token)


def get_untracked_profiles():
    """Returns list untracked profiles, currently residing in the .perun/jobs directory.

    :returns list: list of ProfileInfo parsed from .perun/jobs directory
    """
    saved_entries = []
    profile_list = []
    # First load untracked files from the ./jobs/ directory
    untracked_list = sorted(
        list(filter(lambda f: f.endswith('perf'), os.listdir(pcs.get_job_directory())))
    )

    # Second load registered files in job index
    job_index = pcs.get_job_index()
    index.touch_index(job_index)
    with open(job_index, 'rb+') as index_handle:
        pending_index_entries = list(index.walk_index(index_handle))

    # Iterate through the index and check if it is still in the ./jobs directory
    # In case it is still valid, we extract it into ProfileInfo and remove it from the list
    #   of files in ./jobs directory
    for index_entry in pending_index_entries:
        if index_entry.path in untracked_list:
            real_path = os.path.join(pcs.get_job_directory(), index_entry.path)
            index_info = {
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
            profile_info = profile.ProfileInfo(
                index_entry.path, real_path, index_entry.time, index_info, is_raw_profile=True
            )
            profile_list.append(profile_info)
            saved_entries.append(index_entry)
            untracked_list.remove(index_entry.path)

    # Now for every non-registered file in the ./jobs/ directory, we load the profile,
    #   extract the info and register it in the index
    for untracked_path in untracked_list:
        real_path = os.path.join(pcs.get_job_directory(), untracked_path)
        time = timestamp.timestamp_to_str(os.stat(real_path).st_mtime)

        # Load the data from JSON, which contains additional information about profile
        loaded_profile = store.load_profile_from_file(real_path, is_raw_profile=True)
        registered_checksum = store.compute_checksum(real_path.encode('utf-8'))

        # Update the list of profiles and counters of types
        profile_info = profile.ProfileInfo(
            untracked_path, real_path, time, loaded_profile, is_raw_profile=True
        )
        untracked_entry = index.INDEX_ENTRY_CONSTRUCTORS[index.INDEX_VERSION - 1](
            time, registered_checksum, untracked_path, -1, loaded_profile
        )

        profile_list.append(profile_info)
        saved_entries.append(untracked_entry)

    # We write all of the entries that are valid in the ./jobs/ directory in the index
    index.write_list_of_entries(job_index, saved_entries)

    return profile_list


@perun_log.paged_function(paging_switch=turn_off_paging_wrt_config('status'))
def status(short=False, **_):
    """Prints the status of performance control system

    :param bool short: true if the output should be short (i.e. without some information)
    """
    # Obtain both of the heads
    major_head = vcs.get_head_major_version()
    minor_head = vcs.get_minor_head()

    # Print the status of major head.
    perun_log.info("On major version {} ".format(
        perun_log.in_color(major_head, TEXT_EMPH_COLOUR, TEXT_ATTRS)
    ), end='')

    # Print the index of the current head
    perun_log.info("(minor version: {})".format(
        perun_log.in_color(minor_head, TEXT_EMPH_COLOUR, TEXT_ATTRS)
    ))

    # Print in long format, the additional information about head commit, by default print
    if not short:
        perun_log.info("")
        minor_version = vcs.get_minor_version_info(minor_head)
        print_minor_version_info(minor_version)

    # Print profiles
    minor_version_profiles = profile.load_list_for_minor_version(minor_head)
    untracked_profiles = get_untracked_profiles()
    maxs = calculate_maximal_lengths_for_object_list(
        minor_version_profiles + untracked_profiles, profile.ProfileInfo.valid_attributes
    )
    print_status_profile_list(minor_version_profiles, maxs, short)
    if not short:
        perun_log.info("")
    print_status_profile_list(untracked_profiles, maxs, short, 'untracked')

    # Print degradation info
    degradation_list = store.load_degradation_list_for(
        pcs.get_object_directory(), minor_head
    )
    if not short:
        perun_log.info("")
    perun_log.print_short_summary_of_degradations(degradation_list)
    if not short:
        perun_log.info("")
        perun_log.print_list_of_degradations(degradation_list)


@vcs.lookup_minor_version
def load_profile_from_args(profile_name, minor_version):
    """
    :param Profile profile_name: profile that will be stored for the minor version
    :param str minor_version: SHA-1 representation of the minor version
    :returns dict: loaded profile represented as dictionary
    """
    # If the profile is in raw form
    if not store.is_sha1(profile_name):
        _, minor_index_file = store.split_object_name(pcs.get_object_directory(), minor_version)
        # If there is nothing at all in the index, since it is not even created ;)
        #   we returning nothing otherwise we lookup entries in index
        if not os.path.exists(minor_index_file):
            return None
        with open(minor_index_file, 'rb') as minor_handle:
            lookup_pred = lambda entry: entry.path == profile_name
            profiles = index.lookup_all_entries_within_index(minor_handle, lookup_pred)
    else:
        profiles = [profile_name]

    # If there are more profiles we should chose
    if not profiles:
        return None
    chosen_profile = profiles[0]

    # Peek the type if the profile is correct and load the json
    _, profile_name = store.split_object_name(pcs.get_object_directory(), chosen_profile.checksum)
    loaded_profile = store.load_profile_from_file(profile_name, False)

    return loaded_profile


def print_temp_files(root, **kwargs):
    """Print the temporary files in the root directory.

    :param str root: the path to the directory that should be listed
    :param kwargs: additional parameters such as sorting, output formatting etc.
    """
    # Try to load the files in the root directory
    try:
        temp.synchronize_index()
        tmp_files = temp.list_all_temps_with_details(root)
    except InvalidTempPathException as exc:
        perun_log.error(str(exc))

    # Filter the files by protection level if it is set to show only certain group
    if kwargs['filter_protection'] != 'all':
        tmp_files = [(name, level, size) for name, level, size in tmp_files
                     if level == kwargs['filter_protection']]
    # If there are no files then abort the output
    if not tmp_files:
        perun_log.info('== No results for the given parameters in the .perun/tmp/ directory ==')
        return

    # First sort by the name
    tmp_files.sort(key=itemgetter(0))
    # Now apply 'sort-by' if it differs from name:
    if kwargs['sort_by'] != 'name':
        sort_map = temp.SORT_ATTR_MAP[kwargs['sort_by']]
        tmp_files.sort(key=itemgetter(sort_map['pos']), reverse=sort_map['reverse'])

    # Print the total files size if needed
    _print_total_size(sum(size for _, _, size in tmp_files), not kwargs['no_total_size'])
    # Print the file records
    print_formatted_temp_files(
        tmp_files, not kwargs['no_file_size'], not kwargs['no_protection_level']
    )


def print_formatted_temp_files(records, show_size, show_protection):
    """Format and print temporary file records as:
    size | protection level | path from tmp/ directory

    :param list records: the list of temporary file records as tuple (size, protection, path)
    :param bool show_size: flag indicating whether size for each file should be shown
    :param bool show_protection: if set to True, show the protection level of each file
    """
    # Absolute path might be a bit too long, we remove the path component to the tmp/ directory
    prefix = len(pcs.get_tmp_directory()) + 1
    for file_name, protection, size in records:
        # Print the size of each file
        if show_size:
            perun_log.info('{}'.format(
                perun_log.in_color(utils.format_file_size(size), TEXT_EMPH_COLOUR)
            ), end=perun_log.in_color(' | ', TEXT_WARN_COLOUR))
        # Print the protection level of each file
        if show_protection:
            if protection == temp.UNPROTECTED:
                perun_log.info('{}'.format(temp.UNPROTECTED),
                      end=perun_log.in_color(' | ', TEXT_WARN_COLOUR))
            else:
                perun_log.info('{}  '.format(perun_log.in_color(temp.PROTECTED, TEXT_WARN_COLOUR)),
                      end=perun_log.in_color(' | ', TEXT_WARN_COLOUR))

        # Print the file path, emphasize the directory to make it a bit more readable
        file_name = file_name[prefix:]
        file_dir = os.path.dirname(file_name)
        if file_dir:
            file_dir += os.sep
            perun_log.info('{}'.format(perun_log.in_color(file_dir, TEXT_EMPH_COLOUR)), end='')
        perun_log.info('{}'.format(os.path.basename(file_name)))


def delete_temps(path, ignore_protected, force, **kwargs):
    """Delete the temporary file(s) identified by the path. The path can be either file (= delete
    only the file) or directory (= delete files in the directory or the whole directory).

    :param str path: the path to the target file or directory
    :param bool ignore_protected: if True, protected files are ignored and not deleted, otherwise
                                  deletion process is aborted and exception is raised
    :param bool force: if True, delete also protected files
    :param kwargs: additional parameters
    """
    try:
        # Determine if path is file or directory and call the correct functions for that
        if temp.exists_temp_file(path):
            temp.delete_temp_file(path, ignore_protected, force)
        elif temp.exists_temp_dir(path):
            # We might delete only files or files + empty directories
            if kwargs['keep_directories']:
                temp.delete_all_temps(path, ignore_protected, force)
            else:
                temp.delete_temp_dir(path, ignore_protected, force)
        # The supplied path does not exist, inform the user so they can correct the path
        else:
            perun_log.warn("The supplied path '{}' does not exist, no files deleted"
                           .format(temp.temp_path(path)))
    except (InvalidTempPathException, ProtectedTempException) as exc:
        # Invalid path or protected files encountered
        perun_log.error(str(exc))


def list_stat_objects(mode, **kwargs):
    """ Prints the stat files or versions (based on the mode) in the '.perun/stats' directory.

    The default output formats are:
    'file size | minor version | file name' for files
    'directory size | minor version | files count' for versions
    However, the parameters in 'kwargs' can alter the format (hide certain properties etc.)

    :param str mode: the requested list mode: 'versions' or 'files'
    :param kwargs: additional parameters from the CLI such as coloring the output, sorting etc.
    """
    versions = stats.list_stat_versions(kwargs['from_minor'], kwargs['top'])
    versions = [(version, stats.list_stats_for_minor(version)) for version, _ in versions]

    # Abort the whole output if we have no versions
    if not versions:
        perun_log.info('== No results for the given parameters in the .perun/stats/ directory ==')
        return

    if mode == 'versions':
        # We need to print the versions, aggregate the files and their sizes
        results = [(sum(size for _, size in files), version, len(files))
                   for version, files in versions]
        properties = [
            (not kwargs['no_dir_size'], True),
            (True, False),
            (not kwargs['no_file_count'], False)
        ]
    else:
        # We need to print the files, create separate record for each file
        results = []
        for version, files in versions:
            # A bit more complicated since we also need records for empty version directories
            if files:
                results.extend([(size, version, file) for file, size in files])
            else:
                results.append((None, version, '-= No stats file =-'))
        # results = [(size, version, file) for version, files in versions for file, size in files]
        properties = [
            (not kwargs['no_file_size'], True),
            (not kwargs['no_minor'], False),
            (True, False)
        ]

    # Separate the results with no files since they cannot be properly sorted but still need
    # to be printed
    record_size = itemgetter(0)
    valid_results, empty_results = utils.partition_list(
        results, lambda item: record_size(item) is not None
    )

    # Print the total size if needed
    _print_total_size(
        sum(record_size(record) for record in valid_results), not kwargs['no_total_size']
    )
    # Sort by size if needed
    if kwargs['sort_by_size']:
        if mode == 'versions':
            results.sort(key=record_size, reverse=True)
        else:
            valid_results.sort(key=record_size, reverse=True)
            results = valid_results + empty_results

    # Format the size so that is's suitable for output
    results = [(utils.format_file_size(size), version, file) for size, version, file in results]
    # Print all the results
    _print_stat_objects(results, properties)


def _print_total_size(total_size, enabled):
    """ Prints the formatted total size of all displayed results.

    :param int total_size: the total size in bytes
    :param bool enabled: a flag describing if the total size should be displayed at all
    """
    if enabled:
        total_size = utils.format_file_size(total_size)
        perun_log.info('Total size of all the displayed files / directories: {}'.format(
            perun_log.in_color(total_size, TEXT_EMPH_COLOUR))
        )


def _print_stat_objects(stats_objects, properties):
    """ Prints stats objects (files, versions, other iterable etc.) in a general way.

    The stats object should be a list of items to print, where each item consists of some
    properties that may or may not be printed / colored, as set by the 'properties'.

    The 'properties' should be a list of tuples (print, colored) that define if the corresponding
    property (item property on a matching position) should be printed and colored.

    :param list stats_objects: list of stat objects to print
    :param list properties: list of settings for item properties / parts
    """
    # Iterate all the stats objects and parts of each object
    for item in stats_objects:
        record = ''
        for pos, prop in enumerate(item):
            # Check if we should print the property and if it should be colored
            show_property, colored = properties[pos]
            if show_property:
                # Add the delimiter if the record already has some properties to print
                if record:
                    record += perun_log.in_color(' | ', TEXT_WARN_COLOUR)
                record += perun_log.in_color(str(prop), TEXT_EMPH_COLOUR) if colored else str(prop)
        perun_log.info(record)


def delete_stats_file(name, in_minor, keep_directory):
    """ Deletes stats file in either a specific minor version or across all the versions in the
    stats directory.

    :param str name: the file name
    :param str in_minor: the minor version identification or '.' for global deletion
    :param bool keep_directory: possibly empty version directory after the deletion will be kept
                                in the stats directory if set to True.
    """
    if in_minor == '.':
        stats.delete_stats_file_across_versions(name, keep_directory)
    else:
        stats.delete_stats_file(name, in_minor, keep_directory)


def delete_stats_minor(minor, keep_directory):
    """ Deletes the minor version directory in the stats directory.

    :param str minor: the minor version identification
    :param bool keep_directory: the empty version directory will be kept
                                in the stats directory if True
    """
    stats.delete_version_dirs([minor], False, keep_directory)


def delete_stats_all(keep_directory):
    """ Deletes all items in the stats directory.

    :param bool keep_directory: the empty version directories will be kept
                                in the stats directory if True
    """
    stats.reset_stats(keep_directory)


def clean_stats(keep_custom, keep_empty):
    """ Cleans the stats directory, that is:
    - synchronizes the internal state of the stats directory, i.e. the index file
    - attempts to delete all distinguishable custom files and directories (some manually created or
      custom objects may not be identified if they have the correct format, e.g. version directory
      that was created manually but has a valid version counterpart in the VCS, manually created
      files in the version directory etc.)
    - deletes all empty version directories in the stats directory

    :param bool keep_custom: the custom objects are kept in the stats directory if set to True
    :param bool keep_empty: the empty version directories are not deleted if set to True
    """
    stats.clean_stats(keep_custom, keep_empty)


def sync_stats():
    """ Synchronize the stats directory contents with the index file - delete minor version records
    for deleted versions and add missing records for existing versions.
    """
    stats.synchronize_index()


def sync_temps():
    """Synchronizes the internal state of the index file so that it corresponds to some possible
    manual changes in the directory by the user.
    """
    temp.synchronize_index()
