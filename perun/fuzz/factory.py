"""Collection of global methods for fuzz testing."""

__author__ = 'Tomas Fiedor, Matus Liscinsky'

import copy
import difflib
import itertools
import os
import os.path as path
import signal
import sys
import threading
import time
from subprocess import CalledProcessError, TimeoutExpired
from uuid import uuid4

import numpy as np
import tabulate

import perun.fuzz.callgraph as cg
import perun.fuzz.filesystem as filesystem
import perun.fuzz.filetype as filetype
import perun.fuzz.interpret as interpret
import perun.fuzz.randomizer as randomizer
import perun.utils as utils
import perun.utils.decorators as decorators
import perun.utils.log as log
from perun.fuzz.evaluate.by_coverage import GCOV_VERSION_W_JSON_FORMAT, compute_vectors_score, Coverage
from perun.fuzz.helpers import div_vectors_piecewise
from perun.fuzz.structs import FuzzingConfiguration, FuzzingProgress, Mutation

# to ignore numpy division warnings
np.seterr(divide='ignore', invalid='ignore')

FP_ALLOWED_ERROR = 0.00001
MAX_FILES_PER_RULE = 100
SAMPLING = 1.0


def compute_safe_ratio(lhs, rhs):
    """Computes safely the ratio between lhs and rhs

    In case the @p rhs is equal to zero, then the ratio is approximated

    :param int lhs: statistic of method
    :param int rhs: overall statistic
    :return: probability for applying
    """
    try:
        ratio = lhs / rhs
        ratio = 0.1 if (ratio < 0.1) else ratio
    except ZeroDivisionError:
        ratio = 1
    return ratio


def get_max_size(seeds, max_size, max_size_ratio, max_size_gain):
    """ Finds out max size among the sample files and compare it to specified
    max size of mutated file.

    :param list seeds: list of paths to sample files and their fuzz history
    :param int max_size: user defined max size of mutated file
    :param max_size_ratio: size specified by percentage
    :param max_size_gain: size to adjunct to max
    :return int: `max_size` if defined, otherwise value depending on adjusting method
                 (percentage portion, adding constant size)
    """
    # gets the largest seed's size
    seed_max = max(path.getsize(seed.path) for seed in seeds)

    # --max option was not specified
    if max_size is None:
        if max_size_ratio is not None:
            return int(seed_max * max_size_ratio)  # percentual adjusting
        else:
            return seed_max + max_size_gain  # adjusting by size(B)

    if seed_max >= max_size:
        log.warn("Warning: Specified max size is smaller than the largest workload.")
    return max_size


def strategy_to_generation_repeats(strategy, rule_set, index):
    """ Function decides how many workloads will be generated using certain fuzz method.

    Strategies:
        - "unitary" - always 1
        - "proportional" - depends on how many degradations was caused by this method
        - "probabilistic" - depends on ratio between: num of degradations caused by this method and
                            num of all degradations yet
        - "mixed" - mixed "proportional" and "probabilistic" strategy

    :param str strategy: determines which strategy for deciding will be used
    :param RuleSet rule_set: stats of fuzz methods
    :param int index: index in list `fuzz_stats` corresponding to stats of actual method
    :return int: number of generated mutations for rule
    """
    if strategy == "unitary":
        return 1
    elif strategy == "proportional":
        return min(int(rule_set.hits[index])+1, MAX_FILES_PER_RULE)
    elif strategy == "probabilistic":
        ratio = compute_safe_ratio(rule_set.hits[index], rule_set.hits[-1])
        rand = randomizer.rand_from_range(0, 10) / 10
        return 1 if rand <= ratio else 0
    elif strategy == "mixed":
        ratio = compute_safe_ratio(rule_set.hits[index], rule_set.hits[-1])
        rand = randomizer.rand_from_range(0, 10) / 10
        return min(int(rule_set.hits[index])+1, MAX_FILES_PER_RULE) if rand <= ratio else 0


def contains_same_lines(lines, fuzzed_lines, is_binary):
    """Compares two string list and check if they are equal.

    :param list lines: lines of original file
    :param list fuzzed_lines: lines fo fuzzed file
    :param bool is_binary: determines whether a files are binaries or not
    :return bool: True if lines are the same, False otherwise
    """
    if is_binary:
        delta = difflib.unified_diff(
            [line.decode('utf-8', errors='ignore') for line in lines],
            [f_line.decode('utf-8', errors='ignore') for f_line in fuzzed_lines]
        )
    else:
        delta = difflib.unified_diff(lines, fuzzed_lines)
    return len(list(delta)) == 0


def fuzz(parent, max_bytes, rule_set, config):
    """ Provides fuzzing on workload parent using all the implemented methods.

    Reads the file and store the lines in list. Makes a copy of the list to send it to every
    single function providing one fuzzing method. With every fuzzing method: creates a new file
    with unique name, but with the same extension. It copies the fuzzing history given by
    `fuzz_history`, append the id of used fuzz method and assign it to the new file. If the new file
    would be bigger than specified limit (`max_bytes`), the remainder is cut off.

    :param Mutation parent: path of parent workload file, which will be fuzzed
    :param RuleSet rule_set: stats of fuzzing (mutation) strategies
    :param int max_bytes: specify maximum size of created file in bytes
    :param FuzzingConfiguration config: configuration of the fuzzing
    :return list: list of tuples(new_file, its_fuzzing_history)
    """

    mutations = []

    is_binary, _ = filetype.get_filetype(parent.path)
    with open(parent.path, "rb") if is_binary else open(parent.path, "r") as fp_in:
        lines = fp_in.readlines()

    # "blank file"
    if len(lines) == 0:
        return []

    # split the file to name and extension
    _, file = path.split(parent.path)
    file, ext = path.splitext(file)

    # fuzzing
    for i, method in enumerate(rule_set.rules):
        for _ in range(strategy_to_generation_repeats(config.mutations_per_rule, rule_set, i)):
            fuzzed_lines = lines[:]
            # calling specific fuzz method with copy of parent
            method[0](fuzzed_lines)

            # compare, whether new lines are the same
            if contains_same_lines(lines, fuzzed_lines, is_binary):
                continue

            # new mutation filename and fuzz history
            mutation_name = file.split("-")[0] + "-" + str(uuid4().hex) + ext
            filename = os.path.join(config.output_dir, mutation_name)
            new_fh = copy.copy(parent.history)
            new_fh.append(i)

            predecessor = parent.predecessor or parent
            mutations.append(Mutation(filename, new_fh, predecessor))

            if is_binary:
                fp_out = open(filename, "wb")
                fp_out.write((b"".join(fuzzed_lines))[:max_bytes])
            else:
                fp_out = open(filename, "w")
                fp_out.write("".join(fuzzed_lines)[:max_bytes])

            fp_out.close()

    return mutations


def print_legend(rule_set):
    """ Prints stats of each fuzzing method.

    :param RuleSet rule_set: selected fuzzing (mutation) strategies and their stats
    """
    log.info("Statistics of rule set")
    log.info(tabulate.tabulate([
        [
            i, rule_set.hits[i], method[1]
        ] for (i, method) in enumerate(rule_set.rules)
    ], headers=["id", "Rule Efficiency", "Description"]))


def print_results(fuzzing_report, fuzzing_config, rule_set, output_dirs, start_timestamp):
    """Prints results of fuzzing.

    :param dict fuzzing_report: general information about current fuzzing
    :param FuzzingConfiguration fuzzing_config: configuration of the fuzzing
    :param RuleSet rule_set: selected fuzzing (mutation) strategies and their stats
    :param dict output_dirs: dictionary of output dirs for distinct files
    :param str start_timestamp: datetime information about the start of fuzzing
    """
    log.info("Fuzzing: ", end="")
    log.done("\n")
    log.info("Fuzzing time: {:.2f}s".format(
        fuzzing_report["end_time"] - fuzzing_report["start_time"]
    ))
    log.info("Coverage testing: {}".format(fuzzing_config.coverage_testing))
    if fuzzing_config.coverage_testing:
        log.info("Program executions for coverage testing: {}".format(
            fuzzing_report["cov_execs"]
        ))
        log.info("Program executions for performance testing: {}".format(
            fuzzing_report["perun_execs"]
        ))
        log.info("Total program tests: {}".format(
            str(fuzzing_report["perun_execs"] + fuzzing_report["cov_execs"])
        ))
        log.info("Maximum coverage ratio: {}".format(
            str(fuzzing_report["max_cov"])
        ))
        if fuzzing_config.new_approach:
            interpret.print_most_affected_paths(fuzzing_config.coverage.callgraph)
            if not fuzzing_config.no_plotting:
                interpret.draw_paths_heatmap(
                    fuzzing_config.coverage.callgraph, output_dirs["graphs"], start_timestamp)

    else:
        log.info("Program executions for performance testing: {}".format(
            fuzzing_report["perun_execs"]
        ))
    log.info("Founded degradation mutations: {}".format(str(fuzzing_report["degradations"])))
    log.info("Hangs: {}".format(str(fuzzing_report["hangs"])))
    log.info("Faults: {}".format(str(fuzzing_report["faults"])))
    log.info("Worst-case mutation: {}".format(str(fuzzing_report["worst_case"])))
    print_legend(rule_set)


def evaluate_workloads(method, phase, *args, **kwargs):
    """ Calls initializing function for `method` testing.

    :param str method: testing method, can be "by_perun" or "by_coverage"
    :param str phase: phase of the evaluation (either baseline or target testing)
    :param list args: list of arguments for testing
    :param dict kwargs: additional information for testing
    :return: result of initial testing depending on `method`
    """
    result = utils.dynamic_module_function_call(
        "perun.fuzz.evaluate", method, phase, *args, **kwargs)
    return result


def rate_parent(fuzz_progress, mutation, new_approach):
    """ Rate the `mutation` with fitness function and adds it to list with fitness values.

    :param FuzzingProgress fuzz_progress: progress of the fuzzing
    :param Mutation mutation: path to a file which is classified as mutation
    :param bool new_approach: variable denoting if we work with the static callgraph (True) in
        coverage analysis or not (False)
    """

    increase_cov_rate = compute_vectors_score(
        mutation, fuzz_progress) if new_approach else mutation.cov / fuzz_progress.base_cov

    fitness_value = increase_cov_rate + mutation.deg_ratio
    mutation.fitness = fitness_value

    # empty list or the value is actually the largest
    if not fuzz_progress.parents or fitness_value >= fuzz_progress.parents[-1].fitness:
        fuzz_progress.parents.append(mutation)
    else:
        for index, parent in enumerate(fuzz_progress.parents):
            if fitness_value <= parent.fitness:
                fuzz_progress.parents.insert(index, mutation)
                break


def update_parent_rate(parents, mutation):
    """ Update rate of the `parent` according to degradation ratio yielded from perf testing.

    :param list parents: sorted list of fitness score of parents
    :param Mutation mutation: path to a file which is classified as parent
    """
    for index, par_fit_val in enumerate(parents):
        if par_fit_val == mutation:
            fitness_value = par_fit_val.fitness * (1 + mutation.deg_ratio)
            del parents[index]
            break

    # if its the best rated yet, we save the program from looping
    if fitness_value >= parents[-1].fitness:
        mutation.fitness = fitness_value
        parents.append(mutation)
        return

    for i in range(index, len(parents)):
        if fitness_value <= parents[i].fitness:
            mutation.fitness = fitness_value
            parents.insert(i, mutation)
            break


def choose_parent(parents, num_intervals=5):
    """ Chooses one of the workload file, that will be fuzzed.

    If number of parents is smaller than intervals, function provides random choice.
    Otherwise, it splits parents to intervals, each interval assigns weight(probability)
    and does weighted interval selection. Then provides random choice of file from
    selected interval.

    :param list parents: list of mutations sorted according to their fitness score
    :param int num_intervals: number of intervals to which parents will be splitted
    :return list: absolute path to chosen file
    """
    num_of_parents = len(parents)
    if num_of_parents < num_intervals:
        return randomizer.rand_choice(parents)

    triangle_num = (num_intervals*num_intervals + num_intervals) / 2
    bottom = 0
    tresh = int(num_of_parents/num_intervals)
    top = tresh
    intervals = []
    weights = []

    # creates borders of intervals
    for i in range(num_intervals):
        # remainder
        if num_of_parents - top < tresh:
            top = num_of_parents
        intervals.append((bottom, top))
        weights.append((i+1)/triangle_num)
        bottom = top
        top += tresh

    # choose an interval
    interval_idx = np.random.choice(range(num_intervals), replace=False, p=weights)
    # choose a parent from the interval
    return randomizer.rand_choice(parents[intervals[interval_idx][0]:intervals[interval_idx][1]])


def save_fuzz_state(time_series, state):
    """Saves current state of fuzzing for plotting.

    :param TimeSeries time_series: list of data for x-axis (typically time values) and y-axis
    :param state: current value of measured variable
    """
    if len(time_series.y_axis) > 1 and state == time_series.y_axis[-2]:
        time_series.x_axis[-1] += SAMPLING
    else:
        time_series.x_axis.append(time_series.x_axis[-1] + SAMPLING)
        time_series.y_axis.append(state)


def teardown(fuzz_progress, output_dirs, parents, rule_set, config):
    """Teardown function at the end of the fuzzing, either by natural rundown of timeout or because
    of unnatural circumstances (e.g. exception)

    :param FuzzingProgress fuzz_progress: Progress of the fuzzing process
    :param dict output_dirs: dictionary of output dirs for distinct files
    :param list parents: list of parents
    :param RuleSet rule_set: list of fuzzing methods and their stats
    :param FuzzingConfiguration config: configuration of the fuzzing
    """
    log.info("Executing teardown of the fuzzing. ")
    if not config.no_plotting:
        # Plot the results as time series
        log.info("Plotting time series of fuzzing process...")
        interpret.plot_fuzz_time_series(
            fuzz_progress.deg_time_series,
            path.join(
                output_dirs["graphs"], fuzz_progress.start_timestamp + "_degradations_ts.pdf"),
            "Fuzzing in time", "time (s)", "degradations"
        )
        if config.coverage_testing:
            interpret.plot_fuzz_time_series(
                fuzz_progress.cov_time_series,
                path.join(
                    output_dirs["graphs"], fuzz_progress.start_timestamp + "_coverage_ts.pdf"),
                "Max path during fuzing", "time (s)", "executed lines ratio"
            )
    # Plot the differences between seeds and inferred mutation
    interpret.files_diff(fuzz_progress, output_dirs["diffs"])
    # Save log files
    interpret.save_log_files(output_dirs["logs"], fuzz_progress)
    # Clean-up remaining mutations
    filesystem.del_temp_files(parents, fuzz_progress, config.output_dir)

    fuzz_progress.stats["end_time"] = time.time()
    fuzz_progress.stats["worst_case"] = fuzz_progress.parents[-1].path
    print_results(fuzz_progress.stats, config, rule_set, output_dirs, fuzz_progress.start_timestamp)
    log.done()
    sys.exit(0)


def process_successful_mutation(mutation, parents, fuzz_progress, rule_set, config):
    """If the @p mutation is successful during the evaluation, we update the parent queue
    @p parents, as well as statistics for given rule in rule_set and stats stored in fuzzing
    progress.

    :param Mutation mutation: sucessfully evaluated mutation
    :param FuzzingProgress fuzz_progress: collective state of fuzzing
    :param list parents: list of parents, i.e. mutations which will be furter mutated
    :param RuleSet rule_set: set of applied rules
    :param FuzzingConfiguration config: configuration of the fuzzing
    """
    rule_set.hits[mutation.history[-1]] += 1
    rule_set.hits[-1] += 1
    # without cov testing we firstly rate the new parents here
    if not config.coverage_testing:
        parents.append(mutation)
        rate_parent(fuzz_progress, mutation, config.new_approach)
    # for only updating the parent rate
    else:
        update_parent_rate(fuzz_progress.parents, mutation)

    # appending to final results
    fuzz_progress.final_results.append(mutation)
    fuzz_progress.stats["degradations"] += 1


def save_state(fuzz_progress):
    """Saves the state of the fuzzing at given time and schedules next save after SAMPLING time

    :param FuzzingProgress fuzz_progress:
    """
    save_fuzz_state(fuzz_progress.deg_time_series, fuzz_progress.stats["degradations"])
    save_fuzz_state(fuzz_progress.cov_time_series, fuzz_progress.stats["max_cov"])

    timer = threading.Timer(SAMPLING, lambda: save_state(fuzz_progress),)
    timer.daemon = True
    timer.start()


def perform_baseline_coverage_testing(executable, parents, config):
    """Performs the baseline testing for the coverage

    :param Executable executable: tested executable
    :param list parents: list of parents
    :param FuzzingConfig config: configuration of the fuzzing process
    :return: base coverage of parents
    """
    base_cov = 0
    log.info("Performing coverage-based testing on parent seeds", end=" ")
    try:
        # Note that evaluate workloads modifies config as sideeffect
        base_cov = evaluate_workloads(
            "by_coverage", "baseline_testing", executable, parents, config
        )
        log.done()
    except TimeoutExpired:
        log.error(
            "Timeout ({}s) reached when testing with initial files. Adjust hang timeout using"
            " option --hang-timeout, resp. -h.".format(config.hang_timeout)
        )
    return base_cov


@log.print_elapsed_time
@decorators.phase_function('fuzz performance')
def run_fuzzing_for_command(executable, input_sample, collector, postprocessor, minor_version_list,
                            **kwargs):
    """Runs fuzzing for a command w.r.t initial set of workloads

    :param Executable executable: called command with arguments
    :param list input_sample: initial sample of workloads for fuzzing
    :param str collector: collector used to collect profiling data
    :param list postprocessor: list of postprocessors, which are run after collection
    :param list minor_version_list: list of minor version for which we are collecting
    :param dict kwargs: rest of the keyword arguments
    """

    # Initialization
    config = FuzzingConfiguration(**kwargs)
    fuzz_progress = FuzzingProgress(config)

    output_dirs = filesystem.make_output_dirs(
        config.output_dir, ["hangs", "faults", "diffs", "logs", "graphs"]
    )

    # getting workload corpus
    parents = filesystem.get_corpus(input_sample, config.workloads_filter)
    # choosing appropriate fuzzing methods
    rule_set = filetype.choose_ruleset(parents[0].path, config.regex_rules)

    # getting max size for generated mutations
    max_bytes = get_max_size(parents, config.max_size, config.max_size_ratio, config.max_size_gain)

    # Init coverage testing with seeds
    if config.coverage_testing:
        if config.new_approach:
            # get callgraph of project
            config.coverage.callgraph = cg.initialize(executable, config.coverage.source_path)
        fuzz_progress.base_cov = perform_baseline_coverage_testing(executable, parents, config)

    # No gcno files were found, no coverage testing
    if not fuzz_progress.base_cov:
        # avoiding possible further zero division
        fuzz_progress.base_cov = Coverage([], []) if config.new_approach else 1
        config.coverage_testing = False
        log.warn("No .gcno files were found.")

    log.info("Performing perun-based testing on parent seeds", end=" ")
    # Init performance testing with seeds
    base_result_profile = evaluate_workloads(
        "by_perun", "baseline_testing", executable, parents, collector, postprocessor,
        minor_version_list, **kwargs
    )
    log.done()

    log.info("Rating parents ", end='')
    # Rate seeds
    for parent_seed in parents:
        rate_parent(fuzz_progress, parent_seed, config.new_approach)
        log.info('.', end='')
    log.done()

    save_state(fuzz_progress)
    fuzz_progress.stats["start_time"] = time.time()

    # SIGINT (CTRL-C) signal handler
    def signal_handler(sig, _):
        log.warn("Fuzzing process interrupted by signal {}...".format(sig))
        teardown(fuzz_progress, output_dirs, parents, rule_set, config)

    signal.signal(signal.SIGINT, signal_handler)

    # MAIN LOOP
    while (time.time() - fuzz_progress.stats["start_time"]) < config.timeout:
        # Gathering interesting workloads
        if config.coverage_testing:
            log.info("Gathering interesting workloads using coverage based testing", end=" ")
            execs = config.exec_limit

            while len(fuzz_progress.interesting_workloads) < config.precollect_limit and execs > 0:
                current_workload = choose_parent(fuzz_progress.parents)
                mutations = fuzz(current_workload, max_bytes, rule_set, config)

                for mutation in mutations:
                    try:
                        execs -= 1
                        fuzz_progress.stats["cov_execs"] += 1
                        # testing for coverage
                        result = evaluate_workloads(
                            "by_coverage", "target_testing", executable, mutation, collector,
                            postprocessor, minor_version_list, callgraph=config.coverage.callgraph,
                            config=config, fuzzing_progress=fuzz_progress,
                            base_cov=fuzz_progress.base_cov, parent=current_workload, **kwargs
                        )
                    # error occured
                    except CalledProcessError:
                        fuzz_progress.stats["faults"] += 1
                        mutation.path = filesystem.move_file_to(
                            mutation.path, output_dirs["faults"]
                        )
                        fuzz_progress.faults.append(mutation)
                        result = True
                    # timeout expired
                    except TimeoutExpired:
                        fuzz_progress.stats["hangs"] += 1
                        log.warn("Timeout ({}s) reached when testing. See {}.".format(
                            config.hang_timeout, output_dirs["hangs"]
                        ))
                        mutation.path = filesystem.move_file_to(
                            mutation.path, output_dirs["hangs"]
                        )
                        fuzz_progress.hangs.append(mutation)
                        continue

                    # if successful mutation
                    if result:
                        rate_parent(fuzz_progress, mutation, config.new_approach)
                        fuzz_progress.update_max_coverage(config.new_approach)
                        parents.append(mutation)
                        fuzz_progress.interesting_workloads.append(mutation)
                        log.info('.', end="")
                        rule_set.hits[mutation.history[-1]] += 1
                        rule_set.hits[-1] += 1
                    # not successful mutation or the same file as previously generated
                    else:
                        os.remove(mutation.path)
            log.done()

            # adapting increase coverage ratio
            config.refine_coverage_rate(fuzz_progress.interesting_workloads)

        # not coverage testing, only performance testing
        else:
            current_workload = choose_parent(fuzz_progress.parents)
            fuzz_progress.interesting_workloads = fuzz(
                current_workload, max_bytes, rule_set, config
            )

        log.info("Evaluating gathered mutations")
        for mutation in fuzz_progress.interesting_workloads:
            # creates copy of generator
            base_result_profile, base_copy = itertools.tee(base_result_profile)

            # testing with perun
            sucessful_result = False
            try:
                fuzz_progress.stats["perun_execs"] += 1
                sucessful_result = evaluate_workloads(
                        "by_perun", "target_testing", executable, mutation,
                        collector, postprocessor, minor_version_list, base_result=base_copy,
                        **kwargs
                )
                if sucessful_result:
                    process_successful_mutation(mutation, parents, fuzz_progress, rule_set, config)
            # in case of testing with coverage, parent wont be removed but used for mutation
                elif not config.coverage_testing:
                    os.remove(mutation.path)

            # temporarily we ignore error within individual perf testing without previous cov test
            except Exception as exc:
                log.warn("Executing binary raised an exception: {}".format(exc))

        # deletes interesting workloads for next run
        log.done()
        del fuzz_progress.interesting_workloads[:]

    # get end time
    fuzz_progress.stats["end_time"] = time.time()

    teardown(fuzz_progress, output_dirs, parents, rule_set, config)
