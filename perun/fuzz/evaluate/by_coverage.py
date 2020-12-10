"""Module for providing coverage-based testing.

Collects functions for preparing the workspace before testing (so it removes remaining files),
collecting source files, initial and common testing and gathering coverage information by
executing gcov tool and parsing its output.
"""

__author__ = 'Matus Liscinsky'

import gzip
import json
import os
import os.path as path
import statistics
import subprocess
from collections import namedtuple

import numpy as np

import perun.fuzz.helpers as helpers
import perun.utils.log as log

Coverage = namedtuple('Coverage', 'inclusive exclusive')

GCOV_VERSION_W_INTERMEDIATE_FORMAT = 4.9
GCOV_VERSION_W_JSON_FORMAT = 9
# EVALUATING_STRATEGY = 2
PROGRAM_ERROR_SIGNALS = {
    "8": "SIGFPE",
    "4": "SIGILL",
    "11": "SIGSEGV",
    "10": "SIGBUS",
    "7": "SIGBUS",
    "6": "SIGABRT",
    "12": "SIGSYS",
    "31": "SIGSYS",
    "5": "SIGTRAP"
}


def prepare_workspace(gcno_path, gcov_path):
    """Prepares workspace for yielding coverage information using gcov.

    The .gcda file is generated when a program containing object files built with the GCC
    -fprofile-arcs() option is executed. We use --coverage which is used to compile and link code
    instrumented for coverage analysis. The option is a synonym for -fprofile-arcs -ftest-coverage
    (when compiling) and -lgcov (when linking).
    A separate .gcda file is created for each object file compiled with this option. It contains arc
    transition counts, and some summary information. Files with coverage data created using gcov
    utility have extension .gcov.
    Before meaningful testing, residual .gcda and .gcov files have to be removed.

    :param str gcno_path: path to the dir with source files, where coverage info files are stored
    :param str gcov_path: path to the directory, where building was executed and gcov should be too
    """
    for file in os.listdir(gcno_path):
        if file.endswith(".gcda"):
            os.remove(path.join(gcno_path, file))

    for file in os.listdir(gcov_path):
        if file.endswith(".gcov") or file.endswith(".gcov.json.gz"):
            os.remove(path.join(gcov_path, file))


def execute_bin(command, timeout=None, stdin=None):
    """Executes command with certain timeout.

    :param list command: command to be executed
    :param int timeout: if the process does not end before the specified timeout,
                        the process is terminated
    :param handle stdin: the command input as a file handle
    :return dict: exit code and output string
    """
    command = list(filter(None, command))
    try:
        process = subprocess.Popen(
            command, stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        output, _ = process.communicate(timeout=timeout)
        exit_code = process.wait()

    except subprocess.TimeoutExpired:
        process.terminate()
        raise

    if exit_code != 0 and str(-exit_code) in PROGRAM_ERROR_SIGNALS:
        return {"exit_code": (-exit_code), "output": PROGRAM_ERROR_SIGNALS[str(-exit_code)]}
    return {"exit_code": 0, "output": output.decode('utf-8')}


def get_src_files(source_path):
    """ Gathers all C/C++ source files in the directory specified by `source_path`

    C/C++ files are identified with extensions: .c, .cc, .cpp. All these types of files located in
    source directory are collected together.

    :param str source_path: path to directory with source files
    :return list: list of source files (their absolute paths) located in `source_path`
    """
    sources = []

    for root, _, files in os.walk(source_path):
        if files:
            sources.extend([
                path.join(path.abspath(root), filename) for filename in files
                if path.splitext(filename)[-1] in [".c", ".cpp", ".cc"]
            ])

    return sources


def get_gcov_version():
    """Returns current gcov version installed in the system.
    """
    gcov_output = execute_bin(["gcov", "--version"])
    return int((gcov_output["output"].split("\n")[0]).split()[2][0])


def baseline_testing(executable, workloads, config, **_):
    """ Coverage based testing initialization. Wrapper over function `get_initial_coverage`.

    :param Executable executable: called command with arguments
    :param list workloads: workloads for initial testing
    :param FuzzingConfiguration config: configuration of the fuzzing
    :param dict _: additional information about paths to .gcno files and source files
    :return tuple: median of measured coverages, paths to .gcov files, paths to source_files
    """
    # get source files (.c, .cc, .cpp)
    config.coverage.source_files = get_src_files(config.coverage.source_path)
    return get_initial_coverage(executable, workloads, config)


def get_initial_coverage(executable, seeds, config):
    """ Provides initial testing with initial samples given by user.

    :param Executable executable: called command with arguments
    :param list seeds: initial sample files
    :param FuzzingConfiguration config: configuration of the fuzzing
    :return int or Coverage: median of measured coverages
    """
    coverages = []

    # run program with each seed
    for seed in seeds:
        prepare_workspace(config.coverage.gcno_path,
                          config.coverage.gcov_path)

        command = " ".join([path.abspath(executable.cmd),
                            executable.args, seed.path]).split(' ')

        exit_report = execute_bin(command, config.hang_timeout)
        if exit_report["exit_code"] != 0:
            log.error("Initial testing with file " + seed.path +
                      " caused " + exit_report["output"])
        seed.cov = get_coverage_info(os.getcwd(), config)

        coverages.append(seed.cov)

    # new approach
    if config.new_approach:
        inc_median = helpers.median_vector([vecs[0] for vecs in coverages])
        exc_median = helpers.median_vector([vecs[1] for vecs in coverages])
        return Coverage(inc_median, exc_median)

    return int(statistics.median(coverages))


def target_testing(executable, workload, *_, callgraph=None, config=None, parent=None, fuzzing_progress=None, **__):
    """
    Testing function for coverage based fuzzing. Before testing it prepares the workspace
    using `prepare_workspace` func, executes given command and `get_coverage_info` to
    obtain coverage information.

    :param Executable executable: called command with arguments
    :param Mutation workload: currently tested mutation
    :param CallGraph callgraph: struct of the target application callgraph
    :param FuzzingConfiguration config: configuration of the fuzzing
    :param Mutation parent: parent we are mutating
    :param FuzzingProgress fuzzing_progress: progress of the fuzzing process
    :param list _: additional information containing base result and path to .gcno files
    :param dict __: additional information containing base result and path to .gcno files
    :return int: Greater coverage of the two (base coverage, just measured coverage)
    """
    prepare_workspace(config.coverage.gcno_path, config.coverage.gcov_path)
    command = executable

    command = " ".join([command.cmd, command.args, workload.path]).split(' ')

    exit_report = execute_bin(command, config.hang_timeout)
    if exit_report["exit_code"] != 0:
        log.error(
            "Testing with file " + workload.path +
            " caused " + exit_report["output"],
            recoverable=True
        )
        raise subprocess.CalledProcessError(exit_report, command)

    # if new apprach is enabled, result is stored as namedtuple Coverage,
    # otherwise coverage information represents number of source lines executions
    workload.cov = get_coverage_info(os.getcwd(), config)
    return evaluate_coverage(
        fuzzing_progress, workload, parent, callgraph, config.new_approach, config.cov_rate
    )


def get_gcov_files(directory):
    """ Searches for gcov files in `directory`.
    :param str directory: path of a directory, where searching will be provided
    :return list: absolute paths of found gcov files
    """
    gcov_files = []
    for file in os.listdir(directory):
        if path.isfile(file) and (file.endswith("gcov") or file.endswith("gcov.json.gz")):
            gcov_file = path.abspath(path.join(directory, file))
            gcov_files.append(gcov_file)
    return gcov_files


def parse_line(line, coverage_config):
    """

    :param str line: one line in coverage info
    :param CoverageConfiguration coverage_config: configuration of the coverage
    :return: coverage info from one line
    """
    try:
        # intermediate text format
        if coverage_config.gcov_version >= GCOV_VERSION_W_INTERMEDIATE_FORMAT and "lcount" in line:
            return int(line.split(",")[1])
        # standard gcov file format
        elif coverage_config.gcov_version < GCOV_VERSION_W_INTERMEDIATE_FORMAT:
            return int(line.split(":")[0])
        else:
            return 0
    except ValueError:
        return 0


def parse_gcov_JSON(json_gcov_data):
    """Returns sum of executed lines from `gcov` output in JSON format.

    :param dict json_gcov_data: JSON document as Python object
    :return int: sum of executed lines recorded in @p json_gcov_data
    """
    sum = 0
    for file in json_gcov_data['files']:
        for line in file['lines']:
            sum += line['count']
    return sum


def get_vectors_from_gcov_JSON(json_gcov_data, callgraph):
    """Returns inclusive and exclusive coverage vectors according to the callgraph paths and
    coverage report obtained by `gcov` utility.

    :param dict json_gcov_data: JSON document as Python object
    :param CallGraph callgraph: struct of the target application callgraph
    :return tuple: two integer lists (vectors) carrying coverage information about the cg paths
    """
    inclusive_execs = dict()
    exclusive_execs = dict()
    try:
        cwd = json_gcov_data['current_working_directory']
        for file in json_gcov_data['files']:
            file_path = path.join(cwd, file["file"])
            # counts executed lines in functions (INCLUSIVE coverage),
            # and also system library function calls (EXCLUSIVE coverage)
            for line in file['lines']:
                func_name = line["function_name"]
                if func_name in inclusive_execs:
                    inclusive_execs[func_name] += (int)(line['count'])
                else:
                    inclusive_execs[func_name] = (int)(line['count'])
                try:
                    # library functions in reference table
                    for func_call in callgraph.references[file_path + ":" + str(line["line_number"])]:
                        if func_call.name in exclusive_execs:
                            exclusive_execs[func_call.name] += (
                                int)(line['count'])
                        else:
                            exclusive_execs[func_call.name] = (
                                int)(line['count'])
                except KeyError:
                    pass
            # counts function calls (the ones that are not from system libraries)
            for func in file['functions']:
                func_name = func["name"]
                exclusive_execs[func_name] = (int)(func['execution_count'])
    except KeyError:
        return [], []
    return vectors_from_paths(inclusive_execs, exclusive_execs, callgraph)


def vectors_from_paths(inclusive_execs, exclusive_execs, callgraph):
    """Returns coverage indicators of our new approach (inclusive and exclusive coverage of the
    callgraph paths)from the dictonaries created from gcov output in `get_vectors_from_gcov_JSON` f.

    :param dict inclusive_execs: dictonary with the function names and their inclusive coverage data
    :param dict exclusive_execs: dictonary with the function names and their exclusive coverage data
    :param CallGraph callgraph: struct of the target application callgraph
    :return tuple: two integer lists (vectors) carrying coverage information about the cg paths
    """
    inclusive_vector = []
    exclusive_vector = []
    for i, path in enumerate(callgraph._unique_paths):
        inclusive_vector.append(0)
        exclusive_vector.append(0)
        for func in path.func_chain:
            if func.name in inclusive_execs:
                inclusive_vector[i] += inclusive_execs[func.name]
            if func.name in exclusive_execs:
                exclusive_vector[i] += exclusive_execs[func.name]

    return inclusive_vector, exclusive_vector


def get_coverage_info(cwd, config):
    """ Executes gcov utility with source files, and gathers all output .gcov files.

    First of all, it changes current working directory to directory specified by
    `source_path` and then executes utility gcov over all source files.
    By execution, .gcov files was created as output in intermediate text format("-i") if possible.
    Otherwise, standard gcov output file format  will be parsed.
    Current working directory is now changed back.

    :param str cwd: current working directory for changing back
    :param FuzzingConfiguration config: configuration of the fuzzing
    :return int, list, list: overall count of executed lines, inclusive vector, exclusive vector
    """
    os.chdir(config.coverage.gcov_path)

    if config.coverage.gcov_version >= GCOV_VERSION_W_INTERMEDIATE_FORMAT:
        command = ["gcov", "-i", "-o", config.coverage.gcno_path]
    else:
        command = ["gcov", "-o", config.coverage.gcno_path]
    command.extend(config.coverage.source_files)
    execute_bin(command)

    # searching for gcov files, if they are not already known
    if not config.coverage.gcov_files:
        config.coverage.gcov_files = get_gcov_files(".")

    execs = 0
    inc_vec = []
    exc_vec = []
    # parse every gcov output file
    for gcov_file in config.coverage.gcov_files:
        # JSON format
        if config.coverage.gcov_version >= GCOV_VERSION_W_JSON_FORMAT:
            with gzip.GzipFile(gcov_file, "r") as gcov_fp:
                data = json.loads(gcov_fp.read().decode('utf-8'))
                # old approach using JSON
                if not config.new_approach:
                    execs += parse_gcov_JSON(data)
                # new approach
                else:
                    new_inc, new_exc = get_vectors_from_gcov_JSON(
                        data, config.coverage.callgraph)
                    inc_vec = helpers.sum_vectors_piecewise(inc_vec, new_inc)
                    exc_vec = helpers.sum_vectors_piecewise(exc_vec, new_exc)
        # not JSON format (older gcov version)
        else:
            with open(gcov_file, "r") as gcov_fp:
                for line in gcov_fp:
                    execs += parse_line(line, config.coverage)
    os.chdir(cwd)
    return Coverage(inc_vec, exc_vec) if config.new_approach else execs


def evaluate_coverage(base, workload, parent, callgraph, new_approach, increase_ratio=1.5):
    """ Condition for adding mutated input to set of candidates(parents).

    :param FuzzingProgress base: struct containing information about baseline coverage
    :param Mutation workload: currently tested mutation
    :param Mutation parent: parent we are mutating
    :param CallGraph callgraph: struct of the target application callgraph
    :param bool new_approach: variable denoting if we work with the static callgraph (True)
        or use our previous approach of handling with the coverage data (False)
    :param int increase_ratio: desired coverage increase ration between `base_cov` and `cov`
    :return bool: True if the workload coverage is sufficient enough, False otherwise
    """

    # new approach
    if new_approach:
        return evaluate_by_vectors(base, workload, parent, increase_ratio, callgraph)

    tresh_cov = int(base.base_cov * increase_ratio)
    return workload.cov > tresh_cov and workload.cov > parent.cov


def evaluate_by_vectors(base, workload, parent, increase_ratio, callgraph):
    """ Decides whether the mutation represented by the @p workload is interesting for us,
    by comparing its inclusive and exclusive coverage information.

    :param FuzzingProgress base: struct containing information about baseline coverage
    :param Mutation workload: currently tested mutation
    :param Mutation parent: parent we are mutating
    :param float increase_ratio: treshold ratio between baseline and new workload coverages
    :param CallGraph callgraph: struct of the target application callgraph
    :return bool: True if the coverage associated with the @p workload is sufficient, False otherwise
    """
    # compare each individual path (coverage) with baseline, plus compute ratio between baseline and workload coverage
    cmp_with_baseline_inc, inc_coverage_increase = zip(
        *[(c > b*increase_ratio, c/b) for c, b in zip(workload.cov.inclusive, base.base_cov.inclusive)])
    cmp_with_baseline_exc, exc_coverage_increase = zip(
        *[(c > b*increase_ratio, c/b) for c, b in zip(workload.cov.exclusive, base.base_cov.exclusive)])

    # compare each individual path (coverage) with parent
    cmp_with_parent_inc = [c > p for c, p in zip(
        workload.cov.inclusive, parent.cov.inclusive)]
    cmp_with_parent_exc = [c > p for c, p in zip(
        workload.cov.exclusive, parent.cov.exclusive)]

    # update max coverage increase of paths (for collecting the information about most affected paths)
    callgraph.update_paths_effectivity(
        zip(cmp_with_baseline_inc, cmp_with_baseline_exc,
            cmp_with_parent_inc, cmp_with_parent_exc),
        inc_coverage_increase, exc_coverage_increase)

    # 2. evalutation strategy: briefly, we search for at least one coverage increase
    # in both (parent, baseline) inclusive comparision or in both (parent, baseline) exclusive comparision
    return any(cmp_with_baseline_inc) and any(cmp_with_parent_inc) or \
        any(cmp_with_baseline_exc) and any(cmp_with_parent_exc)


def compute_vectors_score(mutation, fuzz_progress):
    """Function computes coverage part of the mutation fitness score using its coverage vectors.

    :param Mutation mutation: a mutation we compute score for

    :return float: average change compared to baseline vectors
    """
    change_vector_inc = helpers.div_vectors_piecewise(
        mutation.cov.inclusive, fuzz_progress.base_cov.inclusive)
    change_vector_exc = helpers.div_vectors_piecewise(
        mutation.cov.exclusive, fuzz_progress.base_cov.exclusive)
    # average of change vectors
    return (np.average(change_vector_exc) + np.average(change_vector_inc)) / 2
