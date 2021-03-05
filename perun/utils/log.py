"""Set of helper function for logging and printing warnings or errors"""

import builtins
import collections
import operator
import logging
import sys
import itertools
import io
import pydoc
import functools
import traceback
import time
import numpy as np

import termcolor

from perun.utils.helpers import first_index_of_attr, str_to_plural, identity
from perun.utils.decorators import static_variables
from perun.utils.helpers import COLLECT_PHASE_ATTRS, CHANGE_COLOURS, CHANGE_STRINGS, \
    DEGRADATION_ICON, OPTIMIZATION_ICON, CHANGE_CMD_COLOUR, CHANGE_TYPE_COLOURS
from perun.utils.structs import PerformanceChange

__author__ = 'Tomas Fiedor'
VERBOSITY = 0
COLOR_OUTPUT = True

# Enum of verbosity levels
VERBOSE_DEBUG = 2
VERBOSE_INFO = 1
VERBOSE_RELEASE = 0

SUPPRESS_WARNINGS = False
SUPPRESS_PAGING = True

# set the logging for the perun
logging.basicConfig(filename='perun.log', level=logging.DEBUG)


def is_verbose_enough(verbosity_peak):
    """Tests if the current verbosity of the log is enough

    :param int verbosity_peak: peak of the verbosity we are testing
    :return: true if the verbosity is enough
    """
    return VERBOSITY >= verbosity_peak


def page_function_if(func, paging_switch):
    """Adds paging of the output to standard stream

    This decorator serves as a pager for long outputs to the standard stream. As a pager currently,
    'less -R' is used. Further extension to Windows and weird terminals without less -R is planned.

    Fixme: Try the paging on windows
    Fixme: Uhm, what about standard error?

    Note that this should be used by itself but by @paged_function() decorator

    :param function func: original wrapped function that will be paged
    :param bool paging_switch: external paging condition, if set to tru the function will not be
        paged
    """
    def wrapper(*args, **kwargs):
        """Wrapper for the original function whose output will be paged

        :param list args: list of positional arguments for original function
        :param dict kwargs: dictionary of key:value arguments for original function
        """
        if SUPPRESS_PAGING or not paging_switch:
            return func(*args, **kwargs)

        # Replace the original standard output with string buffer
        sys.stdout = io.StringIO()

        # Run the original input with positional and key-value arguments
        result = func(*args, **kwargs)

        # Read the caught standard output and then restore the original stream
        sys.stdout.seek(0)
        stdout_str = "".join(sys.stdout.readlines())
        sys.stdout = sys.__stdout__
        pydoc.pipepager(stdout_str, "less -R")

        return result
    return wrapper


def paged_function(paging_switch):
    """The wrapper of the ``page_function_if`` to serve as a decorator, which partially applies the
    paging_switch. This way the function will accept only the function as parameter and can serve as
    decorator.

    :param bool paging_switch: external paging condition, if set to tru the function will not be
    :return: wrapped paged function
    """
    return functools.partial(page_function_if, paging_switch=paging_switch)


def _log_msg(stream, msg, msg_verbosity, log_level):
    """
    If the @p msg_verbosity is smaller than the set verbosity of the logging
    module, the @p msg is printed to the log with the given @p log_level

    Attributes:
        stream(function): streaming function of the type void f(log_level, msg)
        msg(str): message to be logged if certain verbosity is set
        msg_verbosity(int): level of the verbosity of the message
        log_level(int): log level of the message
    """
    if msg_verbosity <= VERBOSITY:
        stream(log_level, msg)


def msg_to_stdout(message, msg_verbosity, log_level=logging.INFO):
    """
    Helper function for the log_msg, prints the @p msg to the stdout,
    if the @p msg_verbosity is smaller or equal to actual verbosity.
    """
    _log_msg(lambda lvl, msg: print("{}".format(msg)), message, msg_verbosity, log_level)


def msg_to_file(msg, msg_verbosity, log_level=logging.INFO):
    """
    Helper function for the log_msg, prints the @p msg to the log,
    if the @p msg_verbosity is smaller or equal to actual verbosity
    """
    _log_msg(logging.log, msg, msg_verbosity, log_level)


def info(msg, end='\n'):
    """
    :param str msg: info message that will be printed only when there is at least lvl1 verbosity
    :param str end:
    """
    print("{}".format(msg), end=end)


def quiet_info(msg):
    """
    :param str msg: info message to the stream that will be always shown
    """
    msg_to_stdout(msg, VERBOSE_RELEASE)


def extract_stack_frame_info(frame):
    """Helper function for returning name and filename from frame.

    Note that this is needed because of fecking differences between Python 3.4 and 3.5

    :param object frame: some fecking frame object
    :return: tuple of filename and function name
    """
    return (frame[0], frame[1]) if isinstance(frame, tuple) else (frame.filename, frame.name)


def print_current_stack(colour='red', raised_exception=None):
    """Prints the information about stack track leading to an event

    Be default this is used in error traces, so the colour of the printed trace is red.
    Moreover, we filter out some of the events (in particular those outside of perun, or
    those that takes care of the actual trace).

    :param str colour: colour of the printed stack trace
    :param Exception raised_exception: exception that was raised before the error
    """
    reduced_trace = []
    trace = traceback.extract_tb(raised_exception.__traceback__) if raised_exception \
        else traceback.extract_stack()
    for frame in trace:
        frame_file, frame_name = extract_stack_frame_info(frame)
        filtering_conditions = [
            # We filter frames that are outside of perun's scope
            'perun' not in frame_file,
            # We filter the first load entry of the module
            frame_name == '<module>',
            # We filter these error and stack handlers ;)
            frame_file.endswith('log.py') and frame_name in ('error', 'print_current_stack')
        ]
        if not any(filtering_conditions):
            reduced_trace.append(frame)
    print(in_color(
        ''.join(traceback.format_list(reduced_trace)), colour
    ), file=sys.stderr)


def error(msg, recoverable=False, raised_exception=None):
    """
    :param str msg: error message printed to standard output
    :param bool recoverable: whether we can recover from the error
    :param Exception raised_exception: exception that was raised before the error
    """
    print(in_color("fatal: {}".format(msg), 'red'), file=sys.stderr)
    if is_verbose_enough(VERBOSE_DEBUG):
        print_current_stack(raised_exception=raised_exception)

    # If we cannot recover from this error, we end
    if not recoverable:
        sys.exit(1)


def warn(msg, end="\n"):
    """
    :param str msg: warn message printed to standard output
    :param str end:
    """
    if not SUPPRESS_WARNINGS:
        print("warning: {}".format(msg), end=end)


def print_current_phase(phase_msg, phase_unit, phase_colour):
    """Print helper coloured message for the current phase

    :param str phase_msg: message that will be printed to the output
    :param str phase_unit: additional parameter that is passed to the phase_msg
    :param str phase_colour: phase colour defined in helpers.py
    """
    print(in_color(
        phase_msg.format(in_color(phase_unit)), phase_colour, COLLECT_PHASE_ATTRS
    ))


@static_variables(current_job=1)
def print_job_progress(overall_jobs):
    """Print the tag with the percent of the jobs currently done

    :param int overall_jobs: overall number of jobs to be done
    """
    percentage_done = round((print_job_progress.current_job / overall_jobs) * 100)
    print("[{}%] ".format(
        str(percentage_done).rjust(3, ' ')
    ), end='')
    print_job_progress.current_job += 1


def cprint(string, colour, attrs='none', flush=True):
    """Wrapper over coloured print without adding new line

    :param str string: string that is printed with colours
    :param str colour: colour that will be used to colour the string
    :param str attrs: name of additional attributes for the colouring
    :param bool flush: set True to immediately perform print operation
    """
    print(in_color(string, colour, attrs), end='', flush=flush)


def cprintln(string, colour, attrs='none'):
    """Wrapper over coloured print with added new line or other ending

    :param str string: string that is printed with colours and newline
    :param str colour: colour that will be used to colour the stirng
    :param str attrs: name of additional attributes for the colouring
    :param str ending: ending of the string, be default new line
    """
    print(in_color(string, colour, attrs))


def done(ending='\n'):
    """Helper function that will print green done to the terminal

    :param str ending: end of the string, by default new line
    """
    print('[', end='')
    cprint("DONE", 'green', attrs='bold')
    print(']', end=ending)


def failed(ending='\n'):
    """
    :param str ending: end of the string, by default new line
    """
    print('[', end='')
    cprint("FAILED", 'red', attrs='bold')
    print(']', end=ending)


def yes(ending='\n'):
    """
    :param str ending: end of the string, by default new line
    """
    print('[', end='')
    cprint('\u2714', 'green', attrs='bold')
    print(']', end=ending)


def no(ending='\n'):
    """
    :param str ending: end of the string, by default new line
    """
    print('[', end='')
    cprint('\u2717', 'red', attrs='bold')
    print(']', end=ending)


def newline():
    """
    Prints blank line
    """
    print("")


def in_color(output, color='white', attribute_style="none"):
    """Transforms the output to colored version.

    :param str output: the output text that should be colored
    :param str color: the color
    :param str attribute_style: name of the additional style, i.e. bold, italic, etc.

    :return str: the new colored output (if enabled)
    """
    attrs = {
        "none": [],
        "bold": ["bold"],
        "underline": ["underline"]
    }.get(attribute_style, [])

    if COLOR_OUTPUT:
        return termcolor.colored(output, color, attrs=attrs)
    else:
        return output


def count_degradations_per_group(degradation_list):
    """Counts the number of optimizations and degradations

    :param list degradation_list: list of tuples of (degradation info, cmdstr, minor version)
    :return: dictionary mapping change strings to its counts
    """
    # Get only degradation results
    changes = map(operator.attrgetter('result'), map(operator.itemgetter(0), degradation_list))
    # Transform the enum into a string
    change_names = list(map(operator.attrgetter('name'), changes))
    counts = dict(collections.Counter(change_names))
    return counts


def get_degradation_change_colours(degradation_result):
    """Returns the tuple of two colours w.r.t degradation results.

    If the change was optimization (or possible optimization) then we print the first model as
    red and the other by green (since we went from better to worse model). On the other hand if the
    change was degradation, then we print the first one green (was better) and the other as red
    (is now worse). Otherwise (for Unknown and no change) we keep the stuff yellow, though this
    is not used at all

    :param PerformanceChange degradation_result: change of the performance
    :returns: tuple of (from model string colour, to model string colour)
    """
    if degradation_result in (
            PerformanceChange.Optimization, PerformanceChange.MaybeOptimization
    ):
        return 'red', 'green'
    elif degradation_result in (
            PerformanceChange.Degradation, PerformanceChange.MaybeDegradation
    ):
        return 'green', 'red'
    else:
        return 'yellow', 'yellow'


def print_short_summary_of_degradations(degradation_list):
    """Prints a short string representing the summary of the found changes.

    This prints a short statistic of found degradations and short summary string.

    :param list degradation_list:
        list of tuples (degradation info, command string, source minor version)
    """
    counts = count_degradations_per_group(degradation_list)

    print_short_change_string(counts)
    optimization_count = counts.get('Optimization', 0)
    degradation_count = counts.get('Degradation', 0)
    print("{}({}), {}({})".format(
        str_to_plural(optimization_count, "optimization"), OPTIMIZATION_ICON,
        str_to_plural(degradation_count, "degradation"), DEGRADATION_ICON
    ))


def change_counts_to_string(counts, width=0):
    """Transforms the counts to a single coloured string

    :param dict counts: dictionary with counts of degradations
    :param int width: width of the string justified to left
    :return: string representing the counts of found changes
    """
    width = max(width - counts.get('Optimization', 0) - counts.get('Degradation', 0), 0)
    change_str = in_color(
        str(OPTIMIZATION_ICON*counts.get('Optimization', 0)),
        CHANGE_COLOURS[PerformanceChange.Optimization],
        'bold'
    )
    change_str += in_color(
        str(DEGRADATION_ICON*counts.get('Degradation', 0)),
        CHANGE_COLOURS[PerformanceChange.Degradation],
        'bold'
    )
    return change_str + width*' '


def print_short_change_string(counts):
    """Prints short string representing a summary of the given degradation list.

    This prints a short string of form representing a summary of found optimizations (+) and
    degradations (-) in the given degradation list. Uncertain optimizations and degradations
    are omitted. The string can e.g. look as follows:

    ++++-----

    :param dict counts: dictionary mapping found string changes into their counts
    """
    overall_changes = sum(counts.values())
    print(str_to_plural(overall_changes, "change"), end='')
    if overall_changes > 0:
        change_string = change_counts_to_string(counts)
        print(" | {}".format(change_string), end='')
    newline()


def _print_models_info(deg_info, model_strategy):
    """
    The function prints information about both models from detection.

    This function prints available information about models at which
    was detected change, according to the applied models strategy.
    Depends on the applied strategy it can logging the type of
    parametric model (e.g. constant, linear, etc.) or kind of
    models (e.g. regressogram, constant, etc.). The function also
    prints information about confidence at detection, i.e. confidence
    rate and confidence type.

    :param DegradationInfo deg_info: structures of found degradations with required information
    :param str model_strategy: detection model strategy for obtains the relevant kind of models
    :return None: function has no return value
    """
    def print_models_kinds(
            baseline_str, baseline_colour, target_str, target_colour, attrs
    ):
        """
        The function format the given parameters to required format at output.

        :param str baseline_str: baseline kind of model (e.g. regressogram, constant, etc.)
        :param str baseline_colour: baseline colour to print baseline string
        :param str target_str: target kind of model (e.g. moving_average, linear, etc.)
        :param str target_colour: target colour to print target string
        :param str attrs: name of type attributes for the colouring
        :return None: function has nor return value
        """
        print(baseline_str, end='')
        cprint('{}'.format(deg_info.from_baseline), colour=baseline_colour, attrs=attrs)
        print(target_str, end='')
        cprint('{}'.format(deg_info.to_target), colour=target_colour, attrs=attrs)

    from_colour, to_colour = get_degradation_change_colours(deg_info.result)

    if model_strategy == 'best-param':
        print_models_kinds(' from: ', from_colour, ' -> to: ', to_colour, 'bold')
    elif model_strategy in ('best-nonparam', 'best-model', 'best-both'):
        print_models_kinds(' base: ', 'blue', ' targ: ', 'blue', 'bold')
    elif model_strategy in ('all-nonparam', 'all-param', 'all-models'):
        print(' model: ', end='')
        cprint('{}'.format(deg_info.from_baseline), colour='blue', attrs='bold')

    if deg_info.confidence_type != 'no':
        print(' (with confidence ', end='')
        cprint(
            '{} = {}'.format(
                deg_info.confidence_type, deg_info.confidence_rate),
            'white', 'bold'
        )
        print(')', end='')


def _print_partial_intervals(partial_intervals):
    """
    The function prints information about detected changes on the partial intervals.

    This function is using only when was used the `local-statistics` detection
    method, that determines the changes on the individual sub-intervals. The
    function prints the range of the sub-interval and the error rate on this
    sub-interval.

    :param np.ndarray partial_intervals: array with partial intervals and all required items
    :return None: function has no return value
    """
    print('  \u2514 ', end='')
    for change_info, rel_error, x_start, x_end in aggregate_intervals(partial_intervals):
        if change_info != PerformanceChange.NoChange:
            cprint(
                "<{}, {}> {}x; ".format(x_start, x_end, rel_error),
                CHANGE_COLOURS.get(change_info, 'white')
            )
    newline()


def print_list_of_degradations(degradation_list, model_strategy="best-model"):
    """Prints list of found degradations grouped by location

    Currently this is hardcoded and prints the list of degradations as follows:

    at {loc}:
      {result} from {from} -> to {to}

    :param list degradation_list: list of found degradations
    :param str model_strategy: detection model strategy for obtains the relevant kind of models
    """
    def keygetter(item):
        """Returns the location of the degradation from the tuple

        :param tuple item: tuple of (degradation result, cmd string, source minor version)
        :return: location of the degradation used for grouping
        """
        return item[0].location

    # Group by location
    degradation_list.sort(key=keygetter)
    for location, changes in itertools.groupby(degradation_list, keygetter):
        # Print the location
        print("at", end='')
        cprint(' {}'.format(location), 'white', attrs='bold')
        print(":")
        # Iterate and print all of the infos
        for deg_info, cmd, __ in changes:
            print('\u2514 ', end='')
            cprint('{}x'.format(round(deg_info.rate_degradation, 2)), 'white', 'bold')
            print(': ', end='')
            cprint(deg_info.type, CHANGE_TYPE_COLOURS.get(deg_info.type, 'white'))
            print(' ', end='')
            cprint(
                '{}'.format(CHANGE_STRINGS[deg_info.result]),
                CHANGE_COLOURS[deg_info.result], 'bold'
            )
            if deg_info.result != PerformanceChange.NoChange:
                _print_models_info(deg_info, model_strategy)

            # Print information about command that was executed
            print(" (", end='')
            cprint("$ {}".format(cmd), CHANGE_CMD_COLOUR, 'bold')
            print(')')

            # Print information about the change on the partial intervals (only at Local-Statistics)
            if deg_info.partial_intervals is not None:
                _print_partial_intervals(deg_info.partial_intervals)
    newline()


def aggregate_intervals(intervals):
    """
    Function aggregates the partial intervals according to the types of change.

    The function aggregates the neighbourly partial intervals when they have the
    same detected type of change. Then the individual intervals are joined since
    in the whole interval are the same kind of the changes. For example, we can
    suppose the following intervals:

        - <0, 1>: Degradation; <1, 2> Degradation; <2, 3>: Optimization;
          <3, 4>: MaybeOptimization; <4, 5>: MaybeOptimization

    Then the resulting aggregated intervals will be the following:

        - <0, 2>: Degradation; <2, 3>: Optimization; <3, 5>: MaybeOptimization

    :param np.ndarray intervals: the array of partial intervals with tuples of required information
    :return list: list of the aggregated partial intervals to print
    """
    def get_indices_of_intervals():
        """
        Function computes the indices of the aggregated intervals.

        The function iterates over the individual partial intervals and aggregates the
        neighbourly intervals when they have the same type of change. When the next
        interval has the different type of change, then the relevant indices of
        aggregated intervals are returned and proceeds to the next iteration.

        :return tuple: function returns the indices of aggregate intervals.
        """
        if intervals.any():
            start_idx, end_idx = 0, 0
            change, _, _, _ = intervals[start_idx]
            for end_idx, (new_change, _, _, _) in enumerate(intervals[1:], 1):
                if change != new_change:
                    yield (start_idx, end_idx - 1)
                    if end_idx == len(intervals) - 1:
                        yield (end_idx, end_idx)
                    change = new_change
                    start_idx = end_idx
            if start_idx != end_idx or len(intervals) == 1:
                yield (start_idx, end_idx)

    intervals = intervals[intervals[:, 0] != PerformanceChange.NoChange]
    agg_intervals = []
    for start_index, end_index in get_indices_of_intervals():
        rel_error = np.sum(intervals[start_index:end_index+1, 1]) / (end_index - start_index + 1)
        agg_intervals.append((
            intervals[start_index][0], np.round(rel_error, 2),
            intervals[start_index][2], intervals[end_index][3]
        ))

    return agg_intervals


def print_elapsed_time(func):
    """Prints elapsed time after the execution of the wrapped function

    Takes the timestamp before the execution of the function and after the execution and prints
    the elapsed time to the standard output.

    :param function func: wrapped function
    :return: function for which we will print the elapsed time
    """
    def inner_wrapper(*args, **kwargs):
        """Inner wrapper of the decorated function

        :param list args: original arguments of the function
        :param dict kwargs: original keyword arguments of the function
        :return: results of the decorated function
        """
        before = time.time()
        results = func(*args, **kwargs)
        elapsed = time.time() - before
        print("[!] {} [{}] in {} [!]".format(
            (func.phase_name if hasattr(func, 'phase_name') else func.__name__).title(),
            in_color("DONE", 'green', 'bold'),
            in_color("{:0.2f}s".format(elapsed), 'white', 'bold')
        ))
        return results
    return inner_wrapper


def scan_formatting_string(fmt, callbacks, callback=identity, default_fmt_callback=None, sep="%"):
    """Scans the string, parses delimited formatting tokens and transforms them w.r.t callbacks

    :param string fmt: formatting string
    :param dict callbacks: list of callbacks to each formatting token, in case there is no default,
        then error is raised.
    :param func callback: callback function for non formatting string tokens
    :param func default_fmt_callback: default callback called for tokens not found in the callbacks
    :param char sep: delimiter for the tokens
    :return: list of transformed tokens
    """
    i = 0
    tokens = []
    current_token = ""
    for character in fmt:
        if character == sep:
            # found start or end of the token
            i += 1
            if i % 2 == 0:
                # token is formatting string
                tokens.append(("fmt_string", default_fmt_callback(current_token)))
            else:
                # token is raw string
                tokens.append(("raw_string", callback(current_token)))
            current_token = ""
        else:
            current_token += character

    # Add what is rest
    if current_token:
        tokens.append(("raw_string", callback(current_token)))

    # TODO: Add check if there is i % 2 == 1 at the end
    return tokens


class History:
    """Helper with wrapper, which is used when one wants to visualize the version control history
    of the project, printing specific stuff corresponding to a git history

    :ivar list unresolved_edges: list of parents that needs to be resolved in the vcs graph,
        for each such parent, we keep one column.
    :ivar bool auto_flush_with_border: specifies whether in auto-flushing the border should be
        included in the output
    :ivar object _original_stdout: original standard output that is saved and restored when leaving
    :ivar function _saved_print: original print function which is replaced with flushed function
        and is restored when leaving the history
    """
    class Edge:
        """Represents one edge of the history

        :ivar str next: the parent of the edge, i.e. the previously processed sha
        :ivar str colour: colour of the edge (red for deg, yellow for deg+opt, green for opt)
        :ivar str prev: the child of the edge, i.e. the not yet processed sha
        """
        def __init__(self, n, colour='white', prev=None):
            """Initiates one edge of the history

            :param str n: the next sha that will be processed
            :param str colour: colour of the edge
            :param str prev: the "parent" of the n
            """
            self.next = n
            self.colour = colour
            self.prev = prev

        def to_ascii(self, char):
            """Converts the edge to ascii representation

            :param str char: string that represents the edge
            :return: string representing the edge in ascii
            """
            return char if self.colour == 'white' \
                else in_color(char, self.colour, 'bold')

    def __init__(self, head):
        """Creates a with wrapper, which keeps and prints the context of the current vcs
        starting at head

        :param str head: head minor version
        """
        self.unresolved_edges = [History.Edge(head)]
        self.auto_flush_with_border = False
        self._original_stdout = None
        self._saved_print = None

    def __enter__(self):
        """When entering, we create a new string io object to catch standard output

        :return: the history object
        """
        # We will get the original standard output with string buffer and handle writing ourselves
        self._original_stdout = sys.stdout
        sys.stdout = io.StringIO()
        self._saved_print = builtins.print

        def flushed_print(print_function, history):
            """Decorates the print_function with automatic flushing of the output.

            Whenever a newline is included in the output, the stream will be automatically flushed

            :param function print_function: function that will include the flushing
            :param History history: history object that takes care of flushing
            :return: decorated flushed print
            """
            def wrapper(*args, **kwargs):
                """Decorator function for flushed print

                :param list args: list of positional arguments for print
                :param dict kwargs: list of keyword arguments for print
                """
                print_function(*args, **kwargs)
                end_specified = 'end' in kwargs.keys()
                if not end_specified or kwargs['end'] == '\n':
                    history.flush(history.auto_flush_with_border)
            return wrapper
        builtins.print = flushed_print(builtins.print, self)
        return self

    def __exit__(self, *_):
        """Restores the stdout to the original state

        :param list _: list of unused parameters
        """
        # Restore the stdout and printing function
        self.flush(self.auto_flush_with_border)
        builtins.print = self._saved_print
        sys.stdout = sys.__stdout__

    def get_left_border(self):
        """Returns the string representing the currently unresolved branches.

        Each unresolved branch is represented as a '|' characters

        The left border can e.g. look as follows:

        | | | | |

        :return: string representing the columns of the unresolved branches
        """
        return " ".join(edge.to_ascii("|") for edge in self.unresolved_edges) + "  "

    def _merge_parents(self, merged_parent):
        """Removes the duplicate instances of the merge parent.

        E.g. given the following parents:

            [p1, p2, p3, p2, p4, p2]

        End we merge the parent p2, the we will obtain the following:

            [p1, p2, p3, p4]

        This is used, when we are outputing the parent p2, and first we merged the branches, print
        the information about p2 and then actualize the unresolved parents with parents of p2.

        :param str merged_parent: sha of the parent that is going to be merged in the unresolved
        """
        filtered_unresolved = []
        already_found_parent = False
        for parent in self.unresolved_edges:
            if parent.next == merged_parent and already_found_parent:
                continue
            already_found_parent = already_found_parent or parent.next == merged_parent
            filtered_unresolved.append(parent)
        self.unresolved_edges = filtered_unresolved

    def _print_minor_version(self, minor_version_info):
        """Prints the information about minor version.

        The minor version is visualized as follows:

         | * | {sha:6} {desc}

        I.e. all of the unresolved parents are output as | and the printed parent is output as *.
        The further we print first six character of minor version checksum and first line of desc

        :param MinorVersion minor_version_info: printed minor version
        """
        minor_str = " ".join(
            "*" if p.next == minor_version_info.checksum else p.to_ascii("|")
            for p in self.unresolved_edges
        )
        print(minor_str, end='')
        cprint(" {}".format(
            minor_version_info.checksum[:6]
        ), 'yellow')
        print(": {} | ".format(
            minor_version_info.desc.split("\n")[0].strip()
        ), end='')

    def progress_to_next_minor_version(self, minor_version_info):
        r"""Progresses the history of the VCS to next minor version

        This flushes the current caught buffer, resolves the fork points (i.e. when we forked the
        history from the minor_version), prints the information about minor version and the resolves
        the merges (i.e. when the minor_version is spawned from the merge). Finally this updates the
        unresolved parents with parents of minor_version.

        Prints the following:

        | | | |/ / /
        | | | * | | sha: desc
        | | | |\ \ \

        :param MinorVersion minor_version_info: information about minor version
        """
        minor_sha = minor_version_info.checksum
        self.flush(with_border=True)
        self.auto_flush_with_border = False
        self._process_fork_point(minor_sha)
        self._merge_parents(minor_sha)
        self._print_minor_version(minor_version_info)

    def finish_minor_version(self, minor_version_info, degradation_list):
        """Notifies that we have processed the minor version.

        Updates the unresolved parents, taints those where we found degradations and processes
        the merge points. Everything is flushed.

        :param MinorVersion minor_version_info: name of the finished minor version
        :param list degradation_list: list of found degradations
        """
        # Update the unresolved parents
        minor_sha = minor_version_info.checksum
        version_index = first_index_of_attr(self.unresolved_edges, 'next', minor_sha)
        self.unresolved_edges[version_index:version_index+1] = [
            History.Edge(p, 'white', minor_sha) for p in minor_version_info.parents
        ]
        self._taint_parents(minor_sha, degradation_list)
        self._process_merge_point(version_index, minor_version_info.parents)

        # Flush the history
        self.flush()
        self.auto_flush_with_border = True

    def flush(self, with_border=False):
        """Flushes the stdout optionally with left border of unresolved parent columns

        If the current stdout is not readable, the flushing is skipped

        :param bool with_border: if true, then every line is printed with the border of unresolved
            parents
        """
        # Unreadable stdouts are skipped, since we are probably in silent mode
        if sys.stdout.readable():
            # flush the stdout
            sys.stdout.seek(0)
            for line in sys.stdout.readlines():
                if with_border:
                    self._original_stdout.write(self.get_left_border())
                self._original_stdout.write(line)

            # create new stringio
            sys.stdout = io.StringIO()

    def _taint_parents(self, target, degradation_list):
        """According to the given list of degradation, sets the parents either as tainted
        or fixed.

        Tainted parents are output with red colour, while fixed parents with green colour.

        :param str target: target minor version
        :param list degradation_list: list of found degradations
        """
        # First we process all of the degradations and optimization
        taints = set()
        fixes = set()
        for deg, _, baseline in degradation_list:
            if deg.result.name == "Degradation":
                taints.add(baseline)
            elif deg.result.name == "Optimization":
                fixes.add(baseline)

        # At last we colour the edges; edges that contain both optimizations and degradations
        # are coloured yellow
        for edge in self.unresolved_edges:
            if edge.prev == target:
                tainted = edge.next in taints
                fixed = edge.next in fixes
                if tainted and fixed:
                    edge.colour = 'yellow'
                elif tainted:
                    edge.colour = 'red'
                elif fixed:
                    edge.colour = 'green'

    def _process_merge_point(self, merged_at, merged_parents):
        r"""Updates the printed tree after we merged list of parents in the given merge_at index.

        This prints up to merged_at unresolved parents, and then creates a merge point (|\) that
        branches of to the length of the merged_parents columns.

        Prints the following:

        | | | * | | sha: desc
        | | | | \ \
        | | | |\ \ \
        | | | | | \ \
        | | | | |\ \ \
        | | | | | | \ \
        | | | | | |\ \ \
        | | | | | | | | |

        :param int merged_at: index, where the merged has happened
        :param list merged_parents: list of merged parents
        """
        parent_num = len(merged_parents)
        rightmost_branches_num = len(self.unresolved_edges) - merged_at - parent_num

        # We output one additional line for better readability; if we process some merges,
        # then we will have plenty of space left, so no need to do the newline
        if parent_num == 1:
            print(self.get_left_border())
        else:
            for _ in range(1, parent_num):
                merged_at += 1
                left_str = " ".join(
                    e.to_ascii("|") for e in self.unresolved_edges[:merged_at]
                )
                right_str = " ".join(
                    e.to_ascii("\\") for e in self.unresolved_edges[-rightmost_branches_num:]
                ) if rightmost_branches_num else ""
                print(left_str + right_str)
                print(left_str + " ".join(
                    [self.unresolved_edges[merged_at].to_ascii('\\'), right_str]
                ))

    def _process_fork_point(self, fork_point):
        """Updates the printed tree after we forked from the given sha.

        Prints the following:

        | | | | | | |
        | | | |/ / /
        | | | * | |

        :param str fork_point: sha of the point, where we are forking
        """
        ulen = len(self.unresolved_edges)
        forked_index = first_index_of_attr(self.unresolved_edges, 'next', fork_point)
        src_index_map = list(range(0, ulen))
        tgt_index_map = [
            forked_index if self.unresolved_edges[i].next == fork_point else i
            for i in range(0, ulen)
        ]

        while src_index_map != tgt_index_map:
            line = list(" "*(max(src_index_map)+1)*2)
            triple_zip = zip(src_index_map, self.unresolved_edges, tgt_index_map)
            for i, (lhs, origin, rhs) in enumerate(triple_zip):
                # for this index we are moving to the left
                diff = -1 if rhs - lhs else 0
                if diff == 0:
                    line[2*lhs] = origin.to_ascii('|')
                else:
                    line[2*lhs-1] = origin.to_ascii('/')
                src_index_map[i] += diff
            print("".join(line))


class Logger:
    """Helper object that logs the stream into isolate string io

    :ivar object original: original stream
    :ivar StringIO log: log saving the stream
    """
    def __init__(self, stream):
        self.original = stream
        self.log = io.StringIO()

    def write(self, message):
        """Writes the message to both streams

        :param object message: written message
        """
        self.original.write(message)
        self.original.flush()
        self.log.write(message)

    def flush(self):
        """Flushes the original stream"""
        self.original.flush()
