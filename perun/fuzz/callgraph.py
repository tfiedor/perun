"""Module used for our representation of callgraph using `angr` framework."""

__author__ = 'Matus Liscinsky'

import angr
import matplotlib.pyplot as plt
import numpy as np

import perun.fuzz.structs as structs
import perun.utils.log as log
from perun.fuzz.evaluate.by_coverage import get_src_files


def initialize(executable, source_path):
    """Creates callgraph of the target application.

    It uses `angr` to obtain CFG of the target application, then it goes from the main function
    throughout the functions in CFG in order to build a static callgraph. At the end, it identifies
    functions from system libraries, which is important for further work with the exclusive coverage
    information of these functions.

    :param Executable executable: executable profiled command
    :param str source_path: path to the directory, where source codes are stored
    :return CallGraph: struct of the target application callgraph
    """
    log.info("Generating CFG (angr) ")

    # Creating project object
    proj = angr.Project(executable.cmd, load_options={'auto_load_libs': False})

    # Obtaining Control-Flow-Graph
    cfg = proj.analyses.CFGFast(normalize=True)

    # Main function
    main_obj = proj.loader.main_object.get_symbol("main")
    main_func = cfg.kb.functions[main_obj.rebased_addr]

    log.done()
    log.info("Extracting information to create callgraph ", end='')

    # Building and filling our callgraph representation
    cg = structs.CallGraph(main_func, proj.kb)

    # Search for functions from system libraries
    src_files = get_src_files(source_path)
    cg.identify_lib_functions(src_files)

    log.done()
    return cg
