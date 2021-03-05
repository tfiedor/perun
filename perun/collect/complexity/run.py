"""Wrapper for complexity collector, which collects profiling data about
running times and sizes of structures.

Specifies before, collect and after functions to perform the initialization,
collection and postprocessing of collection data.
"""

import collections
import os
import shutil
from subprocess import CalledProcessError

import click

import perun.collect.complexity.configurator as configurator
import perun.collect.complexity.makefiles as makefiles
import perun.collect.complexity.symbols as symbols
import perun.logic.runner as runner
import perun.utils.exceptions as exceptions
import perun.utils.log as log
import perun.utils as utils

# The profiling record template
_ProfileRecord = collections.namedtuple('record', ['action', 'func', 'timestamp', 'size'])

# The collect phase status messages
_COLLECTOR_STATUS_MSG = {
    0:  'OK',
    1:  'Err: profile output file cannot be opened.',
    2:  'Err: profile output file closed unexpectedly.',
    11: 'Err: runtime configuration file does not exists.',
    12: 'Err: runtime configuration file syntax error.',
    21: 'Err: command could not be run.'
}

# The collector subtypes
_COLLECTOR_SUBTYPES = {
    'delta': 'time delta'
}

# The time conversion constant
_MICRO_TO_SECONDS = 1000000.0


def before(executable, **kwargs):
    """ Builds, links and configures the complexity collector executable
    In total, this function creates the so-called configuration executable (used to obtain
    information about the available functions for profiling) and the collector executable
    (used for the data collection itself)

    :param Executable executable: executed profiled command
    :param kwargs: the configuration settings for the complexity collector

    :return tuple:  int as a status code, nonzero values for errors
                    string as a status message, mainly for error states
                    dict of modified kwargs with 'cmd' value representing the executable
    """
    try:

        # Validate the inputs and dependencies first
        _validate_input(**kwargs)
        _check_dependencies()

        # Extract several keywords to local variables
        target_dir, files, rules = kwargs['target_dir'], kwargs['files'], kwargs['rules']

        # Create the configuration cmake and build the configuration executable
        log.cprint('Building the configuration executable...', 'white')
        cmake_path = makefiles.create_config_cmake(target_dir, files)
        exec_path = makefiles.build_executable(cmake_path, makefiles.CMAKE_CONFIG_TARGET)
        log.done()

        # Extract some configuration data using the configuration executable
        log.cprint('Extracting the configuration...', 'white')
        function_sym = symbols.extract_symbols(exec_path)
        include_list, exclude_list, runtime_filter = symbols.filter_symbols(function_sym, rules)
        log.done()

        # Create the collector cmake and build the collector executable
        log.cprint('Building the collector executable...', 'white')
        cmake_path = makefiles.create_collector_cmake(target_dir, files, exclude_list)
        exec_path = makefiles.build_executable(cmake_path, makefiles.CMAKE_COLLECT_TARGET)
        log.done()

        # Create the internal configuration file
        configurator.create_runtime_config(exec_path, runtime_filter, include_list, kwargs)
        executable.cmd = exec_path
        return 0, _COLLECTOR_STATUS_MSG[0], dict(kwargs)

    # The "expected" exception types
    except (OSError, ValueError, CalledProcessError,
            UnicodeError, exceptions.UnexpectedPrototypeSyntaxError) as exception:
        log.failed()
        return 1, str(exception), kwargs


def collect(executable, **kwargs):
    """ Runs the collector executable and extracts the performance data

    :param Executable executable: executable configuration (command, arguments and workloads)
    :param kwargs: the configuration settings for the complexity collector

    :return tuple:  int as a status code, nonzero values for errors
                    string as a status message, mainly for error states
                    dict of unmodified kwargs
    """
    log.cprint('Running the collector...', 'white')
    collect_dir = os.path.dirname(executable.cmd)
    # Run the command and evaluate the returncode
    try:
        utils.run_safely_external_command(str(executable), cwd=collect_dir)
        log.done()
        return 0, _COLLECTOR_STATUS_MSG[0], dict(kwargs)
    except (CalledProcessError, IOError) as err:
        log.failed()
        return 21, _COLLECTOR_STATUS_MSG[21] + ": {}".format(str(err)), dict(kwargs)


def after(executable, **kwargs):
    """ Performs the transformation of the raw data output into the profile format

    :param Executable executable: full collected command with arguments and workload
    :param kwargs: the configuration settings for the complexity collector

    :return tuple:  int as a status code, nonzero values for errors
                    string as a status message, mainly for error states
                    dict of modified kwargs with 'profile' value representing the resulting profile
    """
    # Get the trace log path
    log.cprint('Starting the post-processing phase...', 'white')
    data_path = os.path.join(os.path.dirname(executable.cmd), kwargs['internal_data_filename'])
    address_map = symbols.extract_symbol_address_map(executable.cmd)

    resources, call_stack = [], []
    profile_start, profile_end = 0, 0

    with open(data_path, 'r') as profile:
        is_first_line = True
        for line in profile:
            # Split the line into action, function name, timestamp and size
            record = _ProfileRecord(*line.split())

            # Process the record
            if _process_file_record(record, call_stack, resources, address_map) != 0:
                # Stack error
                err_msg = 'Call stack error, record: ' + record.func + ', ' + record.action
                if not call_stack:
                    err_msg += ', stack top: empty'
                else:
                    err_msg += ', stack top: ' + call_stack[-1].func + ', ' + call_stack[-1].action
                log.failed()
                return 1, err_msg, kwargs

            # Get the first and last record timestamps to determine the profiling time
            profile_end = record.timestamp
            if is_first_line:
                is_first_line = False
                profile_start = record.timestamp

    # Update the profile dictionary
    kwargs['profile'] = {
        'global': {
            'time': str((int(profile_end) - int(profile_start)) / _MICRO_TO_SECONDS) + 's',
            'resources': resources
        }
    }
    log.done()
    return 0, _COLLECTOR_STATUS_MSG[0], dict(kwargs)


def _process_file_record(record, call_stack, resources, address_map):
    """ Processes the next profile record and tries to pair it with stack record if possible

    :param _ProfileRecord record: the _ProfileRecord tuple containing the record data
    :param list call_stack: the call stack with file records
    :param list resources: the list of resource dictionaries
    :param dict address_map: the 'function address : demangled name' map

    :return int: the status code, nonzero values for errors
    """
    if record.action == 'i':
        call_stack.append(record)
        return 0
    elif call_stack and call_stack[-1].action == 'i' and call_stack[-1].func == record.func:
        # Function exit, match with the function enter to create resources record
        matching_record = call_stack.pop()
        resources.append({'amount': int(record.timestamp) - int(matching_record.timestamp),
                          'uid': address_map[record.func],
                          'type': 'mixed',
                          'subtype': _COLLECTOR_SUBTYPES['delta'],
                          'structure-unit-size': int(record.size)})
        return 0
    # Call stack function frames not matching
    return 1


def _check_dependencies():
    """Validates that dependencies (cmake and make) are met"""
    log.cprint('Checking dependencies...', 'white')
    log.newline()
    log.cprint("make:", 'white')
    log.info("\t", end="")
    if not shutil.which('make'):
        log.no()
        log.error("Could not find 'make'. Please, install the makefile package.")
    log.yes()
    log.cprint("cmake:", 'white')
    log.info("\t", end="")
    if not shutil.which('cmake'):
        log.no()
        log.error("Could not find 'cmake'. Please, install build-essentials and cmake packages.")
    log.done()


def _validate_input(**kwargs):
    """Validate the collector input parameters. In case of some error, an according exception
    is raised

    :param kwargs: the collector input parameters
    :return dict: validated input parameters
    """
    target_dir = kwargs['target_dir']
    if not target_dir:
        raise click.exceptions.BadParameter("The --target-dir parameter must be supplied.")
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
    if os.path.exists(target_dir) and not os.path.isdir(target_dir):
        raise click.exceptions.BadParameter("The given --target-dir already exists and "
                                            "is not a directory")
    if not kwargs['files']:
        raise click.exceptions.BadParameter("At least one --files parameter must be supplied.")


def _sampling_to_dictionary(_, __, value):
    """Sampling cli option converter callback. Transforms each sampling tuple into dictionary.

    :param dict _: click context
    :param object __: the parameter object
    :param list value: the list of sampling values

    :return list of dict: list of sampling dictionaries
    """
    if value is not None:
        # Initialize
        sampling_list = []
        # Transform the tuple to more human readable dictionary
        for sample in value:
            sampling_list.append({
                "func": sample[0],
                "sample": sample[1]
            })
        return sampling_list


@click.command()
@click.option('--target-dir', '-t', type=click.Path(resolve_path=True),
              help='Target directory path for compiled binary and temporary build data.')
@click.option('--files', '-f', type=click.Path(exists=True, resolve_path=True), multiple=True,
              help='List of C/C++ source files that will be used to build the'
              ' custom binary with injected profiling commands. Must be valid'
              ' resolvable path')
@click.option('--rules', '-r', type=str, multiple=True,
              help='Marks the function for profiling.')
@click.option('--internal-data-filename', '-if', type=str,
              default=configurator.DEFAULT_DATA_FILENAME,
              help='Sets the different path for internal output filename for'
              ' storing temporary profiling data file name.')
@click.option('--internal-storage-size', '-is', type=int, default=configurator.DEFAULT_STORAGE_SIZE,
              help='Increases the size of internal profiling data storage.')
@click.option('--internal-direct-output', '-id', is_flag=True,
              default=configurator.DEFAULT_DIRECT_OUTPUT,
              help=('If set, profiling data will be stored into the internal'
                    ' log file directly instead of being saved into data '
                    'structure and printed later.'))
@click.option('--sampling', '-s', type=(str, int), multiple=True, callback=_sampling_to_dictionary,
              help='Sets the sampling of the given function to every <int> call.')
@click.pass_context
def complexity(ctx, **kwargs):
    """Generates `complexity` performance profile, capturing running times of
    function depending on underlying structural sizes.

    \b
      * **Limitations**: C/C++ binaries
      * **Metric**: `mixed` (captures both `time` and `size` consumption)
      * **Dependencies**: ``libprofile.so`` and ``libprofapi.so``
      * **Default units**: `ms` for `time`, `element number` for `size`

    Example of collected resources is as follows:

    .. code-block:: json

        \b
        {
            "amount": 11,
            "subtype": "time delta",
            "type": "mixed",
            "uid": "SLList_init(SLList*)",
            "structure-unit-size": 0
        }

    Complexity profiles are suitable for postprocessing by
    :ref:`postprocessors-regression-analysis` since they capture dependency of
    time consumption depending on the size of the structure. This allows one to
    model the estimation of complexity of individual functions.

    Scatter plots are suitable visualization for profiles collected by
    `complexity` collector, which plots individual points along with regression
    models (if the profile was postprocessed by regression analysis). Run
    ``perun show scatter --help`` or refer to :ref:`views-scatter` for more
    information about `scatter plots`.

    Refer to :ref:`collectors-complexity` for more thorough description and
    examples of `complexity` collector.
    """
    runner.run_collector_from_cli_context(ctx, 'complexity', kwargs)
