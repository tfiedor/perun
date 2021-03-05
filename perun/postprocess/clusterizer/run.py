"""Clusterization postprocessing module

Currently we will try to issue the following clusterization techniques:
  1. **Sort order**---the sort order of values itself gives the cluster
  2. **Fixed window**---the cluster is represented by a fixed sized window of values
  3. **Weighted window**---the cluster is represented by a window. The size of the window is
     dependent on the values themselves.

All of the windows can be further augmented by taking into account how many percent of values are
actually taken.
"""

import operator
import itertools
import click

import perun.postprocess.clusterizer as clustering
import perun.profile.convert as convert
import perun.utils as utils
import perun.utils.log as log
import perun.logic.runner as runner

from perun.profile.factory import pass_profile
from perun.utils.structs import PostprocessStatus


def resource_sort_key(resource):
    """Extracts the key from resource used for sorting

    :param dict resource: profiling resource
    :return: key used for sorting
    """
    return convert.flatten(resource['uid']), resource['amount']


def resource_group_key(resource):
    """Extracts the key from resource used for grouping

    :param dict resource: profiling resource
    :return: key used for grouping
    """
    return resource['type'], resource.get('subtype', ''), convert.flatten(resource['uid'])


def print_groups(resources):
    """Helper function for printing groups of resources

    :param list resources: list of resources
    """
    groups = itertools.groupby(resources, resource_group_key)
    for group, members in groups:
        log.info("--- {} ---".format(group))
        for member in members:
            log.info(" -> {}[{}]".format(member['amount'], member.get('cluster', '?')), end='')
        log.newline()


def postprocess(profile, strategy, **kwargs):
    """Takes the given profile and according to the set strategy computes clusters of resources

    All of the resources are first sorted according to their uid and amounts. Then they are group
    according to their uid and for each group we compute the clusters in isolation

    :param Profile profile: performance profile that will be clusterized
    :param str strategy: name of the used strategy
        (one of clustering.SUPPORTED_STRATEGIES
    :param kwargs:
    :return:
    """
    # Flatten the resources to sorted list of resources
    resources = list(map(operator.itemgetter(1), profile.all_resources()))
    resources.sort(key=resource_sort_key)

    # For debug purposes, print the results
    if log.is_verbose_enough(log.VERBOSE_INFO):
        print_groups(resources)

    # Call the concrete strategy, for each group of resources
    groups = itertools.groupby(resources, resource_group_key)
    for group, members in groups:
        log.info("clusterizing group {}{}@{}".format(
            group[0], "({})".format(group[1]) if group[1] else "", group[2]
        ))
        utils.dynamic_module_function_call(
            'perun.postprocess.clusterizer', strategy, 'clusterize', list(members), **kwargs
        )
    profile.update_resources(resources, clear_existing_resources=True)

    # For debug purposes, print the results
    if log.is_verbose_enough(log.VERBOSE_INFO):
        print_groups(resources)

    # Return that everything is ok
    return PostprocessStatus.OK, "Sucessfully clusterized the profile", dict(kwargs)


@click.command()
@click.option('--strategy', '-s', default=clustering.DEFAULT_STRATEGY,
              type=click.Choice(clustering.SUPPORTED_STRATEGIES),
              help="Specifies the clustering strategy, that will be applied for the profile")
@click.option('--window-height', '-wh', default=0.01,
              type=click.FLOAT, required=False,
              help="Specifies the height of the window (either fixed or proportional)")
@click.option('--relative-window-height', '-rwh', 'height_measure',
              default=True, required=False, flag_value='relative',
              help="Specifies that the height of the window is relative to the point")
@click.option('--fixed-window-height', '-fwh', 'height_measure',
              required=False, flag_value='absolute',
              help="Specifies that the height of the window is absolute to the point")
@click.option('--window-width', '-ww', default=0.01,
              type=click.FLOAT, required=False,
              help="Specifies the width of the window"
                   ", i.e. how many values will be taken by window.")
@click.option('--relative-window-width', '-rww', 'width_measure',
              default=True, required=False, flag_value='relative',
              help="Specifies whether the width of the window is weighted or fixed")
@click.option('--fixed-window-width', '-fww', 'width_measure',
              required=False, flag_value='absolute',
              help="Specifies whether the width of the window is weighted or fixed")
@click.option('--weighted-window-width', '-www', 'width_measure',
              required=False, flag_value='weighted',
              help="Specifies whether the width of the window is weighted or fixed")
@pass_profile
def clusterizer(profile, **kwargs):
    """Clusters each resource to an appropriate cluster in order to be postprocessable
    by regression analysis.

    \b
      * **Limitations**: `none`
      * **Dependencies**: `none`

    Clusterizer tries to find a suitable cluster for each resource in the profile. The clusters
    are either computed w.r.t the sort order of the resource amounts, or are computed according
    to the sliding window.

    The sliding window can be further adjusted by setting its **width** (i.e. how many near values
    on the x axis will we fit to a cluster) and its **height** (i.e. how big of an interval of
    resource amounts will be consider for one cluster). Both **width** and **height** can be further
    augmented. **Width** can either be `absolute`, where we take in maximum the absolute number of
    resources, `relative`, where we take in maximum the percentage of number of resources for each
    cluster, or `weighted`, where we take the number of resource depending on the frequency of their
    occurrences. Similarly, the **height** can either be `absolute`, where we set the interval of
    amounts to an absolute size, or `relative`, where we set the interval of amounts relative to the
    to the first resource amount in the cluster (so e.g. if we have window of height 0.1 and the
    first resource in the cluster has amount of 100, we will cluster every resources in interval 100
    to 110 to this cluster).

    For more details about regression analysis refer to :ref:`postprocessors-clusterizer`.
    """
    runner.run_postprocessor_on_profile(profile, 'clusterizer', kwargs)
