"""Collction of helpers structures for fuzzing"""

import copy
import os
import time
from collections import namedtuple

import numpy as np
from angr.codenode import BlockNode, HookNode

# for cross-reference table using cflow
from perun.fuzz.evaluate.by_coverage import (GCOV_VERSION_W_JSON_FORMAT, compute_vectors_score,
                                             execute_bin, get_gcov_version, Coverage)

__author__ = 'Tomas Fiedor, Matus Liscinsky'


TimeSeries = namedtuple("TimeSeries", "x_axis y_axis")
RuleSet = namedtuple("RuleSet", "rules hits")


class Mutation:
    """
    :ivar str path: path to the workload
    :ivar list history: list of predecessors
    :ivar Mutation predecessor: predecessor of the mutation (form which we mutated)
    :ivar int cov: achieved coverage
    :ivar int deg_ratio: achieved degradation ration
    :ivar float fitness: fitness of the mutation
    """

    def __init__(self, path, history, predecessor, cov=0, deg_ratio=0, fitness=0):
        """
        :param str path: path to the workload
        :param list history: list of predecessors
        :param Mutation predecessor: predecessor of the mutation (form which we mutated)
        :param int cov: achieved coverage
        :param int deg_ratio: achieved degradation ration
        :param float fitness: fitness of the mutation
        """
        self.path = path
        self.history = history
        self.predecessor = predecessor
        self.cov = cov
        self.deg_ratio = deg_ratio
        self.fitness = fitness


class CoverageConfiguration:
    """Configuration of the coverage testing

    :ivar str gcno_path: path to the directory, where .gcno files are stored
    :ivar str source_path: path to the directory, where source codes are stored
    :ivar str gcov_path: path to the directory, where building was executed and gcov should be too
    :ivar int gcov_version: version of the gcov utility
    :ivar list gcov_files: list of gcov files
    :ivar list source_files: list of source files
    :ivar CallGraph callgraph: struct of the target application callgraph
    """

    def __init__(self, **kwargs):
        """
        :param dict kwargs: set of keyword configurations
        """
        self.gcno_path = kwargs['gcno_path']
        self.source_path = kwargs['source_path']
        self.gcov_path = kwargs['gcov_path']
        self.gcov_version = get_gcov_version()
        self.gcov_files = []
        self.source_files = []
        self.callgraph = None


class FuzzingConfiguration:
    """Collection of (mostly persistent) configuration of the fuzzing process

    This encapsulates all of the possibly used configurations to be passed around functions, in
    order to reduce the number of local variables and parameters.

    :ivar int timeout: specifies how long the fuzzing should be running
    :ivar int hang_timeout: specifies how long the tested program should run with the mutations
    :ivar str output_dir: directory, where resulting logs, workloads etc. are generated
    :ivar str workloads_filter: regular expression used to filter workloads
    :ivar list regex_rules: list of user defined rules (described by regular expressions
    :ivar int max: maximal size of the generated workloads in B
    :ivar int max_size_ratio: maximal percentual increase in the size of the workloads
    :ivar int max_size_gain: the maximal increase in size of the mutated workload, in comparison
        with input seeds.
    :ivar int exec_limit: limit to number of execution of number of mutation per fuzzing loop
    :ivar int precollect_limit: limit for number of generated mutations per fuzzing loop
    :ivar str mutations_per_rule: strategy used for determining how many workloads will be generated
        per mutation rule.
    :ivar bool no_plotting: specifies if the result of the fuzzing should be plotted by graphs
    :ivar int cov_rate: threshold for the increase of the
    :ivar bool coverage_testing: specifies if the mutations should be tested for coverage also,
        or only using perun
    :ivar CoverageConfiguration coverage
    :ivar bool new_approach: variable denoting if we work with the static callgraph (True) in
        coverage analysis
    """

    def __init__(self, **kwargs):
        """
        :param dict kwargs: set of keyword configurations
        """
        self.timeout = kwargs['timeout']
        self.hang_timeout = kwargs['hang_timeout']
        self.output_dir = os.path.abspath(kwargs['output_dir'])
        self.workloads_filter = kwargs['workloads_filter']
        self.regex_rules = kwargs['regex_rules']
        self.max_size = kwargs.get('max', None)
        self.max_size_ratio = kwargs.get("max_size_ratio", None)
        self.max_size_gain = kwargs.get("max_size_gain")
        self.exec_limit = kwargs['exec_limit']
        self.precollect_limit = kwargs["interesting_files_limit"]
        self.mutations_per_rule = kwargs["mutations_per_rule"]
        self.no_plotting = kwargs['no_plotting']
        self.cov_rate = kwargs['coverage_increase_rate']
        self.coverage_testing = (kwargs.get("source_path") and
                                 kwargs.get("gcno_path") and
                                 kwargs.get("gcov_path")) is not None
        self.coverage = CoverageConfiguration(**kwargs)
        self.new_approach = self.coverage_testing and kwargs['new_approach'] and \
            self.coverage.gcov_version >= GCOV_VERSION_W_JSON_FORMAT

    RATIO_INCR_CONST = 0.05
    RATIO_DECR_CONST = 0.01

    def refine_coverage_rate(self, found_workloads):
        """Refines the coverage rate according to so far founded interesting workloads

        :param list found_workloads: list of interesting workloads
        """
        if found_workloads:
            self.cov_rate += FuzzingConfiguration.RATIO_INCR_CONST
        elif self.cov_rate > FuzzingConfiguration.RATIO_DECR_CONST:
            self.cov_rate -= FuzzingConfiguration.RATIO_DECR_CONST


class FuzzingProgress:
    """Collection of statistics and states used during fuzzing

    :ivar list faults: list of workloads leading to faults
    :ivar list hangs: list of workloads leading to hangs
    :ivar list interesting_workloads: list of potentially interesting workloads
    :ivar list parents: list of fitness values for parents
    :ivar list final_results: list of final results
    :ivar dict stats: additional stats of fuzz testing
    :ivar str start_timestamp: datetime information about the start of fuzzing
    """

    def __init__(self, config):
        """
        :param FuzzingConfiguration config: configuration of the fuzzing
        """
        self.faults = []
        self.hangs = []
        self.interesting_workloads = []
        self.parents = []
        self.final_results = []
        self.start_timestamp = time.strftime(
            "%Y-%m-%d-%H-%M-%S", time.localtime())

        # Time series plotting
        self.deg_time_series = TimeSeries([0], [0])
        self.cov_time_series = TimeSeries([0], [1.0])

        self.base_cov = 1
        if config.coverage_testing:
            if config.new_approach and config.coverage.gcov_version is not None and \
               config.coverage.gcov_version >= GCOV_VERSION_W_JSON_FORMAT:
                # new approach is used only when JSON gcov output is available
                self.base_cov = Coverage([], [])

        self.stats = {
            "start_time": 0.0,
            "end_time": 0.0,
            "cov_execs": 0,
            "perun_execs": 0,
            "degradations": 0,
            "max_cov": 1.0,
            "worst_case": None,
            "hangs": 0,
            "faults": 0
        }

    def update_max_coverage(self, new_approach):
        """Updates the maximal achieved coverage according to the parent fitness values

        :param bool new_approach: variable denoting if we work with the static callgraph (True) in
        coverage analysis
        """
        self.stats["max_cov"] = compute_vectors_score(
            self.parents[-1], self) if new_approach else self.parents[-1].cov / self.base_cov


class CallGraph:
    """Struct representing static callgraph of the target application.

    :ivar dict functions: dictionary of callgraph functions
    :ivar list _unique_paths: list of all unique paths from the root function all leaf nodes
    :ivar list _current_path: curren chain of functions in the process of building the callgraph
    :ivar Function root: main function of the CFG generated by the `angr` framework
        (this Function is `angr` class)
    :ivar dict references: mapping of source code lines to calls of the functions
    :ivar list path_effectivity: success of unique paths
        (how many times coverage of the certain path has sufficiently raised)
    """

    def __init__(self, root, kb):
        """
        :param root: main function of the CFG generated by the `angr` framework
        :param kb: knowledge base of the project object
        """
        self.functions = dict()
        self._unique_paths = []
        self._current_path = Path()
        self.root = self.create(root, kb)
        self.references = dict()
        self.path_effectivity = [0]*len(self._unique_paths)

    def create(self, root, kb):
        """Recursive function that creates callgraph.

        :param root: main function of the CFG generated by the `angr` framework
        :param kb: knowledge base of the project object
        :return CallGraph : struct of the target application callgraph
        """
        if isinstance(root, BlockNode):
            return None
        elif isinstance(root, HookNode):
            # leaves
            if root.addr in kb.functions:
                hook_function = kb.functions[root.addr]
                new_root = Function(hook_function.name, hook_function.addr)
                new_root.leaf_node = True

                self._current_path.append_function(new_root)
                self.functions[new_root.name] = new_root
                self._unique_paths.append(Path.from_path(self._current_path))
                self._current_path.pop_function()
                return new_root
            return None
        else:
            # it's a function
            # check if its in the path already, if true, it is a recursive function
            if self._current_path.contains_funtion(root):
                self.functions[root.name].recursive = True
                return root
            # already processed function (function doesn't have to be in the current path, but can be already processed)
            if root.name in self.functions:
                return None
            # else, not recursive and not processed function
            else:
                new_root = Function(root.name, root.addr)
                self.functions[new_root.name] = new_root
            self._current_path.append_function(new_root)

            for fun in root.nodes:
                if fun.addr == root.addr and not isinstance(fun, BlockNode):
                    if not isinstance(fun, HookNode):
                        new_root.recursive = True
                    continue
                subtree_root = self.create(fun, kb)
                # this function was seen
                if subtree_root == fun:
                    new_root.leaf_node = True
                    self._unique_paths.append(
                        Path.from_path(self._current_path))
                # note: subtree can be None in case of BlockNode in CFG
                elif subtree_root:
                    new_root.add_node(subtree_root)
            if not new_root.nodes:
                self._unique_paths.append(Path.from_path(self._current_path))
            self._current_path.pop_function()
            return new_root

    def identify_lib_functions(self, source_files):
        """Uses cflow utility in order to find system library function calls and label
            these functions.

        :param list source_files: list of source file's paths
        """
        user_defined_functions = []
        command = ["cflow", "-x"]
        command.extend(source_files)
        output = execute_bin(command)
        for func_call in output["output"].split("\n"):
            if not func_call:  # note that empty string is at the end of output
                continue
            func_name = func_call.split(
            )[0] if func_call.split() else ""  # function name
            if func_name in user_defined_functions:
                continue
            elif "*" in func_call:
                user_defined_functions.append(func_name)
                continue
            else:
                try:
                    function_obj = self.functions[func_name]
                    function_obj.is_lib = True
                    self.add_reference((func_call.split()[-1]), function_obj)
                except KeyError:
                    pass

    def add_reference(self, location, obj):
        """Adds reference of the function in the references dictionary.

        :param str location: path of the source file followed by the ':' and a line number
        :param Function obj: function object of the function called in the @p location
        """
        if self.references:
            try:
                self.references[location].append(obj)
            except KeyError:
                self.references.update([(location, [obj])])
        else:
            self.references = {location: [obj]}

    def update_paths_effectivity(self, paths_results, inc_coverage_increase, exc_coverage_increase):
        """Updates the effectivity of the callgraph unique paths, plus updates their max reached
            coverage ratio.

        :param tuple paths_results: zipped results of comparisions with baseline and parent workload
        :param list inc_coverage_increase: inclusive coverage increase of the paths
        :param list exc_coverage_increase: exclusive coverage increase of the paths
        """
        for i, (cmp_with_baseline_inc, cmp_with_baseline_exc,
                cmp_with_parent_inc, cmp_with_parent_exc) in enumerate(paths_results):
            if cmp_with_baseline_inc and cmp_with_parent_inc or cmp_with_baseline_exc and cmp_with_parent_exc:
                self.path_effectivity[i] += 1
                self._unique_paths[i].effectivity += 1
            self._unique_paths[i].update_max_cov(
                inc_coverage_increase[i],
                exc_coverage_increase[i]
            )


class Function:
    """Class that represents callgraph node --- function.

    :ivar str name: name of the function
    :ivar int addr: address of the function
    :ivar list nodes: descendants of the function in the callgraph
    :ivar list parents: parents of the function in the callgraph
    :ivar bool recursive: variable denoting whether the function is recursive
    :ivar bool leaf_node: variable denoting whether the node is a leaf in the callgraph
    :ivar bool is_lib: variable denoting whether the function is from system libraries
    :ivar dict references: dictionary of the function calls
    """

    def __init__(self, name, addr, nodes=[], parents=[]):
        """

        :param name: name of the function
        :param addr: address of the function
        :param nodes: descendants of the function in the callgraph, defaults to []
        :param parents: parents of the function in the callgraph, defaults to []
        """
        self.name = name
        self.addr = addr
        self.nodes = nodes
        self.parents = parents
        self.recursive = False
        self.leaf_node = False
        # for lib functions
        self.is_lib = False

    def add_node(self, node):
        """Adds node to the function descendands.

        :param Function node: function/node to be added
        """
        if self.nodes:
            self.nodes.append(node)
        else:
            self.nodes = [node]

    # def to_string(self):
    #     """Function for debugging purposes only.
    #     """
    #     print(self.name, self.addr, "recursive:", self.recursive,
    #           "leaf_node:", self.leaf_node, "nodes:", len(self.nodes))


class Path:
    """Class representing a path in the callgraph.
    :ivar list func_chain: chain of functions
    :ivar int effectivity: the effectivity of the path
    :ivar float max_inc_cov_increase: maximum increase in inclusive coverage of the path
        during fuzzing
    :ivar float max_exc_cov_increase: maximum increase in exclusive coverage of the path
        during fuzzing
    """

    def __init__(self, func_chain=None, effectivity=0, max_inc_cov_increase=1.0, max_exc_cov_increase=1.0):
        """
        :ivar list func_chain: chain of functions
        :ivar int effectivity: the effectivity of the path
        :ivar float max_inc_cov_increase: maximum increase in inclusive coverage of the path
            during fuzzing
        :ivar float max_exc_cov_increase: maximum increase in exclusive coverage of the path
            during fuzzing
        """
        self.func_chain = func_chain if func_chain else []
        self.effectivity = effectivity
        self.max_inc_cov_increase = max_inc_cov_increase
        self.max_exc_cov_increase = max_exc_cov_increase

    # copy constructor
    @classmethod
    def from_path(Path, path_instance):
        """Function is a copy constructor of Path.

        :param path_instance: instance of the path to be copied
        :return Path: new Path instance
        """
        # deepcopy
        func_chain = copy.deepcopy(
            path_instance.func_chain)
        return Path(
            func_chain, path_instance.effectivity,
            path_instance.max_inc_cov_increase, path_instance.max_exc_cov_increase)

    def update_max_cov(self, inc_cov_incr, exc_cov_incr):
        """Updates max reached coverages.

        :param inc_cov_incr: reached inclusive coverage increase
        :param exc_cov_incr: reached exclusive coverage increase
        """
        self.max_inc_cov_increase = max(
            self.max_inc_cov_increase, inc_cov_incr)
        self.max_exc_cov_increase = max(
            self.max_exc_cov_increase, exc_cov_incr)

    def contains_funtion(self, function):
        """Decides whether the function is already in the function chain.

        :param function: object of `angr` function, which address we looking for in the chain
        :return bool: True if the function is in the function chain, False otherwise
        """
        # note: here, function is an instance of angr function class
        for fun in self.func_chain:
            if fun.addr == function.addr:
                return True
        return False

    def append_function(self, function):
        """Appends function at the end of the function chain.

        :param Function function: function to be appended
        """
        # note: here, function is an instance of our function class
        self.func_chain.append(function)

    def pop_function(self):
        """Pops function from the end of the function chain.
        """
        self.func_chain.pop()

    def to_string(self):
        """Function that converts function chain into formatted string.

        :return: formatted string from a Path object
        """
        return "->".join([func.name for func in self.func_chain])
