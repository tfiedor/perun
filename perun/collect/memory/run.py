"""This module contains methods needed by Perun logic"""

import os
import traceback

import click

import perun.collect.memory.filter as filters
import perun.collect.memory.parsing as parser
import perun.collect.memory.syscalls as syscalls
import perun.logic.runner as runner
import perun.utils.log as log
from perun.utils.structs import CollectStatus

__author__ = 'Radim Podola'
_lib_name = "malloc.so"
_tmp_log_filename = "MemoryLog"
DEFAULT_SAMPLING = 0.001


def before(executable, **_):
    """ Phase for initialization the collect module

    :param Executable executable: executable profiled command
    :returns tuple: (return code, status message, updated kwargs)
    """
    pwd = os.path.dirname(os.path.abspath(__file__))
    if not os.path.isfile("{}/{}".format(pwd, _lib_name)):
        print("Missing compiled dynamic library 'lib{}'. Compiling from sources: ".format(
            os.path.splitext(_lib_name)[0]
        ), end='')
        result = syscalls.init()
        if result:
            log.failed()
            error_msg = 'Build of the library failed with error code: '
            error_msg += str(result)
            return CollectStatus.ERROR, error_msg, {}
        else:
            log.done()

    print("Checking if binary contains debugging information: ", end='')
    if not syscalls.check_debug_symbols(executable.cmd):
        log.failed()
        error_msg = "Binary does not contain debug info section.\n"
        error_msg += "Please recompile your project with debug options (gcc -g | g++ -g)"
        return CollectStatus.ERROR, error_msg, {}
    log.done()
    print("Finished preprocessing step!\n")

    return CollectStatus.OK, '', {}


def collect(executable, **_):
    """ Phase for collection of the profile data

    :param Executable executable: executable profiled command
    :returns tuple: (return code, status message, updated kwargs)
    """
    print("Collecting data: ", end='')
    result, collector_errors = syscalls.run(executable)
    if result:
        log.failed()
        error_msg = 'Execution of binary failed with error code: '
        error_msg += str(result) + "\n"
        error_msg += collector_errors
        return CollectStatus.ERROR, error_msg, {}
    log.done()
    print("Finished collection of the raw data!\n")
    return CollectStatus.OK, '', {}


def after(executable, sampling=DEFAULT_SAMPLING, **kwargs):
    """ Phase after the collection for minor postprocessing
        that needs to be done after collect

    :param Executable executable: executable profiled command
    :param int sampling: sampling of the collection of the data
    :param dict kwargs: profile's header
    :returns tuple: (return code, message, updated kwargs)

    Case studies:
        --sampling=0.1 --no-func=f2 --no-source=s --all
        -> run memory collector with 0.1s sampling,
        excluding allocations in "f2" function and in "s" source file,
        including allocators and unreachable records in call trace

        --no-func=f1 --no-source=s --all
        -> run memory collector with 0.001s sampling,
        excluding allocations in "f1" function and in "s" source file,
        including allocators and unreachable records in call trace

        --no-func=f1 --sampling=1.0
        -> run memory collector with 1.0s sampling,
        excluding allocations in "f1" function,
        excluding allocators and unreachable records in call trace
    """
    include_all = kwargs.get('all', False)
    exclude_funcs = kwargs.get('no_func', None)
    exclude_sources = kwargs.get('no_source', None)

    try:
        profile = parser.parse_log(_tmp_log_filename, executable, sampling)
    except IndexError as i_err:
        log.failed()
        traceback.print_exc()
        return CollectStatus.ERROR, 'Info missing in log file: {}'.format(str(i_err)), {}
    except ValueError as v_err:
        log.failed()
        return CollectStatus.ERROR, 'Wrong format of log file: {}'.format(str(v_err)), {}
    log.done()
    filters.set_global_region(profile)

    if not include_all:
        log.info("Filtering traces: ", end='')
        filters.remove_allocators(profile)
        filters.trace_filter(profile, function=['?'], source=['unreachable'])
        log.done()

    if exclude_funcs or exclude_sources:
        log.info("Excluding functions and sources: ", end='')
        filters.allocation_filter(profile, function=[exclude_funcs], source=[exclude_sources])
        log.done()

    log.info("Clearing records without assigned UID from profile: ", end='')
    filters.remove_uidless_records_from(profile)
    log.done()
    log.newline()

    return CollectStatus.OK, '', {'profile': profile}


@click.command()
@click.option('--sampling', '-s', default=DEFAULT_SAMPLING,
              help='Sets the sampling interval for profiling the allocations.'
              ' I.e. memory snapshots will be collected each <sampling>'
              ' seconds.')
@click.option('--no-source',
              help='Will exclude allocations done from <no_source> file during'
              ' the profiling.')
@click.option('--no-func',
              help='Will exclude allocations done by <no func> function during'
              ' the profiling.')
@click.option('--all', '-a', is_flag=True, default=False,
              help='Will record the full trace for each allocation, i.e. it'
              ' will include all allocators and even unreachable records.')
@click.pass_context
def memory(ctx, **kwargs):
    """Generates `memory` performance profile, capturing memory allocations of
    different types along with target address and full call trace.

    \b
      * **Limitations**: C/C++ binaries
      * **Metric**: `memory`
      * **Dependencies**: ``libunwind.so`` and custom ``libmalloc.so``
      * **Default units**: `B` for `memory`

    The following snippet shows the example of resources collected by `memory`
    profiler. It captures allocations done by functions with more detailed
    description, such as the type of allocation, trace, etc.

    .. code-block:: json

        \b
        {
            "type": "memory",
            "subtype": "malloc",
            "address": 19284560,
            "amount": 4,
            "trace": [
                {
                    "source": "../memory_collect_test.c",
                    "function": "main",
                    "line": 22
                },
            ],
            "uid": {
                "source": "../memory_collect_test.c",
                "function": "main",
                "line": 22
            }
        },

    `Memory` profiles can be efficiently interpreted using :ref:`views-heapmap`
    technique (together with its `heat` mode), which shows memory allocations
    (by functions) in memory address map.

    Refer to :ref:`collectors-memory` for more thorough description and
    examples of `memory` collector.
    """
    runner.run_collector_from_cli_context(ctx, 'memory', kwargs)
