"""Perun can be run from the command line (if correctly installed) using the
command interface inspired by git.

The Command Line Interface is implemented using the Click_ library, which
allows both effective definition of new commands and finer parsing of the
command line arguments. The intefrace can be broken into several groups:

    1. **Core commands**: namely ``init``, ``config``, ``add``, ``rm``,
    ``status``, ``log``, ``run`` commands (which consists of commands ``run
    job`` and ``run matrix``) and ``check`` commands (which consists of
    commands ``check all``, ``check head`` and ``check profiles``).
    These commands automate the creation of performance profiles, detection
    of performance degradation and are used for management of the Perun
    repository. Refer to :ref:`cli-main-ref` for details about commands.

    2. **Collect commands**: group of ``collect COLLECTOR`` commands, where
    ``COLLECTOR`` stands for one of the collector of :ref:`collectors-list`.
    Each ``COLLECTOR`` has its own API, refer to :ref:`cli-collect-units-ref`
    for thorough description of API of individual collectors.

    3. **Postprocessby commands**: group of ``postprocessby POSTPROCESSOR``
    commands, where ``POSTPROCESSOR`` stands for one of the postprocessor of
    :ref:`postprocessors-list`. Each ``POSTPROCESSOR`` has its own API, refer
    to :ref:`cli-postprocess-units-ref` for thorough description of API of
    individual postprocessors.

    4. **View commands**: group of ``view VISUALIZATION`` commands, where
    ``VISUALIZATION`` stands for one of the visualizer of :ref:`views-list`.
    Each ``VISUALIZATION`` has its own API, refer to :ref:`cli-views-units-ref`
    for thorough description of API of individual views.

    5. **Utility commands**: group of commands used for developing Perun
    or for maintenance of the Perun instances. Currently this group contains
    ``create`` command for faster creation of new modules.

Graphical User Interface is currently in development and hopefully will extend
the flexibility of Perun's usage.

.. _Click: http://click.pocoo.org/5/
"""

import os
import pkgutil
import sys

import click

import perun.collect
import perun.postprocess
import perun.view

import perun.fuzz.factory as fuzz
import perun.logic.commands as commands
import perun.logic.pcs as pcs
import perun.logic.config as perun_config
import perun.profile.helpers as profiles
import perun.utils as utils
import perun.utils.helpers as helpers
import perun.utils.cli_helpers as cli_helpers
import perun.utils.log as perun_log
import perun.view
from perun.collect.trace.optimizations.structs import Pipeline, Optimizations, CallGraphTypes
from perun.collect.trace.optimizations.structs import Parameters
import perun.cli_groups.check_cli as check_cli
import perun.cli_groups.config_cli as config_cli
import perun.cli_groups.run_cli as run_cli
import perun.cli_groups.utils_cli as utils_cli

from perun.utils.exceptions import UnsupportedModuleException, UnsupportedModuleFunctionException, \
    NotPerunRepositoryException, IncorrectProfileFormatException, EntryNotFoundException, \
    MissingConfigSectionException, ExternalEditorErrorException
from perun.utils.structs import Executable


__author__ = 'Tomas Fiedor'
DEV_MODE = False


@click.group()
@click.option('--dev-mode', '-d', default=False, is_flag=True,
              help='Suppresses the catching of all exceptions from the CLI and generating of the '
                   'dump.')
@click.option('--no-pager', default=False, is_flag=True,
              help='Disables the paging of the long standard output (currently'
              ' affects only ``status`` and ``log`` outputs). See '
              ':ckey:`paging` to change the default paging strategy.')
@click.option('--no-color', '-nc', default=False, is_flag=True,
              help='Disables the colored output.')
@click.option('--verbose', '-v', count=True, default=0,
              help='Increases the verbosity of the standard output. Verbosity '
              'is incremental, and each level increases the extent of output.')
@click.option('--version', help='Prints the current version of Perun.',
              is_eager=True, is_flag=True, default=False,
              callback=cli_helpers.print_version)
@click.option('--metrics', '-m', type=(str, str), default=["", ""],
              callback=cli_helpers.configure_metrics,
              help='Enables the collection of metrics into the given temp file'
                   '(first argument) under the supplied ID (second argument).')
def cli(dev_mode=False, no_color=False, verbose=0, no_pager=False, **_):
    """Perun is an open source light-weight Performance Versioning System.

    In order to initialize Perun in current directory run the following::

        perun init

    This initializes basic structure in ``.perun`` directory, together with
    possible reinitialization of git repository in current directory. In order
    to set basic configuration and define jobs for your project run the
    following::

        perun config --edit

    This opens editor and allows you to specify configuration of your project
    and choose set of collectors for capturing resources. See :doc:`jobs` and
    :doc:`config` for more details.

    In order to generate first set of profiles for your current ``HEAD`` run the
    following::

        perun run matrix
    """
    # by default the pager is suppressed, and only calling it from the CLI enables it,
    # through --no-pager set by default to False you enable the paging
    global DEV_MODE
    DEV_MODE = dev_mode
    perun_log.SUPPRESS_PAGING = no_pager
    perun_log.COLOR_OUTPUT = not no_color

    # set the verbosity level of the log
    if perun_log.VERBOSITY < verbose:
        perun_log.VERBOSITY = verbose


def configure_local_perun(perun_path):
    """Configures the local perun repository with the interactive help of the user

    :param str perun_path: destination path of the perun repository
    :raises: ExternalEditorErrorException: when underlying editor makes any mistake
    """
    editor = perun_config.lookup_key_recursively('general.editor')
    local_config_file = os.path.join(perun_path, '.perun', 'local.yml')
    utils.run_external_command([editor, local_config_file])


@cli.command()
@click.argument('dst', required=False, default=os.getcwd(), metavar='<path>')
@click.option('--vcs-type', metavar='<type>', default='git',
              type=click.Choice(utils.get_supported_module_names('vcs')),
              help="In parallel to initialization of Perun, initialize the vcs"
              " of <type> as well (by default ``git``).")
@click.option('--vcs-path', metavar='<path>',
              help="Sets the destination of wrapped vcs initialization at "
              "<path>.")
@click.option('--vcs-param', nargs=2, metavar='<param>', multiple=True,
              callback=cli_helpers.vcs_parameter_callback,
              help="Passes additional (key, value) parameter to initialization"
              " of version control system, e.g. ``separate-git-dir dir``.")
@click.option('--vcs-flag', nargs=1, metavar='<flag>', multiple=True,
              callback=cli_helpers.vcs_parameter_callback,
              help="Passes additional flag to a initialization of version "
              "control system, e.g. ``bare``.")
@click.option('--configure', '-c', is_flag=True, default=False,
              help='After successful initialization of both systems, opens '
              'the local configuration using the :ckey:`editor` set in shared '
              'config.')
@click.option('--config-template', '-t', type=click.STRING, default='master',
              help='States the configuration template that will be used for initialization of local'
                   ' configuration. See :ref:`config-templates` for more details about predefined '
                   ' configurations.')
def init(dst, configure, config_template, **kwargs):
    """Initializes performance versioning system at the destination path.

    ``perun init`` command initializes the perun's infrastructure with basic
    file and directory structure inside the ``.perun`` directory. Refer to
    :ref:`internals-overview` for more details about storage of Perun. By
    default following directories are created:

        1. ``.perun/jobs``: storage of performance profiles not yet assigned to
           concrete minor versions.

        2. ``.perun/objects``: storage of packed contents of performance
           profiles and additional informations about minor version of wrapped
           vcs system.

        3. ``.perun/cache``: fast access cache of selected latest unpacked
           profiles

        4. ``.perun/local.yml``: local configuration, storing specification of
           wrapped repository, jobs configuration, etc. Refer to :doc:`config`
           for more details.

    The infrastructure is initialized at <path>. If no <path> is given, then
    current working directory is used instead. In case there already exists a
    performance versioning system, the infrastructure is only reinitialized.

    By default, a control system is initialized as well. This can be changed by
    by setting the ``--vcs-type`` parameter (currently we support ``git`` and
    ``tagit``---a lightweight git-based wrapped based on tags). Additional
    parameters can be passed to the wrapped control system initialization using
    the ``--vcs-params``.
    """
    try:
        commands.init(dst, config_template, **kwargs)

        if configure:
            # Run the interactive configuration of the local perun repository (populating .yml)
            configure_local_perun(dst)
        else:
            msg = "\nIn order to automatically run jobs configure the matrix at:\n"
            msg += "\n" + (" "*4) + ".perun/local.yml\n"
            perun_log.quiet_info(msg)
    except (UnsupportedModuleException, UnsupportedModuleFunctionException) as unsup_module_exp:
        perun_log.error("error while initializing perun: {}".format(str(unsup_module_exp)))
    except PermissionError:
        perun_log.error("writing to shared config 'shared.yml' requires root permissions")
    except (ExternalEditorErrorException, MissingConfigSectionException):
        err_msg = "cannot launch default editor for configuration.\n"
        err_msg += "Please set 'general.editor' key to a valid text editor (e.g. vim)."
        perun_log.error(err_msg)


@cli.command()
@click.argument('profile', required=True, metavar='<profile>', nargs=-1,
                callback=cli_helpers.lookup_added_profile_callback)
@click.option('--minor', '-m', required=False, default=None, metavar='<hash>', is_eager=True,
              callback=cli_helpers.lookup_minor_version_callback,
              help='<profile> will be stored at this minor version (default is HEAD).')
@click.option('--keep-profile', is_flag=True, required=False, default=False,
              help='Keeps the profile in filesystem after registering it in'
              ' Perun storage. Otherwise it is deleted.')
@click.option('--force', '-f', is_flag=True, default=False, required=False,
              help='If set to true, then the profile will be registered in the <hash> minor version'
                   'index, even if its origin <hash> is different. WARNING: This can screw the '
                   'performance history of your project.')
def add(profile, minor, **kwargs):
    """Links profile to concrete minor version storing its content in the
    ``.perun`` dir and registering the profile in internal minor version index.

    In order to link <profile> to given minor version <hash> the following
    steps are executed:

        1. We check in <profile> that its :preg:`origin` key corresponds to
           <hash>. This serves as a check, that we do not assign profiles to
           different minor versions.

        2. The :preg:`origin` is removed and contents of <profile> are
           compresed using `zlib` compression method.

        3. Binary header for the profile is constructed.

        4. Compressed contents are appended to header, and this blob is stored
           in ``.perun/objects`` directory.

        5. New blob is registered in <hash> minor version's index.

        6. Unless ``--keep-profile`` is set. The original profile is deleted.

    If no `<hash>` is specified, then current ``HEAD`` of the wrapped version
    control system is used instead. Massaging of <hash> is taken care of by
    underlying version control system (e.g. git uses ``git rev-parse``).

    <profile> can either be a ``pending tag``, ``pending tag range`` or a
    fullpath. ``Pending tags`` are in form of ``i@p``, where ``i`` stands
    for an index in the pending profile directory (i.e. ``.perun/jobs``)
    and ``@p`` is literal suffix.  The ``pending tag range`` is in form
    of ``i@p-j@p``, where both ``i`` and ``j`` stands for indexes in the
    pending profiles. The ``pending tag range`` then represents all of
    the profiles in the interval <i, j>. When ``i > j``, then no profiles
    will be add; when ``j``; when ``j`` is bigger than the number of
    pending profiles, then all of the non-existing pending profiles will
    be obviously skipped.
    Run ``perun status`` to see the `tag` anotation of pending profiles.
    Tags consider the sorted order as specified by the following option
    :ckey:`format.sort_profiles_by`.

    Example of adding profiles:

    .. code-block:: bash

        $ perun add mybin-memory-input.txt-2017-03-01-16-11-04.perf

    This command adds the profile collected by `memory` collector during
    profiling ``mybin`` command with ``input.txt`` workload on 1st March at
    16:11 to the current ``HEAD``.

    An error is raised if the command is executed outside of range of any
    perun, if <profile> points to incorrect profile (i.e. not w.r.t.
    :ref:`profile-spec`) or <hash> does not point to valid minor version ref.

    See :doc:`internals` for information how perun handles profiles internally.
    """
    try:
        warning_message = 'Warning: Are you sure you want to force the add?' \
                          'This will make the performance history of your project imprecise ' \
                          'or simply wrong.'
        if not kwargs['force'] or click.confirm(warning_message):
            commands.add(profile, minor, **kwargs)
    except (NotPerunRepositoryException, IncorrectProfileFormatException) as exception:
        perun_log.error("error while adding profile:{}".format(str(exception)))


@cli.command('rm')
@click.argument('profile', required=True, metavar='<profile>', nargs=-1,
                callback=cli_helpers.lookup_removed_profile_callback)
@click.option('--minor', '-m', required=False, default=None, metavar='<hash>', is_eager=True,
              callback=cli_helpers.lookup_minor_version_callback,
              help='<profile> will be stored at this minor version (default is HEAD).')
def remove(from_index_generator, from_jobs_generator, minor, **_):
    """Unlinks the profile from the given minor version, keeping the contents
    stored in ``.perun`` directory.

    <profile> is unlinked in the following steps:

        1. <profile> is looked up in the <hash> minor version's internal index.

        2. In case <profile> is not found. An error is raised.

        3. Otherwise, the record corresponding to <hash> is erased. However,
           the original blob is kept in ``.perun/objects``.

    If no `<hash>` is specified, then current ``HEAD`` of the wrapped version
    control system is used instead. Massaging of <hash> is taken care of by
    underlying version control system (e.g. git uses ``git rev-parse``).

    <profile> can either be a ``index tag``, ``pending tag`` or a path specifying
    the profile either in index or in the pending jobs. ``Index tags`` are in form
    of ``i@i``, where ``i`` stands for an index in the minor version's index and
    ``@i`` is literal suffix. Run ``perun status`` to see the `tags` of current
    ``HEAD``'s index. The ``index tag range`` is in form of ``i@i-j@i``, where
    both ``i`` and ``j`` stands for indexes in the minor version's index.
    The ``index tag range`` then represents all of the profiles in the interval
    <i, j>. registered in index. When ``i > j``, then no profiles will be removed;
    when ``j``; when ``j`` is bigger than the number of pending profiles,
    then all of the non-existing pending profiles will be obviously skipped.
    The ``pending tags`` and ``pending tag range`` are defined analogously to
    index tags, except they use the ``p`` character, i.e. ``0@p`` and ``0@p-2@p``
    are valid pending tag and pending tag range. Otherwise one can use the path
    to represent the removed profile. If the path points to existing profile in
    pending jobs (i.e. ``.perun/jobs`` directory) the profile is removed from the
    jobs, otherwise it is looked-up in the index.
    Tags consider the sorted order as specified by the following option
    :ckey:`format.sort_profiles_by`.

    Examples of removing profiles:

    .. code-block:: bash

        $ perun rm 2@i

    This commands removes the third (we index from zero) profile in the index
    of registered profiles of current ``HEAD``.

    An error is raised if the command is executed outside of range of any
    Perun or if <profile> is not found inside the <hash> index.

    See :doc:`internals` for information how perun handles profiles internally.
    """
    try:
        commands.remove_from_index(from_index_generator, minor)
        commands.remove_from_pending(from_jobs_generator)
    except (NotPerunRepositoryException, EntryNotFoundException) as exception:
        perun_log.error("could not remove profiles: {}".format(str(exception)))


@cli.command()
@click.argument('head', required=False, default=None, metavar='<hash>')
@click.option('--short', '-s', is_flag=True, default=False,
              help="Shortens the output of ``log`` to include only most "
              "necessary information.")
def log(head, **kwargs):
    """Shows history of versions and associated profiles.

    Shows the history of the wrapped version control system and all of the
    associated profiles starting from the <hash> point, outputing the
    information about number of profiles, about descriptions ofconcrete minor
    versions, their parents, parents etc.

    If ``perun log --short`` is issued, the shorter version of the ``log`` is
    outputted.

    In no <hash> is given, then HEAD of the version control system is used as a starting point.

    Unless ``perun --no-pager log`` is issued as command, or appropriate
    :ckey:`paging` option is set, the outputs of log will be paged (by
    default using ``less``.

    Refer to :ref:`logs-log` for information how to customize the outputs of
    ``log`` or how to set :ckey:`format.shortlog` in nearest
    configuration.
    """
    try:
        commands.log(head, **kwargs)
    except (NotPerunRepositoryException, UnsupportedModuleException) as exception:
        perun_log.error("could not print the repository history: {}".format(str(exception)))


@cli.command()
@click.option('--short', '-s', required=False, default=False, is_flag=True,
              help="Shortens the output of ``status`` to include only most"
              " necessary information.")
@click.option('--sort-by', '-sb', 'format__sort_profiles_by', nargs=1,
              type=click.Choice(profiles.ProfileInfo.valid_attributes),
              callback=cli_helpers.set_config_option_from_flag(
                  pcs.local_config, 'format.sort_profiles_by', str
              ),
              help="Sets the <key> in the local configuration for sorting profiles. "
                   "Note that after setting the <key> it will be used for sorting which is "
                   "considered in pending and index tags!")
def status(**kwargs):
    """Shows the status of vcs, associated profiles and perun.

    Shows the status of both the nearest perun and wrapped version control
    system. For vcs this outputs e.g. the current minor version ``HEAD``,
    current major version and description of the ``HEAD``.  Moreover ``status``
    prints the lists of tracked and pending (found in ``.perun/jobs``) profiles
    lexicographically sorted along with additional information such as their
    types and creation times.

    Unless ``perun --no-pager status`` is issued as command, or appropriate
    :ckey:`paging` option is set, the outputs of status will be paged (by
    default using ``less``.

    An error is raised if the command is executed outside of range of any
    perun, or configuration misses certain configuration keys
    (namely ``format.status``).

    Profiles (both registered in index and stored in pending directory) are sorted
    according to the :ckey:`format.sort_profiles_by`. The option ``--sort-by``
    sets this key in the local configuration for further usage. This means that
    using the pending or index tags will consider this order.

    Refer to :ref:`logs-status` for information how to customize the outputs of
    ``status`` or how to set :ckey:`format.status` in nearest
    configuration.
    """
    try:
        commands.status(**kwargs)
    except (NotPerunRepositoryException, UnsupportedModuleException,
            MissingConfigSectionException) as exception:
        perun_log.error("could not print status of repository: {}".format(str(exception)))


@cli.group()
@click.argument('profile', required=True, metavar='<profile>',
                callback=cli_helpers.lookup_any_profile_callback)
@click.option('--minor', '-m', nargs=1, default=None, is_eager=True,
              callback=cli_helpers.lookup_minor_version_callback,
              help='Will check the index of different minor version <hash>'
              ' during the profile lookup')
@click.pass_context
def show(ctx, profile, **_):
    """Interprets the given profile using the selected visualization technique.

    Looks up the given profile and interprets it using the selected
    visualization technique. Some of the techniques outputs either to
    terminal (using ``ncurses``) or generates HTML files, which can be
    browseable in the web browser (using ``bokeh`` library). Refer to concrete
    techniques for concrete options and limitations.

    The shown <profile> will be looked up in the following steps:

        1. If <profile> is in form ``i@i`` (i.e, an `index tag`), then `ith`
           record registered in the minor version <hash> index will be shown.

        2. If <profile> is in form ``i@p`` (i.e., an `pending tag`), then
           `ith` profile stored in ``.perun/jobs`` will be shown.

        3. <profile> is looked-up within the minor version <hash> index for a
           match. In case the <profile> is registered there, it will be shown.

        4. <profile> is looked-up within the ``.perun/jobs`` directory. In case
           there is a match, the found profile will be shown.

        5. Otherwise, the directory is walked for any match. Each found match
           is asked for confirmation by user.

    Tags consider the sorted order as specified by the following option
    :ckey:`format.sort_profiles_by`.

    Example 1. The following command will show the first profile registered at
    index of ``HEAD~1`` commit. The resulting graph will contain bars
    representing sum of amounts per each subtype of resources and will be shown
    in the browser::

        perun show -m HEAD~1 0@i bars sum --of 'amount' --per 'subtype' -v

    Example 2. The following command will show the profile at the absolute path
    using in raw JSON format::

        perun show ./echo-time-hello-2017-04-02-13-13-34-12.perf raw

    For a thorough list and description of supported visualization techniques
    refer to :ref:`views-list`.
    """
    ctx.obj = profile


@cli.group()
@click.argument('profile', required=True, metavar='<profile>',
                callback=cli_helpers.lookup_any_profile_callback)
@click.option('--output-filename-template', '-ot', default=None,
              callback=cli_helpers.set_config_option_from_flag(
                  perun_config.runtime, 'format.output_profile_template', str
              ), help='Specifies the template for automatic generation of output filename'
              ' This way the postprocessed file will have a resulting filename w.r.t to this'
              ' parameter. Refer to :ckey:`format.output_profile_template` for more'
              ' details about the format of the template.')
@click.option('--minor', '-m', nargs=1, default=None, is_eager=True,
              callback=cli_helpers.lookup_minor_version_callback,
              help='Will check the index of different minor version <hash>'
              ' during the profile lookup')
@click.pass_context
def postprocessby(ctx, profile, **_):
    """Postprocesses the given stored or pending profile using selected
    postprocessor.

    Runs the single postprocessor unit on given looked-up profile. The
    postprocessed file will be then stored in ``.perun/jobs/`` directory as a
    file, by default with filanem in form of::

        bin-collector-workload-timestamp.perf

    The postprocessed <profile> will be looked up in the following steps:

        1. If <profile> is in form ``i@i`` (i.e, an `index tag`), then `ith`
           record registered in the minor version <hash> index will be
           postprocessed.

        2. If <profile> is in form ``i@p`` (i.e., an `pending tag`), then
           `ith` profile stored in ``.perun/jobs`` will be postprocessed.

        3. <profile> is looked-up within the minor version <hash> index for a
           match. In case the <profile> is registered there, it will be
           postprocessed.

        4. <profile> is looked-up within the ``.perun/jobs`` directory. In case
           there is a match, the found profile will be postprocessed.

        5. Otherwise, the directory is walked for any match. Each found match
           is asked for confirmation by user.

    Tags consider the sorted order as specified by the following option
    :ckey:`format.sort_profiles_by`.

    For checking the associated `tags` to profiles run ``perun status``.

    Example 1. The following command will postprocess the given profile
    stored at given path by normalizer, i.e. for each snapshot, the resources
    will be normalized to the interval <0, 1>::

        perun postprocessby ./echo-time-hello-2017-04-02-13-13-34-12.perf normalizer

    Example 2. The following command will postprocess the second profile stored
    in index of commit preceeding the current head using interval regression
    analysis::

        perun postprocessby -m HEAD~1 1@i regression-analysis --method=interval

    For a thorough list and description of supported postprocessors refer to
    :ref:`postprocessors-list`. For a more subtle running of profiling jobs and
    more complex configuration consult either ``perun run matrix --help`` or
    ``perun run job --help``.
    """
    ctx.obj = profile


@cli.group()
@click.option('--profile-name', '-pn', nargs=1, required=False, multiple=False, type=str,
              help="Specifies the name of the profile, which will be collected, e.g. profile.perf.")
@click.option('--minor-version', '-m', 'minor_version_list', nargs=1, multiple=True,
              callback=cli_helpers.minor_version_list_callback, default=['HEAD'],
              help='Specifies the head minor version, for which the profiles will be collected.')
@click.option('--crawl-parents', '-cp', is_flag=True, default=False, is_eager=True,
              help='If set to true, then for each specified minor versions, profiles for parents'
                   ' will be collected as well')
@click.option('--cmd', '-c', nargs=1, required=False, multiple=True, default=[''],
              help='Command that is being profiled. Either corresponds to some'
              ' script, binary or command, e.g. ``./mybin`` or ``perun``.')
@click.option('--args', '-a', nargs=1, required=False, multiple=True,
              help='Additional parameters for <cmd>. E.g. ``status`` or '
              '``-al`` is command parameter.')
@click.option('--workload', '-w', nargs=1, required=False, multiple=True, default=[''],
              help='Inputs for <cmd>. E.g. ``./subdir`` is possible workload'
              'for ``ls`` command.')
@click.option('--params', '-p', nargs=1, required=False, multiple=True,
              callback=cli_helpers.single_yaml_param_callback,
              help='Additional parameters for called collector read from '
              'file in YAML format.')
@click.option('--output-filename-template', '-ot', default=None,
              callback=cli_helpers.set_config_option_from_flag(
                  perun_config.runtime, 'format.output_profile_template', str
              ), help='Specifies the template for automatic generation of output filename'
              ' This way the file with collected data will have a resulting filename w.r.t '
              ' to this parameter. Refer to :ckey:`format.output_profile_template` for more'
              ' details about the format of the template.')
@click.option('--optimization-pipeline', '-op', type=click.Choice(Pipeline.supported()),
              default=Pipeline.default(), callback=cli_helpers.set_optimization,
              help='Pre-configured combinations of collection optimization methods.')
@click.option('--optimization-on', '-on',
              type=click.Choice(Optimizations.supported()), multiple=True,
              callback=cli_helpers.set_optimization,
              help='Enable the specified collection optimization method.')
@click.option('--optimization-off', '-off',
              type=click.Choice(Optimizations.supported()), multiple=True,
              callback=cli_helpers.set_optimization,
              help='Disable the specified collection optimization method.')
@click.option('--optimization-args', '-oa', type=(click.Choice(Parameters.supported()), str),
              multiple=True, callback=cli_helpers.set_optimization_param,
              help='Set parameter values for various optimizations.')
@click.option('--optimization-cache-off', is_flag=True, callback=cli_helpers.set_optimization_cache,
              help='Ignore cached optimization data (e.g., cached call graph).')
@click.option('--optimization-reset-cache', is_flag=True, default=False,
              callback=cli_helpers.reset_optimization_cache,
              help='Remove the cached optimization resources and data.')
@click.option('--use-cg-type', '-cg', type=(click.Choice(CallGraphTypes.supported())),
              default=CallGraphTypes.default(), callback=cli_helpers.set_call_graph_type)
@click.pass_context
def collect(ctx, **kwargs):
    """Generates performance profile using selected collector.

    Runs the single collector unit (registered in Perun) on given profiled
    command (optionaly with given arguments and workloads) and generates
    performance profile. The generated profile is then stored in
    ``.perun/jobs/`` directory as a file, by default with filename in form of::

        bin-collector-workload-timestamp.perf

    Generated profiles will not be postprocessed in any way. Consult ``perun
    postprocessby --help`` in order to postprocess the resulting profile.

    The configuration of collector can be specified in external YAML file given
    by the ``-p``/``--params`` argument.

    For a thorough list and description of supported collectors refer to
    :ref:`collectors-list`. For a more subtle running of profiling jobs and
    more complex configuration consult either ``perun run matrix --help`` or
    ``perun run job --help``.
    """
    ctx.obj = kwargs


@cli.command('fuzz')
@click.option('--cmd', '-b', nargs=1, required=True,
              help='The command which will be fuzzed.')
@click.option('--args', '-a', nargs=1, required=False, default='',
              help='Arguments for the fuzzed command.')
@click.option('--input-sample', '-w', nargs=1, required=True, multiple=True,
              help='Initial sample of workloads, that will be source of the fuzzing.')
@click.option('--collector', '-c', nargs=1, default='time',
              type=click.Choice(utils.get_supported_module_names('collect')),
              help='Collector that will be used to collect performance data.')
@click.option('--collector-params', '-cp', nargs=2, required=False, multiple=True,
              callback=cli_helpers.yaml_param_callback,
              help='Additional parameters for the <collector> read from the'
                   ' file in YAML format')
@click.option('--postprocessor', '-p', nargs=1, required=False, multiple=True,
              type=click.Choice(utils.get_supported_module_names('postprocess')),
              help='After each collection of data will run <postprocessor> to '
                   'postprocess the collected resources.')
@click.option('--postprocessor-params', '-pp', nargs=2, required=False, multiple=True,
              callback=cli_helpers.yaml_param_callback,
              help='Additional parameters for the <postprocessor> read from the'
                   ' file in YAML format')
@click.option('--minor-version', '-m', 'minor_version_list', nargs=1,
              callback=cli_helpers.minor_version_list_callback, default=['HEAD'],
              help='Specifies the head minor version, for which the fuzzing will be performed.')
@click.option('--workloads-filter', '-wf', nargs=1, required=False,
              type=str, metavar='<regexp>', default="",
              help='Regular expression for filtering the workloads.')
@click.option('--source-path', '-s', nargs=1, required=False,
              type=click.Path(exists=True, readable=True), metavar='<path>',
              help='The path to the directory of the project source files.')
@click.option('--gcno-path', '-g', nargs=1, required=False,
              type=click.Path(exists=True, writable=True), metavar='<path>',
              help='The path to the directory where .gcno files are stored.')
@click.option('--output-dir', '-o', nargs=1, required=True,
              type=click.Path(exists=True, writable=True), metavar='<path>',
              help='The path to the directory where generated outputs will be stored.')
@click.option('--timeout', '-t', nargs=1, required=False, default=1800,
              type=click.IntRange(1, None, False), metavar='<int>',
              help='Time limit for fuzzing (in seconds).  Default value is 1800s.')
@click.option('--hang-timeout', '-h', nargs=1, required=False, default=10,
              type=click.FloatRange(0.001, None, False), metavar='<int>',
              help='The time limit before input is classified as a hang (in seconds).'
              ' Default value is 30s.')
@click.option('--max', '-N', nargs=1, required=False,
              type=click.IntRange(1, None, False), metavar='<int>',
              help='The maximum size limit of the generated input file.'
              ' Value should be larger than any of the initial workload,'
              ' otherwise it will be adjusted')
@click.option('--max-size-gain', '-mg', nargs=1, required=False, default=1000000,
              type=click.IntRange(0, None, False), metavar='<int>',
              help='Max size expressed by gain. Using this option, max size of generated input'
              ' file will be set to (size of the largest workload + value).'
              'Default value is 1 000 000 B = 1MB.')
@click.option('--max-size-ratio', '-mp', nargs=1, required=False,
              type=click.FloatRange(0.1, None, False), metavar='<float>',
              help='Max size expressed by percentage. Using this option, max size of generated'
              ' input file will be set to (size of the largest workload * value).'
              ' E.g. 1.5, max size=largest workload size * 1.5')
@click.option('--exec-limit', '-e', nargs=1, required=False, default=100,
              type=click.IntRange(1, None, False), metavar='<int>',
              help='Defines maximum number executions while gathering interesting inputs.')
@click.option('--interesting-files-limit', '-l', nargs=1, required=False,
              type=click.IntRange(1, None, False), metavar='<int>', default=20,
              help='Defines minimum number of gathered interesting inputs before perun testing.')
@click.option('--coverage-increase-rate', '-cr', nargs=1, required=False, default=1.5,
              type=click.FloatRange(0, None, False), metavar='<int>',
              help='Represents threshold of coverage increase against base coverage.'
              '  E.g 1.5, base coverage = 100 000, so threshold = 150 000.')
@click.option('--mutations-per-rule', '-mpr', nargs=1, required=False, default='mixed',
              type=click.Choice(['unitary', 'proportional', 'probabilistic', 'mixed']),
              metavar='<str>',
              help='Strategy which determines how many mutations will be generated by certain'
              ' fuzzing rule in one iteration: unitary, proportional, probabilistic, mixed')
@click.option('--regex-rules', '-r', nargs=1, required=False, multiple=True,
              callback=cli_helpers.single_yaml_param_callback, metavar='<file>',
              help='Option for adding custom rules specified by regular expressions,'
              ' written in YAML format file.')
@click.option('--no-plotting', '-np', is_flag=True, required=False,
              help='Avoiding sometimes lengthy plotting of graphs.')
def fuzz_cmd(cmd, args, **kwargs):
    """Performs fuzzing for the specified command according to the initial sample of workload."""
    kwargs['executable'] = Executable(cmd, args)
    fuzz.run_fuzzing_for_command(**kwargs)


def init_unit_commands(lazy_init=True):
    """Runs initializations for all of the subcommands (shows, collectors, postprocessors)

    Some of the subunits has to be dynamically initialized according to the registered modules,
    like e.g. show has different forms (raw, graphs, etc.).
    """
    for (unit, cli_cmd, cli_arg) in [(perun.view, show, 'show'),
                                     (perun.postprocess, postprocessby, 'postprocessby'),
                                     (perun.collect, collect, 'collect')]:
        if lazy_init and cli_arg not in sys.argv:
            continue
        for module in pkgutil.walk_packages(unit.__path__, unit.__name__ + '.'):
            # Skip modules, only packages can be used for show
            if not module[2]:
                continue
            unit_package = perun.utils.get_module(module[1])

            # Skip packages that are not for viewing, postprocessing, or collection of profiles
            if not hasattr(unit_package, 'SUPPORTED_PROFILES') and \
                    not hasattr(unit_package, 'COLLECTOR_TYPE'):
                continue

            # Skip those packages that do not contain the appropriate cli wrapper
            unit_module = perun.utils.get_module(module[1] + '.' + 'run')
            cli_function_name = module[1].split('.')[-1]
            if hasattr(unit_module, cli_function_name):
                cli_cmd.add_command(getattr(unit_module, cli_function_name))


# Initialization of other stuff
init_unit_commands()
cli.add_command(check_cli.check_group)
cli.add_command(config_cli.config)
cli.add_command(run_cli.run)
cli.add_command(utils_cli.utils_group)


def launch_cli_in_dev_mode():
    """Runs the cli in developer mode.

    In this mode, all of the exceptions are propagated, and additionally faulthandler and
    tracemalloc is enabled to ease the debugging.
    """
    import tracemalloc
    import faulthandler
    tracemalloc.start()
    faulthandler.enable()
    cli()


def launch_cli_safely():
    """Safely runs the cli.

    In case any exceptions are raised, they are catched and dump is created with additional
    debugging information, such as the environment, perun version, perun commands, etc.
    """
    try:
        stdout_log = perun_log.Logger(sys.stdout)
        stderr_log = perun_log.Logger(sys.stderr)
        sys.stdout, sys.stderr = stdout_log, stderr_log
        cli()
    except Exception as catched_exception:
        error_module = catched_exception.__module__ + '.' \
            if hasattr(catched_exception, '__module__') else ''
        error_name = error_module + catched_exception.__class__.__name__

        reported_error = error_name + ": " + str(catched_exception)
        perun_log.error("Unexpected error: {}".format(reported_error), recoverable=True)
        with helpers.SuppressedExceptions(Exception):
            cli_helpers.generate_cli_dump(reported_error, catched_exception, stdout_log, stderr_log)


def launch_cli():
    """Runs the CLI either in developer mode or in safe mode"""
    if DEV_MODE:
        launch_cli_in_dev_mode()
    else:
        launch_cli_safely()


if __name__ == "__main__":
    launch_cli()
