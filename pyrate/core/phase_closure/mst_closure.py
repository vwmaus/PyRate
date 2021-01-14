#   This Python module is part of the PyRate software package.
#
#   Copyright 2021 Geoscience Australia
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.


from collections import namedtuple
from typing import List, Union
from datetime import date
import networkx as nx
from pyrate.core.shared import dem_or_ifg

Edge = namedtuple('Edge', ['first', 'second'])


class SignedEdge:

    def __init__(self, edge: Edge, sign: int):
        self.edge = edge
        self.sign = sign
        self.first = self.edge.first
        self.second = self.edge.second

    def __repr__(self):
        return f'({self.first}, {self.second})'


class SignedWeightedEdge(SignedEdge):

    def __init__(self, signed_edge: SignedEdge, weight: int):
        super().__init__(signed_edge.edge, sign=signed_edge.sign)
        self.signed_edge = signed_edge
        self.weight = weight


class WeightedLoop:
    """
    Loop with weight equal to the sum of the edge weights, where edge weights are the epochs of the ifgs
    """

    def __init__(self, loop: List[SignedWeightedEdge]):
        self.loop = loop

    @property
    def weight(self):
        return sum([swe.weight for swe in self.loop])

    @property
    def earliest_date(self):
        return min({swe.first for swe in self.loop})

    @property
    def primary_dates(self):
        first_dates = [swe.first for swe in self.loop]
        first_dates.sort()
        st = ''.join([str(d) for d in first_dates])
        return st

    @property
    def secondary_dates(self):
        first_dates = [swe.second for swe in self.loop]
        first_dates.sort()
        st = ''.join([str(d) for d in first_dates])
        return st

    def __len__(self):
        return len(self.loop)

    @property
    def edges(self):
        return [Edge(swe.first, swe.edge.second) for swe in self.loop]


def __discard_cycles_with_same_members(simple_cycles: List[List[date]]) -> List[List[date]]:
    seen_sc_sets = set()
    filtered_sc = []
    for sc in simple_cycles:
        loop = sc[:]
        sc.sort()
        sc = tuple(sc)
        if sc not in seen_sc_sets:
            seen_sc_sets.add(sc)
            filtered_sc.append(loop)
    return filtered_sc


def __find_closed_loops(edges: List[Edge]) -> List[List[date]]:
    g = nx.Graph()
    edges = [(we.first, we.second) for we in edges]
    g.add_edges_from(edges)
    dg = nx.DiGraph(g)
    simple_cycles = nx.simple_cycles(dg)  # will have all edges
    simple_cycles = [scc for scc in simple_cycles if len(scc) > 2]  # discard edges

    # also discard loops when the loop members are the same
    return __discard_cycles_with_same_members(simple_cycles)


def __add_signs_and_weights_to_loops(loops: List[List[date]], available_edges: List[Edge]) -> List[WeightedLoop]:
    """
    add signs and weights to loops.
    Additionally, sort the loops (change order of ifgs appearing in loop) by weight and date
    """
    weighted_signed_loops = []
    available_edges = set(available_edges)  # hash it once for O(1) lookup
    for i, l in enumerate(loops):
        weighted_signed_loop = []
        l.append(l[0])  # add the closure loop
        for ii, ll in enumerate(l[:-1]):
            if l[ii+1] > ll:
                edge = Edge(ll, l[ii+1])
                assert edge in available_edges
                signed_edge = SignedEdge(edge, 1)  # opposite direction of ifg
            else:
                edge = Edge(l[ii+1], ll)
                assert edge in available_edges
                signed_edge = SignedEdge(edge, -1)  # in direction of ifg
            weighted_signed_edge = SignedWeightedEdge(
                signed_edge,
                (signed_edge.second - signed_edge.first).days
            )
            weighted_signed_loop.append(weighted_signed_edge)

        # sort the loops by first the weight, and then minimum start date
        weighted_signed_loop.sort(key=lambda x: (x.first, x.second, x.sign))
        weighted_loop = WeightedLoop(weighted_signed_loop)
        weighted_signed_loops.append(weighted_loop)

    return weighted_signed_loops


def __setup_edges(ifg_files: List[str]) -> List[Edge]:
    ifg_files.sort()
    ifgs = [dem_or_ifg(i) for i in ifg_files]
    for i in ifgs:
        i.open()
        i.nodata_value = 0
    return [Edge(i.first, i.second) for i in ifgs]


def __find_signed_closed_loops(ifg_files: List[str]) -> List[WeightedLoop]:
    available_edges = __setup_edges(ifg_files)
    all_loops = __find_closed_loops(available_edges)  # find loops with weights
    signed_weighted_loops = __add_signs_and_weights_to_loops(all_loops, available_edges)
    return signed_weighted_loops


def sort_loops_based_on_weights_and_date(ifg_files: List[str]) -> List[WeightedLoop]:
    """
    :param ifg_files: list of ifg files
    :return: list of sorted, signed, and weighted loops
    """
    signed_weighted_loops = __find_signed_closed_loops(ifg_files)
    # sort based on weights and dates
    signed_weighted_loops.sort(key=lambda x: [x.weight, x.primary_dates, x.secondary_dates])
    return signed_weighted_loops