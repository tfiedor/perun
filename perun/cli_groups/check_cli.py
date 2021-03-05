"""Group of CLI commands used for detecting degradations in VCS history"""

import distutils.util as dutils

import click

import perun.check.factory as check
import perun.logic.pcs as pcs
import perun.logic.config as perun_config
import perun.utils.cli_helpers as cli_helpers
import perun.utils.log as log


__author__ = 'Tomas Fiedor'


@click.group('check')
@click.option('--compute-missing', '-c',
              callback=cli_helpers.set_config_option_from_flag(
                  perun_config.runtime, 'degradation.collect_before_check'),
              is_flag=True, default=False,
              help='whenever there are missing profiles in the given point of history'
                   ' the matrix will be rerun and new generated profiles assigned.')
@click.option('--models-type', '-m', nargs=1, required=False, multiple=False,
              type=click.Choice(check.get_supported_detection_models_strategies()),
              default=check.get_supported_detection_models_strategies()[0],
              help="The detection models strategies predict the way of executing "
                   "the detection between two profiles, respectively between relevant "
                   "kinds of its models. Available only in the following detection "
                   "methods: Integral Comparison (IC) and Local Statistics (LS).")
def check_group(**_):
    """Applies for the points of version history checks for possible performance changes.

    This command group either runs the checks for one point of history (``perun check head``) or for
    the whole history (``perun check all``). For each minor version (called the `target`) we iterate
    over all of the registered profiles and try to find a predecessor minor version (called the
    `baseline`) with profile of the same configuration (by configuration we mean the tuple of
    collector, postprocessors, command, arguments and workloads) and run the checks according to the
    rules set in the configurations.

    The rules are specified as an ordered list in the configuration by
    :ckey:`degradation.strategies`, where the keys correspond to the configuration (or the type) and
    key `method` specifies the actual method used for checking for performance changes. The applied
    methods can then be either specified by the full name or by its short string consisting of all
    first letter of the function name.

    The example of configuration snippet that sets rules and strategies for one project can be as
    follows:

      .. code-block:: yaml

      \b
          degradation:
            apply: first
            strategies:
              - type: mixed
                postprocessor: regression_analysis
                method: bmoe
              - cmd: mybin
                type: memory
                method: bmoe
              - method: aat

    Currently we support the following methods:

      \b
      1. Best Model Order Equality (BMOE)
      2. Average Amount Threshold (AAT)
      3. Polynomial Regression (PREG)
      4. Linear Regression (LREG)
      5. Fast Check (FAST)
      6. Integral Comparison (INT)
      7. Local Statistics (LOC)

    """
    should_precollect = dutils.strtobool(str(
        perun_config.lookup_key_recursively('degradation.collect_before_check', 'false')
    ))
    precollect_to_log = dutils.strtobool(str(
        perun_config.lookup_key_recursively('degradation.log_collect', 'false')
    ))
    if should_precollect:
        print("{} is set to {}. ".format(
            log.in_color('degradation.collect_before_check', 'white', 'bold'),
            log.in_color('true', 'green', 'bold')
        ), end='')
        print("Missing profiles will be freshly collected with respect to the ", end='')
        print("nearest job matrix (run `perun config edit` to modify the underlying job matrix).")
        if precollect_to_log:
            print("The progress of the pre-collect phase will be stored in logs at {}.".format(
                log.in_color(pcs.get_log_directory(), 'white', 'bold')
            ))
        else:
            print("The progress of the pre-collect phase will be redirected to {}.".format(
                log.in_color('black hole', 'white', 'bold')
            ))


@check_group.command('head')
@click.argument('head_minor', required=False, metavar='<hash>', nargs=1,
                callback=cli_helpers.lookup_minor_version_callback, default='HEAD')
def check_head(head_minor='HEAD'):
    """Checks for changes in performance between between specified minor version (or current `head`)
    and its predecessor minor versions.

    The command iterates over all of the registered profiles of the specified `minor version`
    (`target`; e.g. the `head`), and tries to find the nearest predecessor minor version
    (`baseline`), where the profile with the same configuration as the tested target profile exists.
    When it finds such a pair, it runs the check according to the strategies set in the
    configuration (see :ref:`degradation-config` or :doc:`config`).

    By default the ``hash`` corresponds to the `head` of the current project.
    """
    log.newline()
    check.degradation_in_minor(head_minor)


@check_group.command('all')
@click.argument('minor_head', required=False, metavar='<hash>', nargs=1,
                callback=cli_helpers.lookup_minor_version_callback, default='HEAD')
def check_all(minor_head='HEAD'):
    """Checks for changes in performance for the specified interval of version history.

    The commands crawls through the whole history of project versions starting from the specified
    ``<hash>`` and for all of the registered profiles (corresponding to some `target` minor version)
    tries to find a suitable predecessor profile (corresponding to some `baseline` minor version)
    and runs the performance check according to the set of strategies set in the configuration
    (see :ref:`degradation-config` or :doc:`config`).
    """
    print("[!] Running the degradation checks on the whole VCS history. This might take a while!\n")
    check.degradation_in_history(minor_head)


@check_group.command('profiles')
@click.argument('baseline_profile', required=True, metavar='<baseline>', nargs=1,
                callback=cli_helpers.lookup_any_profile_callback)
@click.argument('target_profile', required=True, metavar='<target>', nargs=1,
                callback=cli_helpers.lookup_any_profile_callback)
@click.option('--minor', '-m', nargs=1, default=None, is_eager=True,
              callback=cli_helpers.lookup_minor_version_callback, metavar='<hash>',
              help='Will check the index of different minor version <hash>'
                   ' during the profile lookup.')
@click.pass_context
def check_profiles(ctx, baseline_profile, target_profile, minor, **_):
    """Checks for changes in performance between two profiles.

    The commands checks for the changes between two isolate profiles, that can be stored in pending
    profiles, registered in index, or be simply stored in filesystem. Then for the pair of profiles
    <baseline> and <target> the command runs the performance chekc according to the set of
    strategies set in the configuration (see :ref:`degradation-config` or :doc:`config`).

    <baseline> and <target> profiles will be looked up in the following steps:

        1. If profile is in form ``i@i`` (i.e, an `index tag`), then `ith`
           record registered in the minor version <hash> index will be used.

        2. If profile is in form ``i@p`` (i.e., an `pending tag`), then
           `ith` profile stored in ``.perun/jobs`` will be used.

        3. Profile is looked-up within the minor version <hash> index for a
           match. In case the <profile> is registered there, it will be used.

        4. Profile is looked-up within the ``.perun/jobs`` directory. In case
           there is a match, the found profile will be used.

        5. Otherwise, the directory is walked for any match. Each found match
           is asked for confirmation by user.

    """
    log.newline()
    check.degradation_between_files(
        baseline_profile, target_profile, minor, ctx.parent.params['models_type']
    )
