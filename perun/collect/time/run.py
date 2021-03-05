"""A wrapper of the classical time linux utility.

Time collects the runtime of given commands with repetition of the measurements. First we do a
several warm-up executions, followed by the actual timing.
"""

import sys
import time as systime
import click

import perun.utils.log as log
import perun.logic.runner as runner
import perun.utils as utils
import perun.utils.helpers as helpers
from perun.utils.structs import CollectStatus

__author__ = 'Tomas Fiedor'

TIME_TYPES = ('real', 'user', 'sys')


def collect(executable, repeat=10, warmup=3, **kwargs):
    """Times the runtime of the given command, with stated repeats.

    :param Executable executable: executed command, with arguments and workloads
    :param int warmup: number of warm-up pahses, i.e. number of times the binary will be run, but
        the resulting collection will not be stored
    :param int repeat: number of repeats of the the timing, by default 10
    :param dict kwargs: dictionary with key, value options
    :return:
    """
    log.info('Executing the warmup-phase ', end='')
    for timing in range(0, warmup):
        command = " ".join(['time -p', str(executable)]).split(' ')
        utils.get_stdout_from_external_command(command).split('\n')
        print('.', end='')
        sys.stdout.flush()
    log.newline()

    log.info('Begin timing of {} {}'.format(
        executable.cmd, helpers.str_to_plural(repeat, "time")
    ), end='')
    times = []

    before_timing = systime.time()
    for timing in range(1, repeat + 1):
        command = " ".join(['time -p', str(executable)]).split(' ')
        collected_data = utils.get_stdout_from_external_command(command).split('\n')

        times.extend([
            (timing, t[0], t[1]) for t in map(lambda x: x.split(' '), collected_data)
            if len(t) == 2 and t[0] in TIME_TYPES
        ])
        log.info('.', end='')
        sys.stdout.flush()
    log.newline()
    overall_time = systime.time() - before_timing

    return CollectStatus.OK, "", {'profile': {
        "global": {
            "timestamp": overall_time,
            "resources": [
                {
                    "amount": float(timing),
                    "uid": executable.cmd,
                    "order": order,
                    "subtype": key,
                    "type": "time",
                } for (order, key, timing) in times
            ]
        }
    }}


@click.command()
@click.option('--warmup', '-w', 'warmup',
              default=3, nargs=1, type=click.INT, metavar='<int>',
              help='Before the actual timing, the collector will execute <int> warm-up executions.')
@click.option('--repeat', '-r',
              default=10, nargs=1, type=click.INT, metavar='<int>',
              help='The timing of the given binaries will be repeated <int> times.')
@click.pass_context
def time(ctx, **kwargs):
    """Generates `time` performance profile, capturing overall running times of
    the profiled command.

    \b
      * **Limitations**: `none`
      * **Metric**: running `time`
      * **Dependencies**: `none`
      * **Default units**: `s`

    This is a wrapper over the ``time`` linux unitility and captures resources
    in the following form:

    .. code-block:: json

        \b
        {
            "amount": 0.59,
            "type": "time",
            "subtype": "sys",
            "uid": cmd
            "order": 1
        }

    Refer to :ref:`collectors-time` for more thorough description and examples
    of `trace` collector.
    """
    runner.run_collector_from_cli_context(ctx, 'time', kwargs)
