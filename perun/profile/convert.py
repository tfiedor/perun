"""``perun.profile.convert`` is a module which specifies interface for
conversion of profiles from :ref:`profile-spec` to other formats.

.. _pandas: https://pandas.pydata.org/

Run the following in the Python interpreter to extend the capabilities of
Python to different formats of profiles::

    import perun.profile.convert

Combined with ``perun.profile.factory``, ``perun.profile.query`` and e.g.
`pandas`_ library one can obtain efficient interpreter for executing more
complex queries and statistical tests over the profiles.
"""
import perun.utils.helpers as helpers
import perun.profile.query as query
import perun.postprocess.regression_analysis.transform as transform
import operator
import array

import demandimport
with demandimport.enabled():
    import numpy
    import pandas


__author__ = 'Radim Podola'
__coauthors__ = ['Tomas Fiedor', 'Jirka Pavela']


def resources_to_pandas_dataframe(profile):
    """Converts the profile (w.r.t :ref:`profile-spec`) to format supported by
    `pandas`_ library.

    Queries through all of the resources in the `profile`, and flattens each
    key and value to the tabular representation. Refer to `pandas`_ library for
    more possibilities how to work with the tabular representation of collected
    resources.

    E.g. given `time` and `memory` profiles ``tprof`` and ``mprof``
    respectively, one can obtain the following formats::

        >>> convert.resources_to_pandas_dataframe(tprof)
           amount  snapshots   uid
        0  0.616s          0  real
        1  0.500s          0  user
        2  0.125s          0   sys

        >>> convert.resources_to_pandas_dataframe(mmprof)
            address  amount  snapshots subtype                   trace    type
        0  19284560       4          0  malloc  malloc:unreachabl...  memory
        1  19284560       0          0    free  free:unreachable:...  memory

                          uid uid:function  uid:line                 uid:source
        0  main:../memo...:22         main        22   ../memory_collect_test.c
        1  main:../memo...:27         main        27   ../memory_collect_test.c

    :param Profile profile: dictionary with profile w.r.t. :ref:`profile-spec`
    :returns: converted profile to ``pandas.DataFramelist`` with resources
        flattened as a pandas dataframe
    """
    # Since some keys may be missing in the resources, we consider all of the possible fields
    resource_keys = list(profile.all_resource_fields())
    values = {key: [] for key in resource_keys}
    values['snapshots'] = array.array('I')

    # All resources at this point should be flat
    for (snapshot, resource) in profile.all_resources(True):
        values['snapshots'].append(snapshot)
        for resource_key in resource_keys:
            values[resource_key].append(resource.get(resource_key, numpy.nan))

    return pandas.DataFrame(values)


def models_to_pandas_dataframe(profile):
    """Converts the models of profile (w.r.t :ref:`profile-spec`) to format
    supported by `pandas`_ library.

    Queries through all of the models in the `profile`, and flattens each
    key and value to the tabular representation. Refer to `pandas`_ library for
    more possibilities how to work with the tabular representation of models.

    :param Profile profile: dictionary with profile w.r.t. :ref:`profile-spec`
    :returns: converted models of profile to ``pandas.DataFramelist``
    """
    # Note that we need to to this inefficiently, because some keys can be missing in resources
    model_keys = list(query.all_model_fields_of(profile))
    values = {key: [] for key in model_keys}

    for _, model in profile.all_models():
        flattened_resources = dict(list(query.all_items_of(model)))
        for model_key in model_keys:
            values[model_key].append(flattened_resources.get(model_key, numpy.nan))

    return pandas.DataFrame(values)


def to_flame_graph_format(profile):
    """Transforms the **memory** profile w.r.t. :ref:`profile-spec` into the
    format supported by perl script of Brendan Gregg.

    .. _Brendan Gregg's homepage: http://www.brendangregg.com/index.html

    :ref:`views-flame-graph` can be used to visualize the inclusive consumption
    of resources w.r.t. the call trace of the resource. It is useful for fast
    detection, which point at the trace is the hotspot (or bottleneck) in the
    computation. Refer to :ref:`views-flame-graph` for full capabilities of our
    Wrapper. For more information about flame graphs itself, please check
    `Brendan Gregg's homepage`_.

    Example of format is as follows::

        >>> print(''.join(convert.to_flame_graph_format(memprof)))
        malloc()~unreachable~0;main()~/home/user/dev/test.c~45 4
        valloc()~unreachable~0;main()~/home/user/dev/test.c~75;__libc_start_main()~unreachable~0 8
        main()~/home/user/dev/test02.c~79 156

    Each line corresponds to some collected resource (in this case amount of
    allocated memory) preceeded by its trace (i.e. functions or other unique
    identifiers joined using ``;`` character.

    :param Profile profile: the memory profile
    :returns: list of lines, each representing one allocation call stack
    """
    stacks = []
    for _, snapshot in profile.all_snapshots():
        for alloc in snapshot:
            if alloc['subtype'] != 'free':
                stack_str = ""
                for frame in alloc['trace']:
                    line = to_string_line(frame)
                    stack_str += line + ';'
                if stack_str and stack_str.endswith(';'):
                    final = stack_str[:-1]
                    final += " " + str(alloc['amount']) + '\n'
                    stacks.append(final)

    return stacks


def to_string_line(frame):
    """ Create string representing call stack's frame

    :param dict frame: call stack's frame
    :returns str: line representing call stack's frame
    """
    return "{}()~{}~{}".format(frame['function'], frame['source'], frame['line'])


def plot_data_from_coefficients_of(model):
    """Transform coefficients computed by
    :ref:`postprocessors-regression-analysis` into dictionary of points,
    plotable as a function or curve. This function serves as a public wrapper
    over regression analysis transformation function.

    :param dict model: the models dictionary from profile (refer to
        :pkey:`models`)
    :returns dict: updated models dictionary extended with `plot_x` and
        `plot_y` lists
    """
    model.update(transform.coefficients_to_points(**model))
    return model


def flatten(flattened_value):
    """Converts the value to something that can be used as one value.

    Flattens the value to single level, lists are processed to comma separated representation and
    rest is left as it is.
    TODO: Add caching

    :param object flattened_value: value that is flattened
    :returns: either decimal, string, or something else
    """
    # Dictionary is processed recursively according to the all items that are nested
    if isinstance(flattened_value, dict):
        nested_values = []
        for key, value in query.all_items_of(flattened_value):
            # Add one level of hierarchy with ':'
            nested_values.append((key, value))
        # Return the overall key as joined values of its nested stuff,
        # only if root is not a list (i.e. root key is not int = index)!
        nested_values.sort(key=helpers.uid_getter)
        return ":".join(map(str, map(operator.itemgetter(1), nested_values)))
    # Lists are merged as comma separated keys
    elif isinstance(flattened_value, list):
        return ','.join(
            ":".join(str(nested_value[1]) for nested_value in query.flattened_values(i, lv))
            for (i, lv) in enumerate(flattened_value)
        )
    # Rest of the values are left as they are
    else:
        return flattened_value
