"""Collection of helper functions used in fuzzing"""

__author__ = 'Tomas Fiedor, Matus Liscinsky'

import numpy as np

from perun.postprocess.regression_analysis.tools import APPROX_ZERO


def median_vector(vectors):
    """Computes piecewise median from list of numerical vectors.

    :param list vectors: list of vectors (lists with numerical value)
    :return list: vector, which has on each position median value from all vectors on this postition
    """
    data = np.array(vectors)
    data = data.astype('float')
    data[data == 0.0] = APPROX_ZERO
    return (np.median(data,axis=0)).tolist()


def sum_vectors_piecewise(vec1, vec2):
    """Creates a vector, where each value on position i is sum of vec1[i] and vec2[i]. Lengths of the
        vectors does not have to equal.

    :param list vec1: first vector
    :param list vec2: second vector
    :return list: [vec1[0]+vec2[0], vec1[1]+vec2[1], ...]
    """
    # fill in 0 so that the lengths of the vectors are equal (0 is a neutral element for addition)
    if len(vec1) != len(vec2):
        shorter_list = min(vec1, vec2, key=len)
        diff = abs(len(vec1) - len(vec2))
        shorter_list.extend([0]*diff)
    # numpy array automatically sums element-wise
    return (np.array(vec1) + np.array(vec2)).tolist()


def div_vectors_piecewise(vec1, vec2):
    """Creates a vector, where each value on position i is div of vec1[i] by vec2[i]. Lengths of the
        vectors have to equal.

    :param list vec1: first vector
    :param list vec2: second vector
    :return list: [vec1[0]/vec2[0], vec1[1]/vec2[1], ...] or empty list if the lengths don't equal
    """
    # numpy array automatically divs element-wise
    return (np.array(vec1)/ np.array(vec2)).tolist() if len(vec1) == len(vec2) else []


def insert_at_split(lines, index, split_position, inserted_bytes):
    """

    :param list lines:
    :param int index:
    :param int split_position:
    :param bytes inserted_bytes:
    :return:
    """
    lines[index] = lines[index][:split_position] + inserted_bytes + lines[index][split_position:]


def remove_at_split(lines, index, split_position):
    """

    :param list lines:
    :param int index:
    :param int split_position:
    :return:
    """
    lines[index] = lines[index][:split_position] + lines[index][split_position+1:]


def replace_at_split(lines, index, split_position, replaced_bytes):
    """
    :param list lines:
    :param int index:
    :param int split_position:
    :param bytes replaced_bytes:
    :return:
    """
    lines[index] = lines[index][:split_position] + replaced_bytes + lines[index][split_position+1:]
