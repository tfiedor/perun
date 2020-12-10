""" Module contains functions dedicated for various operations over files and directories in
file system, helpful for fuzzing process."""

__author__ = 'Matus Liscinsky'

import os
import os.path as path
import re

from perun.fuzz.structs import Mutation
import perun.utils.log as log
import perun.utils.helpers as helpers


def get_corpus(workloads, pattern):
    """ Iteratively search for files to fill input corpus.

    :param list workloads: list of paths to sample files or directories of sample files
    :param str pattern: regular expression for filtering the workloads
    :return list: list of dictonaries, dictionary contains information about file
    """
    init_seeds = []

    try:
        filter_regexp = re.compile(pattern)
    except re.error:
        filter_regexp = re.compile("")

    for workload in workloads:
        if path.isdir(workload) and os.access(workload, os.R_OK):
            for root, _, files in os.walk(workload):
                if files:
                    init_seeds.extend([
                        Mutation(
                            path.join(path.abspath(root), filename), [], None
                        ) for filename in files if filter_regexp.match(filename)
                    ])
        else:
            init_seeds.append(Mutation(path.abspath(workload), [], None))
    return init_seeds


def move_file_to(filename, directory):
    """Useful function for moving file to the special output directory.

    :param str filename: path to a file
    :param str directory: path of destination directory, where file should be moved
    :return str: new path of the moved file
    """
    _, file = path.split(filename)
    os.rename(filename, os.path.join(directory, file))
    return os.path.join(directory, file)


def make_output_dirs(output_dir, new_dirs):
    """Creates special output directories for diffs and mutations causing fault or hang.

    :param str output_dir: path to user-specified output directory
    :param list new_dirs: names of new directories
    :return list: paths to newly created directories
    """
    dirs_dict = {}
    for dir_name in new_dirs:
        os.makedirs(os.path.join(output_dir, dir_name), exist_ok=True)
        dirs_dict[dir_name] = os.path.join(output_dir, dir_name)
    return dirs_dict


def del_temp_files(parents, fuzz_progress, output_dir):
    """ Deletes temporary files that are not positive results of fuzz testing

    :param list parents: list of parent mutations
    :param FuzzingProgress fuzz_progress: progress of the fuzzing
    :param str output_dir: path to directory, where fuzzed files are stored
    """
    log.info("Removing remaining mutations ", end='')
    for mutation in parents:
        if mutation not in fuzz_progress.final_results and mutation not in fuzz_progress.hangs \
                and mutation not in fuzz_progress.faults and \
                mutation.path.startswith(output_dir) and path.isfile(mutation.path):
            # for evaluation purposes only:
            # don't remove the best mutation in case that no degradative mutation has been found
            # and mutation.path != fuzz_progress.parents[-1].path
            with helpers.SuppressedExceptions(FileNotFoundError):
                os.remove(mutation.path)
            log.info('-', end="")
    log.done()
