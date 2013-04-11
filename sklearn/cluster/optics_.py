# -*- coding: utf-8 -*-
"""
OPTICS: Ordering Points To Identify the Clustering Structure
"""

# Author: Fredrik Appelros, Carl Ekerot
# License: BSD

import numpy as np

from ..base import BaseEstimator, ClusterMixin
from ..metrics import pairwise_distances
from scipy.spatial.distance import cdist

def hierarchical_extraction(ordering, reachability_distances, min_cluster_size,
        significant_ratio=0.75, similarity_ratio=0.4, min_reach_ratio=0.1):
    """
    Constructs a tree structure from an OPTICS ordering and a set of
    reachability distances and extracts clusters from this structure.

    Parameters
    ----------
    ordering : array [n_samples]
        Indices of the samples in the order generated by OPTICS.

    reachability_distances : array [n_samples]
        Reachability distance for each sample.

    min_cluster_size : int
        The minimum size of a cluster in number of samples.

    significant_ratio : float
        The ratio for the reachability score of a local maximum
        compared to its neighbors to be considered significant.

    similarity_ratio : float
        The ratio for the reachability score of a split point
        compared to the parent split point for it to be considered
        similar.

    min_reach_ratio : float
        The ratio of the largest reachability score that a local
        maximum needs to reach in order to be considered.

    Returns
    -------
    labels : array [n_samples]
        Cluster labels for each point.  Noisy samples are given the label -1.

    References
    ----------
    Sander, Jörg, Xuejie Qin, Zhiyong Lu, Nan Niu, and Alex Kovarsky.
    "Automatic extraction of clusters from hierarchical clustering
    representations." Advances in Knowledge Discovery and Data Mining (2003):
    567-567.

    """
    R = np.asarray([reachability_distances[i] for i in ordering])
    n = len(ordering)

    # Find local maximas
    L = []
    for i in xrange(0, min_cluster_size):
        if np.argmax(R[0:i + min_cluster_size + 1]) == i:
            L.append(i)
        if np.argmax(R[n - 2 * min_cluster_size + i:n]) == i:
            L.append(n - min_cluster_size + i)
    for i in xrange(min_cluster_size, n - min_cluster_size):
        if np.argmax(R[i - min_cluster_size:i + min_cluster_size + 1]) == min_cluster_size:
            L.append(i)
    # Sort local maximas in order of their reachability
    L.sort(key=lambda x: R[x]) 
    R_max = R[L[-1]]
    L = filter(lambda x: R[x] >= min_reach_ratio * R_max, L)

    class Node:
        def __init__(self, left, right):
            self.left = left
            self.right = right
            self.children = []

    leaves = []
    def cluster_tree(node, parent, L):
        if not L:
            leaves.append(node)
            return

        s = node.split = L.pop()
        child_left = Node(node.left, s)
        child_right = Node(s, node.right)
        L_left  = [L[i] for i in np.where(np.asarray(L) < s)[0]]
        L_right = [L[i] for i in np.where(np.asarray(L) > s)[0]]
        R_left  = R[child_left.left:child_left.right]
        R_right = R[child_right.left:child_right.right]

        if R_left.size > 0:
            avg_reach_left = np.mean(R_left)
        else:
            avg_reach_left = 0
        if R_right.size > 0:
            avg_reach_right = np.mean(R_right)
        else:
            avg_reach_right = 0

        if avg_reach_left <= significant_ratio * R[s] >= avg_reach_right:
            children = []
            left_size = child_left.right - child_left.left
            if left_size >= min_cluster_size or left_size == child_left.right:
                children.append((child_left, L_left))
            right_size = child_right.right - child_right.left
            if right_size >= min_cluster_size or right_size == n - child_right.left:
                children.append((child_right, L_right))
            if not children:
                leaves.append(node)
                return

            if parent and R[s] / R[parent.split] >= similarity_ratio:
                for child, L in children:
                    parent.children.append(child)
                parent.children.remove(node)
                p = parent
            else:
                for child, L in children:
                    node.children.append(child)
                p = node
            for (child, L) in children:
                cluster_tree(child, p, L)
        else:
            cluster_tree(node, parent, L)

    root = Node(0, n)
    cluster_tree(root, None, L)

    labels = -np.ones(n)
    for (i, leaf) in enumerate(leaves):
        for j in xrange(leaf.left, leaf.right):
            labels[ordering[j]] = i

    return labels

EXTRACTION_FUNCTIONS = {
    'hierarchical': hierarchical_extraction,
}

def optics(X, eps=float('inf'), min_samples=5, metric='euclidean',
           extraction='hierarchical', ext_kwargs=dict()):
    """
    Perform OPTICS clustering from vector array or distance matrix.

    Parameters
    ----------
    X : array [n_samples, n_samples] or [n_samples, n_features]
        Array of distances between samples, or a feature array.
        The array is treated as a feature array unless the metric is given as
        'precomputed'.

    eps : float, optional
        The generating distance between two samples for them to be considered
        as in the same neighborhood.

    min_samples : int, optional
        The number of samples in a neighborhood for a point to be considered
        as a core point.

    metric : string or callable, optional
        The metric to use when calculating distance between instances in a
        feature array. If metric is a string or callable, it must be one of
        the options allowed by metrics.pairwise.calculate_distance for its
        metric parameter.
        If metric is "precomputed", X is assumed to be a distance matrix and
        must be square.

    extraction : string, optional
        The extraction method used to generate clusters from the ordering of
        points returned by the OPTICS algorithm.

    ext_kwargs : dict
        Keyword arguments to be supplied to the extraction function.

    Returns
    -------
    core_distances : array [n_samples]
        Core distance for each sample.

    ordering : array [n_samples]
        Indices of the samples in the order generated by OPTICS.

    reachability_distances : array [n_samples]
        Reachability distance for each sample.

    labels : array [n_samples]
        Cluster labels for each point. Noisy samples are given the label -1.

    Notes
    -----
    See examples/cluster/plot_optics.py for an example.

    References
    ----------
    Ankerst, Mihael, Markus M. Breunig, Hans-Peter Kriegel, and Jörg Sander.
    "OPTICS: ordering points to identify the clustering structure." ACM SIGMOD
    Record 28, no. 2 (1999): 49-60.

    """
    X = np.asarray(X)
    n = X.shape[0]
    ordering = []
    core_distances = np.ndarray(len(X))
    # Initiate reachability distances to infinity
    reachability_distances = float('inf') * np.ones(n)

    seeds = range(n)
    i = 0
    while len(seeds) > 1:
        # Mark current point as processed
        seeds.remove(i)
        # Add current point to the ordering
        ordering.append(i)
        # Calculate the pairwise distances
        D = cdist([X[i]], X).reshape(len(X))
        # Calculate core distance
        core_dist = np.sort(D)[min_samples]
        core_distances[i] = core_dist

        if core_dist <= eps:
            seeds_array = np.asarray(seeds)
            # Get the neighbors of the current point
            neighbors = seeds_array[np.where(D[seeds] <= eps)[0]]
            cd = core_dist * np.ones(neighbors.size)
            d = D[neighbors]
            # Set the new reachability distances to
            # max(core_distance, distance)
            new_reach_dists = np.maximum(cd, d)
            reachability_distances[neighbors] = new_reach_dists
            i = seeds[np.argmin(reachability_distances[seeds])]
        else:
            i = seeds[0]
    # Add last point
    ordering.append(seeds[0])
    # Set reachability for first point
    reachability_distances[0] = 0

    if type(extraction) is str:
        estr = extraction.lower()
        if estr in EXTRACTION_FUNCTIONS:
            func = EXTRACTION_FUNCTIONS[estr]
            labels = func(ordering, reachability_distances, min_samples,
                    **ext_kwargs)
        else:
            raise ValueError('Unknown Extraction Method: %s' % estr)
    else:
        raise TypeError('Extraction Method must be a string.')

    return core_distances, ordering, reachability_distances, labels

class OPTICS(BaseEstimator, ClusterMixin):
    """
    Perform OPTICS clustering from vector array or distance matrix.

    Parameters
    ----------
    X : array [n_samples, n_samples] or [n_samples, n_features]
        Array of distances between samples, or a feature array.
        The array is treated as a feature array unless the metric is given as
        'precomputed'.

    eps : float, optional
        The generating distance between two samples for them to be considered
        as in the same neighborhood.

    min_samples : int, optional
        The number of samples in a neighborhood for a point to be considered
        as a core point.

    metric : string or callable, optional
        The metric to use when calculating distance between instances in a
        feature array. If metric is a string or callable, it must be one of
        the options allowed by metrics.pairwise.calculate_distance for its
        metric parameter.
        If metric is "precomputed", X is assumed to be a distance matrix and
        must be square.

    extraction : string, optional
        The extraction method used to generate clusters from the ordering of
        points returned by the OPTICS algorithm.

    ext_kwargs : dict
        Keyword arguments to be supplied to the extraction function.

    Attributes
    ----------
    `core_distances_` : array [n_samples]
        Core distance for each sample.

    `ordering_` : array [n_samples]
        Indices of the samples in the order generated by OPTICS.

    `reachability_distances_` : array [n_samples]
        Reachability distance for each sample.

    `labels_` : array [n_samples]
        Cluster labels for each point. Noisy samples are given the label -1.

    Notes
    -----
    See examples/cluster/plot_optics.py for an example.

    References
    ----------
    Ankerst, Mihael, Markus M. Breunig, Hans-Peter Kriegel, and Jörg Sander.
    "OPTICS: ordering points to identify the clustering structure." ACM SIGMOD
    Record 28, no. 2 (1999): 49-60.

    """
    def __init__(self, eps=float('inf'), min_samples=5, metric='euclidean',
                 extraction='hierarchical', ext_kwargs=dict()):
        self.eps = eps
        self.min_samples = min_samples
        self.metric = metric
        self.extraction = extraction
        self.ext_kwargs = ext_kwargs

    def fit(self, X):
        """
        Perform OPTICS clustering from vector array or distance matrix.

        Parameters
        ----------
        X : array [n_samples, n_samples] or [n_samples, n_features]
            Array of distances between samples, or a feature array.
            The array is treated as a feature array unless the metric is
            given as 'precomputed'.
        params : dict
            Overwrite keywords from __init__.
        """
        clust = optics(X, **self.get_params())
        (self.core_distances_, self.ordering_, self.reachability_distances_,
                self.labels_) = clust
        return self
