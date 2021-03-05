"""Set of helper constants and helper named tuples for perun pcs"""
import os
import re
import operator
import collections
import signal

from perun.utils.structs import PerformanceChange
from perun.utils.exceptions import SignalReceivedException, NotPerunRepositoryException

__author__ = 'Tomas Fiedor'

# File system specific
READ_CHUNK_SIZE = 1024

# Other constants
MAXIMAL_LINE_WIDTH = 60
TEXT_ATTRS = 'none'
TEXT_EMPH_COLOUR = 'green'
TEXT_WARN_COLOUR = 'red'
AGGREGATIONS = "sum", "mean", "count", "nunique", "median", "min", "max"

# Minor Version specific things
MinorVersion = collections.namedtuple("MinorVersion", "date author email checksum desc parents")
MajorVersion = collections.namedtuple("MajorVersion", "name head")

# Profile specific stuff
SUPPORTED_PROFILE_TYPES = ['memory', 'mixed', 'time']
PROFILE_MALFORMED = 'malformed'
PROFILE_TYPE_COLOURS = {
    'time': 'blue',
    'mixed': 'cyan',
    'memory': 'white',
    PROFILE_MALFORMED: 'red'
}
PROFILE_DELIMITER = '|'

HEADER_ATTRS = 'underline'
HEADER_COMMIT_COLOUR = 'green'
HEADER_INFO_COLOUR = 'white'
HEADER_SLASH_COLOUR = 'white'

DESC_COMMIT_COLOUR = 'white'
DESC_COMMIT_ATTRS = 'darkbold'

# Raw output specific thing
RAW_KEY_COLOUR = 'magenta'
RAW_ITEM_COLOUR = 'yellow'
RAW_ATTRS = 'none'

# Job specific
COLLECT_PHASE_CMD = 'blue'
COLLECT_PHASE_WORKLOAD = 'cyan'
COLLECT_PHASE_COLLECT = 'magenta'
COLLECT_PHASE_POSTPROCESS = 'yellow'
COLLECT_PHASE_ERROR = 'red'
COLLECT_PHASE_ATTRS = 'none'
COLLECT_PHASE_ATTRS_HIGH = 'none'

# Degradation specific
CHANGE_CMD_COLOUR = 'magenta'
CHANGE_STRINGS = {
    PerformanceChange.Degradation: 'Degradation',
    PerformanceChange.MaybeDegradation: 'Maybe Degradation',
    PerformanceChange.NoChange: 'No Change',
    PerformanceChange.Unknown: 'Unknown',
    PerformanceChange.MaybeOptimization: 'Maybe Optimization',
    PerformanceChange.Optimization: 'Optimization'
}
CHANGE_COLOURS = {
    PerformanceChange.Degradation: 'red',
    PerformanceChange.MaybeDegradation: 'yellow',
    PerformanceChange.NoChange: 'white',
    PerformanceChange.Unknown: 'grey',
    PerformanceChange.MaybeOptimization: 'cyan',
    PerformanceChange.Optimization: 'green'
}
CHANGE_TYPE_COLOURS = {
    'time': 'blue',
    'mixed': 'cyan',
    'memory': 'white',
}
DEGRADATION_ICON = '-'
OPTIMIZATION_ICON = '+'
LINE_PARSING_REGEX = re.compile(
    r"(?P<location>.+)\s"
    r"PerformanceChange[.](?P<result>[A-Za-z]+)\s"
    r"(?P<type>\S+)\s"
    r"(?P<from>\S+)\s"
    r"(?P<to>\S+)\s"
    r"(?P<drate>\S+)\s"
    r"(?P<ctype>\S+)\s"
    r"(?P<crate>\S+)\s"
    r"(?P<minor>\S+)\s"
    r"(?P<cmdstr>.+)"
)


def first_index_of_attr(tuple_list, attr, value):
    """Helper function for getting the first index of value in list of tuples

    :param list tuple_list: list of tuples
    :param str attr: name of the attribute we are getting
    :param value: lookedup value
    :return: index of the tuple or exception
    :raises: ValueError when there is no object/tuple with attribute with given value
    """
    list_of_attributes = list(map(operator.attrgetter(attr), tuple_list))
    return list_of_attributes.index(value)


def uid_getter(uid):
    """Helper function for getting the order priority of the uid

    By default the highest priority is the executed binary or command,
    then file and package structure, then modules, objects, concrete functions
    or methods, on lines up to instruction. If we encounter unknown key, then we
    use some kind of lexicographic sorting

    :param tuple uid: the part of the uid
    :return: the rank of the uid in the ordering
    """
    uid_priority = {
        'bin': 0,
        'file': 1, 'source': 1, 'package': 1,
        'module': 2,
        'class': 3, 'struct': 3, 'structure': 3,
        'function': 4, 'func': 4, 'method': 4, 'procedure': 4,
        'line': 5,
        'instruction': 6
    }
    max_value = max(uid_priority.values())
    return uid_priority.get(
        uid[0],
        int("".join(map(str, map(lambda x: x+max_value, map(ord, uid[0])))))
    )


class SuppressedExceptions:
    """Context manager class for code blocks that need to suppress / ignore some exceptions
    and simply continue in the execution if those exceptions are encountered.

    :ivar list exc: the list of exception classes that should be ignored
    """
    def __init__(self, *exception_list):
        """
        :param exception_list: the exception classes to ignore
        """
        self.exc = exception_list

    def __enter__(self):
        """Context manager entry sentinel, no set up needed

        :return object: the context manager class instance, shouldn't be needed
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit sentinel, check if the code raised an exception and if the
        exception belongs to the list of suppressed exceptions.

        :param type exc_type: the type of the exception
        :param exception exc_val: the value of the exception
        :param traceback exc_tb: the exception traceback
        :return bool: True if the encountered exception should be ignored, False otherwise or if
                      no exception was raised
        """
        return isinstance(exc_val, tuple(self.exc))


def str_to_plural(count, verb):
    """Helper function that returns the plural of the string if count is more than 1

    :param int count: number of the verbs
    :param str verb: name of the verb we are creating a plural for
    """
    return str(count) + " " + verb + "s" if count != 1 else verb


def format_counter_number(count, max_number):
    """Helper function that returns string formatted to number of places given by the lenght of max
    counter number.

    :param int count: the current number of the counter
    :param int max_number: the maximal number of counter
    :return:
    """
    return "{:{decimal_width}d}".format(
        count, decimal_width=len(str(max_number))
    )


class HandledSignals:
    """Context manager for code blocks that need to handle one or more signals during their
    execution.

    The CM offers a default signal handler and a default handler exception. In this scenario, the
    code execution is interrupted when the registered signals are encountered and - if provided -
    a callback function is invoked.

    After the callback, previous signal handlers are re-registered and the CM ends. If an exception
    not related to the signal handling was encountered, it is re-raised after resetting the signal
    handlers and (if set) invoking the callback function.

    The callback function prototype is flexible, and the required arguments can be supplied by
    the callback_args parameter. However, it should always accept the **kwargs arguments because
    of the exc_type, exc_val and exc_tb arguments provided by the __exit__ function. This allows
    the programmer to decide e.g. if certain parts of the callback code should be executed, based
    on the raised exception - or the lack of an exception, that is.

    A custom signal handler function can be supplied. In this case, the prototype should oblige
    the rules of signal handling functions: func_name(signal_number, frame). If the custom signal
    handling function uses a different exception then the default, it should be supplied to the CM
    as well.

    :ivar list signals: the list of signals that are being handled by the CM
    :ivar function handler: the function used to handle the registered signals
    :ivar exception handler_exc: the exception type related to the signal handler
    :ivar function callback: the function that is always invoked during the CM exit
    :ivar list callback_args: arguments for the callback function
    :ivar list old_handlers: the list of previous signal handlers

    """
    def __init__(self, *signals, **kwargs):
        """
        :param signals: the identification of the handled signal, 'signal.SIG_' is recommended
        :param kwargs: additional properties of the context manager
        """
        self.signals = signals
        self.handler = kwargs.get('handler', default_signal_handler)
        self.handler_exc = kwargs.get('handler_exception', SignalReceivedException)
        self.callback = kwargs.get('callback')
        self.callback_args = kwargs.get('callback_args', [])
        self.old_handlers = []

    def __enter__(self):
        """ The CM entry sentinel, register the new signal handlers and store the previous ones.

        :return object: the CM instance
        """
        for sig in self.signals:
            self.old_handlers.append(signal.signal(sig, self.handler))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """ The CM exit sentinel, perform the callback and reset the signal handlers.

        :param type exc_type: the type of the exception
        :param exception exc_val: the value of the exception
        :param traceback exc_tb: the exception traceback
        :return bool: True if the encountered exception should be ignored, False otherwise or if
                      no exception was raised
        """
        # Ignore all the handled signals temporarily
        for sig in self.signals:
            signal.signal(sig, signal.SIG_IGN)
        # Perform the callback
        if self.callback:
            self.callback(*self.callback_args, exc_type=exc_type, exc_val=exc_val, exc_tb=exc_tb)
        # Reset the signal handlers
        for sig, sig_handler in zip(self.signals, self.old_handlers):
            signal.signal(sig, sig_handler)
        # Re-raise exceptions not related to signal handling done by the CM (e.g., SignalReceivedE.)
        return isinstance(exc_val, self.handler_exc)


def default_signal_handler(signum, frame):
    """Default signal handler used by the HandledSignals CM.

    The function attempts to block any subsequent handler invocation of the same signal by ignoring
    the signal. Thus, there should be no further interrupts by the same signal until the __exit__
    sentinel is reached (where all the handled signals are then temporarily ignored during
    the callback).

    However, this will still not block any other signals than the initially encountered one, since
    the default handler doesn't have means to find out all the signals that are being handled by
    a specific CM instance and should be thus ignored.

    To block all the signals handled by a certain HandledSignals context manager, a custom handler
    should be constructed in such a way that all the handled signals are set to signal.SIG_IGN.

    :param int signum: representation of the signal that caused the handler to be invoked
    :param object frame: the frame / stack trace object
    """
    signal.signal(signum, signal.SIG_IGN)
    raise SignalReceivedException(signum, frame)


def is_variable_len_dict(list_value):
    """This tests for a case when list_value is a list with dictionaries containing name and list_value
    keys only.

    This the case, e.g. for coefficients of models.

    :param list list_value: object we are testing
    :return: true if list_value is variable length dictionary
    """
    return len(list_value) and all(
        isinstance(v, dict) and set(v.keys()) == {'name', 'value'} for v in list_value
    )


def get_key_with_aliases(dictionary, key_aliases, default=None):
    """Safely returns the key in the dictionary that has several aliases.

    This function assures the backward compatibility with older profiles, after renaming the keys.

    :param dict dictionary: dictionary
    :param tuple key_aliases: tuple of aliases of the same key in the dictionary, ordered
        according to the order of the versions
    :param object default: default value that is returned if none of the aliases is found in
        the dictionary
    :return: value of the key in the dictionary
    :raises KeyError: if default is set to None and none of the keys in key_aliases is in the dict
    """
    for key in key_aliases:
        if key in dictionary.keys():
            return dictionary[key]
    if default is not None:
        return default
    raise KeyError("None of the keys {} found in the dictionary".format(key_aliases))


def escape_ansi(line):
    """Escapes the font/colour ansi characters in the line

    Based on: https://stackoverflow.com/a/38662876

    :param str line: line with ansi control characters
    :return: ansi control-free string
    """
    ansi_escape = re.compile(r'(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]')
    return ansi_escape.sub('', line)


def touch_file(touched_filename, times=None):
    """
    Corresponding implementation of touch inside python.
    Courtesy of:
    http://stackoverflow.com/questions/1158076/implement-touch-using-python

    :param str touched_filename: filename that will be touched
    :param time times: access times of the file
    """
    with open(touched_filename, 'a'):
        os.utime(touched_filename, times)


def touch_dir(touched_dir):
    """
    Touches directory, i.e. if it exists it does nothing and
    if the directory does not exist, then it creates it.

    :param str touched_dir: path that will be touched
    """
    if not os.path.exists(touched_dir):
        os.makedirs(touched_dir)


def path_to_subpaths(path):
    """Breaks path to all the subpaths, i.e. all of the prefixes of the given path.

    >>> path_to_subpaths('/dir/subdir/subsubdir')
    ['/dir', '/dir/subdir', '/dir/subdir/subsubdir']

    :param str path: path separated by os.sep separator
    :returns list: list of subpaths
    """
    components = path.split(os.sep)
    return [os.sep + components[0]] + \
           [os.sep.join(components[:till]) for till in range(2, len(components) + 1)]


def locate_perun_dir_on(path):
    """Locates the nearest perun directory

    Locates the nearest perun directory starting from the @p path. It walks all of the
    subpaths sorted by their lenght and checks if .perun directory exists there.

    :param str path: starting point of the perun dir search
    :returns str: path to perun dir or "" if the path is not underneath some underlying perun
        control
    """
    # convert path to subpaths and reverse the list so deepest subpaths are traversed first
    lookup_paths = path_to_subpaths(path)[::-1]

    for tested_path in lookup_paths:
        if os.path.isdir(tested_path) and '.perun' in os.listdir(tested_path):
            return tested_path
    raise NotPerunRepositoryException(path)


def try_convert(value, list_of_types):
    """Tries to convert a value into one of the specified types

    :param object value: object that is going to be converted to one of the types
    :param list list_of_types: list or tuple of supported types
    :return: converted value or value, if conversion failed for all of the types
    """
    for checked_type in list_of_types:
        with SuppressedExceptions(Exception):
            return checked_type(value)
    return value


def identity(*args):
    """Identity function, that takes the arguments and return them as they are

    Note that this is used as default transformator for to be used in arguments for transforming
    the data.

    :param list args: list of input arguments
    :return: non-changed list of arguments
    """
    # Unpack the tuple if it is single
    return args if len(args) > 1 else args[0]
