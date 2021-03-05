"""Collection of functions for running collectors and postprocessors"""

import os
import subprocess
import signal

import distutils.util as dutils
import perun.vcs as vcs
import perun.logic.pcs as pcs
import perun.logic.config as config
import perun.logic.commands as commands
import perun.logic.index as index
import perun.profile.helpers as profile
import perun.utils as utils
import perun.utils.streams as streams
import perun.utils.log as log
import perun.utils.decorators as decorators
import perun.utils.helpers as helpers
import perun.workload as workloads
import perun.collect.trace.optimizations.optimization

from perun.utils import get_module
from perun.utils.structs import GeneratorSpec, Unit, Executable, RunnerReport, \
    CollectStatus, PostprocessStatus, Job
from perun.utils.helpers import COLLECT_PHASE_COLLECT, COLLECT_PHASE_POSTPROCESS, \
    COLLECT_PHASE_CMD, COLLECT_PHASE_WORKLOAD, HandledSignals
from perun.workload.singleton_generator import SingletonGenerator
from perun.utils.exceptions import SignalReceivedException

__author__ = 'Tomas Fiedor'


def construct_job_matrix(cmd, args, workload, collector, postprocessor, **kwargs):
    """Constructs the job matrix represented as dictionary.

    Reads the local of the current PCS and constructs the matrix of jobs
    that will be run. Each job consists of command that will be run,
    collector used to collect the data and list of postprocessors to
    alter the output profiles. Inside the dictionary jobs are distributed
    by binaries, then workloads and finally Jobs.

    Returns the job matrix as dictionary of form:
    {
      'cmd1': {
        'workload1': [ Job1, Job2 , ...],
        'workload2': [ Job1, Job2 , ...]
      },
      'cmd2': {
        'workload1': [ Job1, Job2 , ...],
        'workload2': [ Job1, Job2 , ...]
      }
    }

    :param list cmd: binary that will be run
    :param list args: lists of additional arguments to the job
    :param list workload: list of workloads
    :param list collector: list of collectors
    :param list postprocessor: list of postprocessors
    :param dict kwargs: additional parameters issued from the command line
    :returns dict, int: dict of jobs in form of {cmds: {workloads: {Job}}}, number of jobs
    """
    def construct_unit(unit, unit_type, ukwargs):
        """Helper function for constructing the {'name', 'params'} objects for collectors and posts.

        :param str unit: name of the unit (collector/postprocessor)
        :param str unit_type: name of the unit type (collector or postprocessor)
        :param dict ukwargs: dictionary of additional parameters
        :returns dict: dictionary of the form {'name', 'params'}
        """
        # Get the dictionaries for from string and from file params obtained from commandline
        unit_param_dict = ukwargs.get(unit_type + "_params", {}).get(unit, {})

        # Construct the object with name and parameters
        return Unit(unit, unit_param_dict)

    # Convert the bare lists of collectors and postprocessors to {'name', 'params'} objects
    collector_pairs = list(map(lambda c: construct_unit(c, 'collector', kwargs), collector))
    posts = list(map(lambda p: construct_unit(p, 'postprocessor', kwargs), postprocessor))

    # Construct the actual job matrix
    matrix = {
        str(b): {
            str(w): [
                Job(c, posts, Executable(b, a, w)) for c in collector_pairs for a in args or ['']
                ] for w in workload
            } for b in cmd
        }

    # Count overall number of the jobs:
    number_of_jobs = 0
    for cmd_values in matrix.values():
        for workload_values in cmd_values.values():
            for job in workload_values:
                number_of_jobs += 1 + len(job.postprocessors)

    return matrix, number_of_jobs


def load_job_info_from_config():
    """
    :returns dict: dictionary with cmds, args, workloads, collectors and postprocessors
    """
    local_config = pcs.local_config().data

    if 'collectors' not in local_config.keys():
        log.error(
            "missing 'collectors' region in the local.yml\n\n"
            "Run `perun config edit` and fix the job matrix in order to collect the data."
            "For more information about job matrix see :doc:`jobs`."
        )
    collectors = local_config['collectors']
    postprocessors = local_config.get('postprocessors', [])

    if 'cmds' not in local_config.keys():
        log.error(
            "missing 'cmds' region in the local.yml\n\n"
            "Run `perun config edit` and fix the job matrix in order to collect the data."
            "For more information about job matrix see :doc:`jobs`."
        )

    info = {
        'cmd': local_config['cmds'],
        'args': helpers.get_key_with_aliases(local_config, ('args', 'params'), default=[]),
        'workload': local_config.get('workloads', ['']),
        'postprocessor': [post.get('name', '') for post in postprocessors],
        'collector': [collect.get('name', '') for collect in collectors],
        'collector_params': {
            collect.get('name', ''): collect.get('params', {}) for collect in collectors
            },
        'postprocessor_params': {
            post.get('name', ''): post.get('params', {}) for post in postprocessors
            }
    }

    return info


def run_phase_function(report, phase):
    """Runs the concrete phase function of the runner (collector or postprocessor)

    If the runner does not provide the function for phase then empty pass is created and
    nothing is returned. If any exception occurs, or if the phase return non-zero status,
    then the overall report ends with Error.

    :param RunnerReport report: collective report about the run of the phase
    :param str phase: name of the phase/function that is run
    """
    phase_function = getattr(report.runner, phase, utils.create_empty_pass(report.ok_status))
    runner_verb = report.runner_type[:-2]
    report.phase = phase
    try:
        phase_result = phase_function(**report.kwargs)
        report.update_from(*phase_result)
    # We safely catch all of the exceptions
    except Exception as exc:
        report.status = report.error_status
        report.exception = exc
        report.message = "error while {}{} phase: {}".format(
            phase, ("_" + runner_verb)*(phase != runner_verb), str(exc)
        )


def check_integrity_of_runner(runner, runner_type, report):
    """Checks that the runner has basic requirements of collectors and postprocessor.

    This function warns user that some expected conventions were not fulfilled. In particular,
    this checks that the runners return the dictionary with 'profile' keyword, i.e. it does
    something with profile. Second it checks that the runner has corresponding collect or
    postprocess functions (though theoretically one can have only before and after phases)

    :param module runner: module of the runner (postprocessor or collector)
    :param str runner_type: string name of the runner (the run function is derived from this)
    :param RunnerReport report: report of the collection phase
    """
    runner_name = runner.__name__.split('.')[-2]
    if 'profile' not in report.kwargs.keys() and report.is_ok():
        log.warn("{} {} does not return any profile".format(
            runner_name, runner_type
        ))

    runner_verb = runner_type[:-2]
    if not getattr(runner, runner_verb, None):
        log.warn("{} is missing {}() function".format(
            runner_name, runner_verb
        ))


def runner_teardown_handler(status_report, **kwargs):
    """The teardown callback used in the signal handler.

    :param RunnerReport status_report: the collection report object
    :param kwargs: additional parameters as supplied by the HandledSignals CM
    """
    exc = kwargs['exc_val']
    if isinstance(exc, SignalReceivedException):
        log.warn('Received signal: {}, safe termination in process'.format(exc.signum))
        status_report.status = status_report.error_status
        status_report.exception = exc
        status_report.message = "received signal during teardown() phase: {} ({})" .format(
            exc.signum, str(exc)
        )
    run_phase_function(status_report, 'teardown')


def runner_signal_handler(signum, frame):
    """Custom signal handler that blocks all the handled signals until the __exit__ sentinel of
    the CM is reached.

    :param int signum: a representation of the encountered signal
    :param object frame: a frame / stack trace object
    """
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    signal.signal(signal.SIGQUIT, signal.SIG_IGN)
    raise SignalReceivedException(signum, frame)


def run_all_phases_for(runner, runner_type, runner_params):
    """Run all of the phases (before, runner_type, after) for given params.

    Runs three of the phases before, runner_type and after for the given runner params
    with runner (collector or postprocesser). During each phase, either error occurs,
    with given error message or updated params, that are used in next phase. This
    way the phases can pass the information.

    Returns the computed profile

    :param module runner: module that is going to be runned
    :param str runner_type: string type of the runner (either collector or postprocessor)
    :param dict runner_params: dictionary of arguments for runner
    :return RunnerReport: report about the run phase
    """
    runner_verb = runner_type[:-2]
    # Create immutable list of resource that should hold even in case of problems
    runner_params['opened_resources'] = []

    report = RunnerReport(runner, runner_type, runner_params)

    with HandledSignals(
            signal.SIGINT, signal.SIGTERM, signal.SIGQUIT, handler=runner_signal_handler,
            callback=runner_teardown_handler, callback_args=[report]
    ):
        for phase in ['before', runner_verb, 'after']:
            run_phase_function(report, phase)

            if not report.is_ok():
                break

            # Run the optimizations
            perun.collect.trace.optimizations.optimization.optimize(
                runner_type, phase, **report.kwargs
            )

    check_integrity_of_runner(runner, runner_type, report)

    return report, report.kwargs.get('profile', {})


@log.print_elapsed_time
@decorators.phase_function('collect')
def run_collector(collector, job):
    """Run the job of collector of the given name.

    Tries to look up the module containing the collector specified by the
    collector name, and then runs it with the parameters and returns collected profile.

    :param Unit collector: object representing the collector
    :param Job job: additional information about the running job
    :returns (int, dict): status of the collection, generated profile
    """
    log.print_current_phase(
        "Collecting data by {}", collector.name, COLLECT_PHASE_COLLECT
    )

    try:
        collector_module = get_module('perun.collect.{0}.run'.format(collector.name))
    except ImportError:
        log.error("{} collector does not exist".format(collector.name), recoverable=True)
        return CollectStatus.ERROR, {}

    # First init the collector by running the before phases (if it has)
    job_params = utils.merge_dictionaries(job._asdict(), collector.params)
    collection_report, prof = run_all_phases_for(collector_module, 'collector', job_params)

    if not collection_report.is_ok():
        log.error("while collecting by {}: {}".format(
            collector.name, collection_report.message
        ), recoverable=True, raised_exception=collection_report.exception)
    else:
        log.info("Successfully collected data from {}".format(job.executable.cmd))

    return collection_report.status, prof


def run_collector_from_cli_context(ctx, collector_name, collector_params):
    """Runs the collector according to the given cli context.

    This is used as a wrapper for calls from various collector modules. This was extracted,
    to minimize the needed input of new potential collectors.

    :param Context ctx: click context containing arguments obtained by 'perun collect' command
    :param str collector_name: name of the collector that will be run
    :param dict collector_params: dictionary with collector params
    """
    cmd, args, workload = ctx.obj['cmd'], ctx.obj['args'], ctx.obj['workload']
    minor_versions = ctx.obj['minor_version_list']
    collector_params.update(ctx.obj['params'])
    run_params = {
        'collector_params': {
            collector_name: collector_params
        },
        'profile_name': ctx.obj['profile_name']
    }
    collect_status = run_single_job(
        cmd, args, workload, [collector_name], [], minor_versions, **run_params
    )
    if collect_status != CollectStatus.OK:
        log.error("collection of profiles was unsuccessful")


@log.print_elapsed_time
@decorators.phase_function('postprocess')
def run_postprocessor(postprocessor, job, prof):
    """Run the job of postprocess of the given name.

    Tries to look up the module containing the postprocessor specified by the
    postprocessor name, and then runs it with the parameters and returns processed
    profile.

    :param Unit postprocessor: dictionary representing the postprocessor
    :param Job job: additional information about the running job
    :param dict prof: dictionary with profile
    :returns (int, dict): status of the collection, postprocessed profile
    """
    log.print_current_phase(
        "Postprocessing data with {}", postprocessor.name, COLLECT_PHASE_POSTPROCESS
    )

    try:
        postprocessor_module = get_module('perun.postprocess.{0}.run'.format(postprocessor.name))
    except ImportError:
        log.error("{} postprocessor does not exist".format(postprocessor.name), recoverable=True)
        return PostprocessStatus.ERROR, {}

    # First init the collector by running the before phases (if it has)
    job_params = utils.merge_dict_range(job._asdict(), {'profile': prof}, postprocessor.params)
    postprocess_report, prof = run_all_phases_for(postprocessor_module, 'postprocessor', job_params)

    if not postprocess_report.is_ok() or not prof:
        log.error("while postprocessing by {}: {}".format(
            postprocessor.name, postprocess_report.message
        ), recoverable=True)
    else:
        log.info("Successfully postprocessed data by {}".format(postprocessor.name))

    return postprocess_report.status, prof


def store_generated_profile(prof, job, profile_name=None):
    """Stores the generated profile in the pending jobs directory.

    :param Profile prof: profile that we are storing in the repository
    :param Job job: job with additional information about generated profiles
    :param optional profile_name: user-defined name of the profile
    """
    full_profile = profile.finalize_profile_for_job(prof, job)
    full_profile_name = profile_name or profile.generate_profile_name(full_profile)
    profile_directory = pcs.get_job_directory()
    full_profile_path = os.path.join(profile_directory, full_profile_name)
    streams.store_json(full_profile.serialize(), full_profile_path)
    log.info("stored profile at: {}".format(os.path.relpath(full_profile_path)))
    if dutils.strtobool(str(config.lookup_key_recursively("profiles.register_after_run", "false"))):
        # We either store the profile according to the origin, or we use the current head
        dst = prof.get('origin', vcs.get_minor_head())
        commands.add([full_profile_path], dst, keep_profile=False)
    else:
        # Else we register the profile in pending index
        index.register_in_pending_index(full_profile_path, prof)


def run_postprocessor_on_profile(prof, postprocessor_name, postprocessor_params, skip_store=False):
    """Run the job of the postprocessor according to the given profile.

    First extracts the information from the profile in order to construct the job,
    then runs the given postprocessor that is appended to the list of postprocessors
    of the profile, and the postprocessed profile is stored in the pending jobs.

    :param dict prof: dictionary with profile informations
    :param str postprocessor_name: name of the postprocessor that we are using
    :param dict postprocessor_params: parameters for the postprocessor
    :param bool skip_store: if set to true, then the profil will not be stored
    :returns (PostprocessStatus, dict): status how the postprocessing went and the postprocessed
        profile
    """
    profile_job = profile.extract_job_from_profile(prof)
    postprocessor_unit = Unit(postprocessor_name, postprocessor_params)
    profile_job.postprocessors.append(postprocessor_unit)

    p_status, processed_profile = run_postprocessor(postprocessor_unit, profile_job, prof)
    if p_status == PostprocessStatus.OK and prof and not skip_store:
        store_generated_profile(processed_profile, profile_job)
    return p_status, processed_profile


@log.print_elapsed_time
@decorators.phase_function('prerun')
def run_prephase_commands(phase, phase_colour='white'):
    """Runs the phase before the actual collection of the methods

    This command first retrieves the phase from the configuration, and runs
    safely all of the commands specified in the list.

    The phase is specified in :doc:`config` by keys specified in section
    :cunit:`execute`.

    :param str phase: name of the phase commands
    :param str phase_colour: colour for the printed phase
    """
    phase_key = ".".join(["execute", phase]) if not phase.startswith('execute') else phase
    cmds = pcs.local_config().safe_get(phase_key, [])
    if cmds:
        log.cprint("Running '{}' phase".format(phase), phase_colour)
        log.newline()
        try:
            utils.run_safely_list_of_commands(cmds)
        except subprocess.CalledProcessError as exception:
            error_command = str(exception.cmd)
            error_code = exception.returncode
            error_output = exception.output
            log.error("error during {} phase while running '{}' exited with: {} ({})".format(
                phase, error_command, error_code, error_output
            ))


@log.print_elapsed_time
@decorators.phase_function('batch job run')
def generate_jobs_on_current_working_dir(job_matrix, number_of_jobs):
    """Runs the batch of jobs on current state of the VCS.

    This function expects no changes not commited in the repo, it excepts correct version
    checked out and just runs the matrix.

    :param dict job_matrix: dictionary with jobs that will be run
    :param int number_of_jobs: number of jobs that will be run
    :return: pair of job and generated profile
    """
    workload_generators_specs = workloads.load_generator_specifications()

    log.print_job_progress.current_job = 1
    collective_status = CollectStatus.OK
    log.newline()
    for job_cmd, workloads_per_cmd in job_matrix.items():
        log.print_current_phase("Collecting profiles for {}", job_cmd, COLLECT_PHASE_CMD)
        for workload, jobs_per_workload in workloads_per_cmd.items():
            log.print_current_phase(" = processing generator {}", workload, COLLECT_PHASE_WORKLOAD)
            # Prepare the specification
            generator, params = workload_generators_specs.get(
                workload, GeneratorSpec(SingletonGenerator, {'value': workload})
            )
            for job in jobs_per_workload:
                log.print_job_progress(number_of_jobs)
                for c_status, prof in generator(job, **params).generate(run_collector):
                    # Run the collector and check if the profile was successfully collected
                    # In case, the status was not OK, then we skip the postprocessing
                    if c_status != CollectStatus.OK or not prof:
                        collective_status = CollectStatus.ERROR
                        continue

                    # Temporary nasty hack
                    prof = profile.finalize_profile_for_job(prof, job)

                    for postprocessor in job.postprocessors:
                        log.print_job_progress(number_of_jobs)
                        # Run postprocess and check if the profile was successfully postprocessed
                        p_status, prof = run_postprocessor(postprocessor, job, prof)
                        if p_status != PostprocessStatus.OK or not prof:
                            collective_status = CollectStatus.ERROR
                            break
                    else:
                        # Store the computed profile inside the job directory
                        yield collective_status, prof, job


@log.print_elapsed_time
@decorators.phase_function('overall profiling')
def generate_jobs(minor_version_list, job_matrix, number_of_jobs):
    """
    :param list minor_version_list: list of MinorVersion info
    :param dict job_matrix: dictionary with jobs that will be run
    :param int number_of_jobs: number of jobs that will be run
    """
    with vcs.CleanState():
        for minor_version in minor_version_list:
            vcs.checkout(minor_version.checksum)
            run_prephase_commands('pre_run', COLLECT_PHASE_CMD)
            yield from generate_jobs_on_current_working_dir(job_matrix, number_of_jobs)


@log.print_elapsed_time
@decorators.phase_function('overall profiling')
def generate_jobs_with_history(minor_version_list, job_matrix, number_of_jobs):
    """
    :param list minor_version_list: list of MinorVersion info
    :param dict job_matrix: dictionary with jobs that will be run
    :param int number_of_jobs: number of jobs that will be run
    """
    with log.History(minor_version_list[0].checksum) as history:
        with vcs.CleanState():
            for minor_version in minor_version_list:
                history.progress_to_next_minor_version(minor_version)
                log.newline()
                history.finish_minor_version(minor_version, [])
                vcs.checkout(minor_version.checksum)
                run_prephase_commands('pre_run', COLLECT_PHASE_CMD)
                yield from generate_jobs_on_current_working_dir(job_matrix, number_of_jobs)
                log.newline()
                history.flush(with_border=True)


def generate_profiles_for(cmd, args, workload, collector, postprocessor, minor_version_list,
                          **kwargs):
    """Helper generator, that takes job specification and continuously generates profiles

    This is mainly used for fuzzing, which requires to handle the profiles without any storage,
    since the generated profiles are not futher used.

    :param list cmd: list of commands that will be run
    :param list args: lists of additional arguments to the job
    :param list workload: list of workloads
    :param list collector: list of collectors
    :param list postprocessor: list of postprocessors
    :param list minor_version_list: list of MinorVersion info
    :param dict kwargs: dictionary of additional params for postprocessor and collector
    """
    job_matrix, number_of_jobs = \
        construct_job_matrix(cmd, args, workload, collector, postprocessor, **kwargs)
    yield from generate_jobs(minor_version_list, job_matrix, number_of_jobs)


def run_single_job(cmd, args, workload, collector, postprocessor, minor_version_list,
                   with_history=False, **kwargs):
    """
    :param list cmd: list of commands that will be run
    :param list args: lists of additional arguments to the job
    :param list workload: list of workloads
    :param list collector: list of collectors
    :param list postprocessor: list of postprocessors
    :param list minor_version_list: list of MinorVersion info
    :param bool with_history: if set to true, then we will print the history object
    :param dict kwargs: dictionary of additional params for postprocessor and collector
    :return: CollectStatus.OK if all jobs were successfully collected, CollectStatus.ERROR if any
        of collections or postprocessing failed
    """
    job_matrix, number_of_jobs = \
        construct_job_matrix(cmd, args, workload, collector, postprocessor, **kwargs)
    generator_function = generate_jobs_with_history if with_history else generate_jobs
    status = CollectStatus.OK
    finished_jobs = 0
    for status, prof, job in generator_function(minor_version_list, job_matrix, number_of_jobs):
        store_generated_profile(prof, job, kwargs.get('profile_name'))
        finished_jobs += 1
    return status if finished_jobs > 0 else CollectStatus.ERROR


def run_matrix_job(minor_version_list, with_history=False):
    """
    :param list minor_version_list: list of MinorVersion info
    :param bool with_history: if set to true, then we will print the history object
    :return: CollectStatus.OK if all jobs were successfully collected, CollectStatus.ERROR if any
        of collections or postprocessing failed
    """
    job_matrix, number_of_jobs = construct_job_matrix(**load_job_info_from_config())
    generator_function = generate_jobs_with_history if with_history else generate_jobs
    status = CollectStatus.OK
    finished_jobs = 0
    for status, prof, job in generator_function(minor_version_list, job_matrix, number_of_jobs):
        store_generated_profile(prof, job)
        finished_jobs += 1
    return status if finished_jobs > 0 else CollectStatus.ERROR
