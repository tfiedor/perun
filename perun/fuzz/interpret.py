""" Module contains a set of functions for fuzzing results interpretation."""

__author__ = 'Matus Liscinsky'

import difflib
import math
import os.path as path

import matplotlib.pyplot as plt
import numpy as np
import scipy.stats.mstats as stats
import seaborn as sns

import perun.fuzz.filesystem as filesystem
import perun.utils.log as log
import perun.utils.streams as streams


# Force matplotlib to not use any Xwindows backend.
plt.switch_backend('agg')

DATA_LINE_WIDTH = 4
DATA_LINE_ALPHA = 0.9
GREY_COLOR = '#555555'
MEDIAN_ALPHA = 0.7
PLOT_SIZE_X = 10
PLOT_SIZE_Y = 5
TEXT_FONTSIZE = 11
TEXT_SPACE_CONSTANT_X = 25
TEXT_SPACE_CONSTANT_Y = 40
QUARTILE_ALPHA = 0.4
QUARTILE_LINE_WIDTH = 2


def save_anomalies(anomalies, anomaly_type, file_handle):
    """Saves anomalies (faults and hangs) into the file

    :param list anomalies: list of
    :param str anomaly_type: type of the anomalies (e.g. Faults, Hangs)
    :param File file_handle: file, where the anomalies are written
    """
    log.info("Saving {}s".format(anomaly_type), end=" ")
    if anomalies:
        file_handle.write("{}s:\n".format(anomaly_type.capitalize()))
        for anomaly in anomalies:
            file_handle.write(
                anomaly.path + " " + str(anomaly.history) + "\n"
            )
            log.info('.')


def save_time_series(file_handle, time_series):
    """Saves the time series data into the file handle

    :param File file_handle: opened file handle for writing
    :param TimeSeries time_series: list of times for values
    """
    for x_value, y_value in zip(time_series.x_axis, time_series.y_axis):
        file_handle.write(
            str(x_value) + " " + str(y_value) + "\n"
        )
        log.info('.', end="")


def save_log_files(log_dir, fuzz_progress):
    """ Saves information about fuzzing in log file. Note: refactor

    :param str log_dir: path to the output log directory
    :param FuzzingProgress fuzz_progress: progress of the fuzzing
    """
    log.info("Saving log files ", end="")
    deg_data_file = open(
        path.join(log_dir, fuzz_progress.start_timestamp + "_degradation_plot_data.txt"), "w")
    cov_data_file = open(
        path.join(log_dir, fuzz_progress.start_timestamp + "_coverage_plot_data.txt"), "w")
    results_data_file = open(
        path.join(log_dir, fuzz_progress.start_timestamp + "_results_data.txt"), "w")

    save_time_series(deg_data_file, fuzz_progress.deg_time_series)
    save_time_series(cov_data_file, fuzz_progress.cov_time_series)

    for mut in fuzz_progress.parents:
        results_data_file.write(
            str(mut.fitness) + " " + str(mut.cov) + " " +
            str(mut.deg_ratio) + " " + mut.path + " " + str(mut.history) + "\n"
        )
        log.info('.', end="")
    log.done()

    save_anomalies(fuzz_progress.hangs, 'hang', results_data_file)
    log.done()
    save_anomalies(fuzz_progress.faults, 'fault', results_data_file)
    log.done()

    deg_data_file.close()
    cov_data_file.close()
    results_data_file.close()


def get_time_value(value, time_data, data):
    """Function gets time value according to measured value.

    :param numeric value: selected y-axis value
    :param list time_data: time values (x-axis)
    :param list data: measured values (y-axis)
    :return int: time value from `time_data` according to measured value from `data`
    """
    for val in zip(time_data, data):
        if val[1] >= value:
            return val[0]
    return 0


def plot_fuzz_time_series(time_series, filename, title, xlabel, ylabel):
    """Plots the measured values to time series graph.

    :param TimeSeries time_series: measured values (x and y-axis)
    :param str filename: name of the output .pdf file
    :param str title: title of graph
    :param str xlabel: name of x-axis
    :param str ylabel: name of y-axis
    """
    _, axis = plt.subplots(figsize=(PLOT_SIZE_X, PLOT_SIZE_Y))

    axis.set_title(title)
    axis.set_xlabel(xlabel)
    axis.set_ylabel(ylabel)

    axis.spines['top'].set_visible(False)
    axis.spines['right'].set_visible(False)

    axis.grid(color='grey', linestyle='-', linewidth=0.5, alpha=0.2)

    st_quartile, nd_quartile, rd_quartile = stats.mquantiles(
        time_series.y_axis)
    st_quartile, nd_quartile, rd_quartile = int(
        st_quartile), int(nd_quartile), int(rd_quartile)
    st_time = get_time_value(
        st_quartile, time_series.x_axis, time_series.y_axis)
    nd_time = get_time_value(
        nd_quartile, time_series.x_axis, time_series.y_axis)
    rd_time = get_time_value(
        rd_quartile, time_series.x_axis, time_series.y_axis)

    axis.axvline(x=st_time, ymin=0, ymax=1, linestyle='--',
                 linewidth=QUARTILE_LINE_WIDTH, alpha=QUARTILE_ALPHA, color='k')
    axis.axhline(y=st_quartile, xmin=0, xmax=1, linestyle='--',
                 linewidth=QUARTILE_LINE_WIDTH, alpha=QUARTILE_ALPHA, color='k')

    axis.axvline(x=nd_time, ymin=0, ymax=1, linestyle='-',
                 linewidth=QUARTILE_LINE_WIDTH, alpha=MEDIAN_ALPHA, color='r')
    axis.axhline(y=nd_quartile, xmin=0, xmax=1, linestyle='-',
                 linewidth=QUARTILE_LINE_WIDTH, alpha=MEDIAN_ALPHA, color='r')

    axis.axvline(x=rd_time, ymin=0, ymax=1, linestyle='--',
                 linewidth=QUARTILE_LINE_WIDTH, alpha=QUARTILE_ALPHA, color='k')
    axis.axhline(y=rd_quartile, xmin=0, xmax=1, linestyle='--',
                 linewidth=QUARTILE_LINE_WIDTH, alpha=QUARTILE_ALPHA, color='k')

    text_space_x = -(max(time_series.x_axis)/TEXT_SPACE_CONSTANT_X)
    text_space_y = max(time_series.y_axis)/TEXT_SPACE_CONSTANT_Y

    plt.plot(time_series.x_axis, time_series.y_axis, 'c', alpha=DATA_LINE_ALPHA,
             linewidth=DATA_LINE_WIDTH)
    plt.text(st_time + text_space_x, st_quartile + text_space_y, str(int(st_quartile)),
             fontweight='bold', color=GREY_COLOR, fontsize=TEXT_FONTSIZE)
    plt.text(nd_time + text_space_x, nd_quartile + text_space_y, str(int(nd_quartile)),
             fontweight='bold', color='red', alpha=MEDIAN_ALPHA, fontsize=TEXT_FONTSIZE)
    plt.text(rd_time + text_space_x, rd_quartile + text_space_y, str(int(rd_quartile)),
             fontweight='bold', color=GREY_COLOR, fontsize=TEXT_FONTSIZE)
    plt.savefig(filename, bbox_inches='tight', format='pdf')


def files_diff(fuzz_progress, diffs_dir):
    """Creates html files showing the difference between mutations and its predecessor
    in diff unified format.

    :param FuzzingProgress fuzz_progress: collection of statistics of fuzzing process
    :param str diffs_dir: path to the directory where diffs will be stored
    """
    log.info("Computing deltas", end=" ")
    for mutations in [fuzz_progress.final_results, fuzz_progress.faults, fuzz_progress.hangs]:
        for res in mutations:
            pred = streams.safely_load_file(res.predecessor.path)
            result = streams.safely_load_file(res.path)

            delta = difflib.unified_diff(pred, result, lineterm='')

            # split the file to name and extension
            _, file = path.split(res.path)
            file, _ = path.splitext(file)

            diff_file_name = file + "-diff.html"

            diff = "<table>"
            for line in delta:
                diff += "<tr><td>"
                if line[0] == '-':
                    diff += "<xmp style='color: red; display: inline'>" + line + "</xmp>"
                elif line[0] == '+':
                    diff += "<xmp style='color: green; display: inline'>" + line + "</xmp>"
                else:
                    diff += "<xmp style='display: inline'>" + line + "</xmp>"
                diff += "</td></tr>\n"
            diff += "</table>"

            open(diff_file_name, "w").writelines(diff)
            filesystem.move_file_to(diff_file_name, diffs_dir)

    log.done()


def print_most_affected_paths(callgraph):
    """Function prints all callgraph paths, that we were able to affect (specifically their coverage)
        during the fuzzing. Paths are sorted according to their max coverage ratio with baseline coverage.

    :param CallGraph callgraph: struct of the target application callgraph
    """
    log.info("Most affected pahts:")

    # Sort paths by reached coverage increase
    sorted_paths = sorted(callgraph._unique_paths, key=lambda p: (
        p.max_inc_cov_increase + p.max_exc_cov_increase)/2, reverse=True)
    average_inc = sum(
        [p.max_exc_cov_increase for p in callgraph._unique_paths])/len(sorted_paths)
    average_exc = sum(
        [p.max_inc_cov_increase for p in callgraph._unique_paths])/len(sorted_paths)

    for i, path in enumerate(sorted_paths):
        # Print only sufficiently affected paths
        if path.max_inc_cov_increase > average_inc or \
                path.max_exc_cov_increase > average_exc:
            log.info("{}. {}\n inc_ratio: {}, exc_ratio: {}".format(
                str(i+1), path.to_string(), path.max_inc_cov_increase, path.max_exc_cov_increase))


def draw_paths_heatmap(callgraph, graphs_dir, fuzzing_timestamp):
    """Using overall coverage information about callgraph pahts, this functions draws two heatmaps,
        where each cell represent the max coverage ratio of the belonging path.

    :param CallGraph callgraph: struct of the target application callgraph
    :param str graphs_dir: path to the dir, where graphs (as one of the fuzzing outputs) are stored
    :param str fuzzing_timestamp: string with the datetime we use to distinguish outputs from different
        fuzz testing runs
    """
    path_count = len(callgraph._unique_paths)
    rows = math.floor(math.sqrt(path_count))
    cols = math.ceil(path_count/rows)
    empty_cells = (rows*cols) - path_count

    # Gather the data about coverage
    data_inc = [
        path.max_inc_cov_increase for path in callgraph._unique_paths] + ([0]*empty_cells)
    data_exc = [
        path.max_exc_cov_increase for path in callgraph._unique_paths] + ([0]*empty_cells)
    # Mask for empty cells in future matrix (padding)
    mask = ([False]*path_count) + ([True]*empty_cells)

    # Transform each list to 2d array (matrix)
    data_inc = np.array(data_inc).reshape((rows,cols))
    data_exc = np.array(data_exc).reshape((rows,cols))
    mask = np.array(mask).reshape((rows,cols))

    sns.set()
    log.info("Plotting heatmaps of callgpaph paths coverage.", end="")
    create_heatmap(data_inc, graphs_dir + "/" + fuzzing_timestamp +
                   "_inc_paths_heatmap.png", cols, rows, mask)
    create_heatmap(data_exc, graphs_dir + "/" + fuzzing_timestamp +
                   "_exc_paths_heatmap.png", cols, rows, mask)
    log.done()


def create_heatmap(data, filename, cols, rows, mask):
    """Helper function that uses seaborn and matplotlib in order to plot the heatmaps.

    :param list data: coverage data of the paths
    :param str filename: path to the output file (where to store the heatmap)
    :param int cols: num of columns in heatmap
    :param int rows: num of rows in heatmap
    :param list mask: list of bool values used to mask the cells without the coverage value
    """
    with sns.axes_style("white"):
        _, ax = plt.subplots(figsize=(cols, rows))
        ax = sns.heatmap(data, mask=np.array(mask), annot=True, fmt=".2f",
                         xticklabels=False, yticklabels=False, linewidths=.5,
                         cbar_kws={"orientation": "horizontal"})
        ax.figure.savefig(filename, dpi=300)
    log.info('.', end="")
