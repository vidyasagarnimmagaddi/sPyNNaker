# Copyright (c) 2014 The University of Manchester
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import annotations
import math
from typing import List, Optional, Sequence, TYPE_CHECKING

import numpy
from numpy import integer, uint32
from numpy.typing import NDArray

from pyNN.random import NumpyRNG

from spinn_utilities.overrides import overrides

from pacman.model.graphs.common import Slice

from spinn_front_end_common.utilities.constants import BYTES_PER_WORD

from spynnaker.pyNN.exceptions import SpynnakerException
from spynnaker.pyNN.utilities import utility_calls

from .abstract_connector import AbstractConnector
from .abstract_generate_connector_on_machine import (
    AbstractGenerateConnectorOnMachine, ConnectorIDs)
from .abstract_generate_connector_on_host import (
    AbstractGenerateConnectorOnHost)

if TYPE_CHECKING:
    from spynnaker.pyNN.models.neural_projections import (
        ProjectionApplicationEdge, SynapseInformation)

N_GEN_PARAMS = 8


class FixedNumberPostConnector(AbstractGenerateConnectorOnMachine,
                               AbstractGenerateConnectorOnHost):
    """
    Connects a fixed number of post-synaptic neurons selected at random,
    to all pre-synaptic neurons.
    """

    __slots__ = (
        "__allow_self_connections",
        "__n_post",
        "__post_neurons",
        "__post_neurons_set",
        "__with_replacement",
        "__rng")

    def __init__(
            self, n: int, *, allow_self_connections: bool = True,
            with_replacement: bool = False, rng: Optional[NumpyRNG] = None,
            safe=True, verbose=False, callback=None):
        """
        :param int n:
            number of random post-synaptic neurons connected to pre-neurons.
        :param bool allow_self_connections:
            if the connector is used to connect a Population to itself, this
            flag determines whether a neuron is allowed to connect to itself,
            or only to other neurons in the Population.
        :param bool safe:
            Whether to check that weights and delays have valid values;
            if ``False``, this check is skipped.
        :param bool verbose:
            Whether to output extra information about the connectivity to a
            CSV file
        :param bool with_replacement:
            this flag determines how the random selection of post-synaptic
            neurons is performed; if ``True``, then every post-synaptic neuron
            can be chosen on each occasion, and so multiple connections
            between neuron pairs are possible; if ``False``, then once a
            post-synaptic neuron has been connected to a pre-neuron, it can't
            be connected again.
        :param rng:
            Seeded random number generator, or ``None`` to make one when
            needed.
        :type rng: ~pyNN.random.NumpyRNG or None
        :param callable callback:
            if given, a callable that display a progress bar on the terminal.

            .. note::
                Not supported by sPyNNaker.
        """
        super().__init__(safe, callback, verbose)
        self.__n_post = self._roundsize(n, "FixedNumberPostConnector")
        self.__allow_self_connections = allow_self_connections
        self.__with_replacement = with_replacement
        self.__post_neurons: List[NDArray[integer]] = []
        self.__post_neurons_set = False
        self.__rng = rng

    def set_projection_information(self, synapse_info: SynapseInformation):
        super().set_projection_information(synapse_info)
        if (not self.__with_replacement and
                self.__n_post > synapse_info.n_post_neurons):
            raise SpynnakerException(
                "FixedNumberPostConnector will not work when "
                "with_replacement=False and n > n_post_neurons")
        if (not self.__with_replacement and
                not self.__allow_self_connections and
                self.__n_post == synapse_info.n_post_neurons and
                synapse_info.pre_population is synapse_info.post_population):
            raise SpynnakerException(
                "FixedNumberPostConnector will not work when "
                "with_replacement=False, allow_self_connections=False "
                "and n = n_post_neurons")

    @overrides(AbstractConnector.get_delay_maximum)
    def get_delay_maximum(self, synapse_info: SynapseInformation) -> float:
        n_connections = synapse_info.n_pre_neurons * self.__n_post
        return self._get_delay_maximum(
            synapse_info.delays, n_connections, synapse_info)

    @overrides(AbstractConnector.get_delay_minimum)
    def get_delay_minimum(self, synapse_info: SynapseInformation) -> float:
        n_connections = synapse_info.n_pre_neurons * self.__n_post
        return self._get_delay_minimum(
            synapse_info.delays, n_connections, synapse_info)

    def __build_post_neurons(
            self, synapse_info: SynapseInformation) -> List[NDArray[integer]]:
        rng = self.__rng or NumpyRNG()
        post_neurons: List[NDArray[integer]] = \
            [numpy.empty([0], dtype=integer)] * synapse_info.n_pre_neurons
        # Loop over all the pre neurons
        for m in range(synapse_info.n_pre_neurons):
            if post_neurons[m] is None:
                # If the pre and post populations are the same
                # then deal with allow_self_connections=False
                if (synapse_info.pre_population is
                        synapse_info.post_population and
                        not self.__allow_self_connections):
                    # Create a list without the pre_neuron in it
                    no_self_post_neurons = numpy.concatenate(
                        [numpy.arange(0, m),
                         numpy.arange(m + 1,
                                      synapse_info.n_post_neurons)])

                    # Now use this list in the random choice
                    post_neurons[m] = rng.choice(
                        no_self_post_neurons, self.__n_post,
                        self.__with_replacement)
                else:
                    post_neurons[m] = rng.choice(
                        synapse_info.n_post_neurons, self.__n_post,
                        self.__with_replacement)
        return post_neurons

    def _get_post_neurons(self, synapse_info: SynapseInformation):
        """
        :param SynapseInformation synapse_info:
        :rtype: list(~numpy.ndarray)
        """
        # If we haven't set the array up yet, do it now
        if not self.__post_neurons_set:
            self.__post_neurons = self.__build_post_neurons(synapse_info)
            self.__post_neurons_set = True

            # if verbose open a file to output the connectivity
            if self.verbose:
                filename = f"{synapse_info.pre_population.label}_to_" \
                           f"{synapse_info.post_population.label}" \
                           f"_fixednumberpost-conn.csv"
                print('Output post-connectivity to ', filename)
                with open(filename, 'w', encoding="utf-8") as file_handle:
                    numpy.savetxt(file_handle,
                                  [(synapse_info.n_pre_neurons,
                                    synapse_info.n_post_neurons,
                                    self.__n_post)],
                                  fmt="%u,%u,%u")
                    for post_neuron in self.__post_neurons:
                        numpy.savetxt(
                            file_handle, post_neuron,
                            fmt=("%u," * (self.__n_post - 1) + "%u"))

        return self.__post_neurons

    def _post_neurons_in_slice(
            self, post_vertex_slice: Slice, n: int,
            synapse_info: SynapseInformation) -> NDArray[integer]:
        """
        :param ~pacman.model.graphs.common.Slice post_vertex_slice:
        :param int n:
        :param SynapseInformation synapse_info:
        :rtype: ~numpy.ndarray
        """
        post_neurons = self._get_post_neurons(synapse_info)

        # Get the nth array and get the bits we need for
        # this post-vertex slice
        this_post_neuron_array = post_neurons[n]

        return this_post_neuron_array[numpy.logical_and(
            post_vertex_slice.lo_atom <= this_post_neuron_array,
            this_post_neuron_array <= post_vertex_slice.hi_atom)]

    def _n_post_neurons_in_slice(
            self, post_vertex_slice: Slice, n: int,
            synapse_info: SynapseInformation) -> int:
        """
        Count the number of post neurons in the slice.
        Faster than ``len(_post_neurons_in_slice(...))``.

        :param ~pacman.model.graphs.common.Slice post_vertex_slice:
        :param int n:
        :param SynapseInformation synapse_info:
        :rtype: int
        """
        post_neurons = self._get_post_neurons(synapse_info)

        # Get the nth array and get the bits we need for
        # this post-vertex slice
        this_post_neuron_array = post_neurons[n]

        return numpy.count_nonzero(numpy.logical_and(
            post_vertex_slice.lo_atom <= this_post_neuron_array,
            this_post_neuron_array <= post_vertex_slice.hi_atom))

    @overrides(AbstractConnector.get_n_connections_from_pre_vertex_maximum)
    def get_n_connections_from_pre_vertex_maximum(
            self, n_post_atoms: int, synapse_info: SynapseInformation,
            min_delay: Optional[float] = None,
            max_delay: Optional[float] = None) -> int:
        prob_in_slice = min(
            n_post_atoms / float(
                synapse_info.n_post_neurons), 1.0)
        n_connections = utility_calls.get_probable_maximum_selected(
            synapse_info.n_pre_neurons * synapse_info.n_post_neurons,
            self.__n_post, prob_in_slice, chance=1.0/100000.0)

        if min_delay is None or max_delay is None:
            return int(math.ceil(n_connections))

        return self._get_n_connections_from_pre_vertex_with_delay_maximum(
            synapse_info.delays,
            synapse_info.n_pre_neurons * synapse_info.n_post_neurons,
            n_connections, min_delay, max_delay, synapse_info)

    @overrides(AbstractConnector.get_n_connections_to_post_vertex_maximum)
    def get_n_connections_to_post_vertex_maximum(
            self, synapse_info: SynapseInformation) -> int:
        selection_prob = 1.0 / float(synapse_info.n_post_neurons)
        n_connections = utility_calls.get_probable_maximum_selected(
            synapse_info.n_pre_neurons * synapse_info.n_post_neurons,
            synapse_info.n_pre_neurons, selection_prob,
            chance=1.0/100000.0)
        return int(math.ceil(n_connections))

    @overrides(AbstractConnector.get_weight_maximum)
    def get_weight_maximum(self, synapse_info: SynapseInformation) -> float:
        n_connections = synapse_info.n_pre_neurons * self.__n_post
        return self._get_weight_maximum(
            synapse_info.weights, n_connections, synapse_info)

    @overrides(AbstractGenerateConnectorOnHost.create_synaptic_block)
    def create_synaptic_block(
            self, post_slices: Sequence[Slice], post_vertex_slice: Slice,
            synapse_type: int, synapse_info: SynapseInformation) -> NDArray:
        # Get lo and hi for the pre vertex
        lo = 0
        hi = synapse_info.n_pre_neurons - 1

        # Get number of connections
        n_connections = sum(
            self._n_post_neurons_in_slice(post_vertex_slice, n, synapse_info)
            for n in range(lo, hi + 1))

        # Set up the block
        block = numpy.zeros(
            n_connections, dtype=AbstractConnector.NUMPY_SYNAPSES_DTYPE)

        # Set up source and target
        pre_neurons_in_slice = []
        post_neurons_in_slice = []
        pre_vertex_array = numpy.arange(lo, hi + 1)
        for n in range(lo, hi + 1):
            for pn in self._post_neurons_in_slice(
                    post_vertex_slice, n, synapse_info):
                post_neurons_in_slice.append(pn)
                pre_neurons_in_slice.append(pre_vertex_array[n - lo])

        block["source"] = pre_neurons_in_slice
        block["target"] = post_neurons_in_slice
        block["weight"] = self._generate_weights(
            block["source"], block["target"], n_connections, post_vertex_slice,
            synapse_info)
        block["delay"] = self._generate_delays(
            block["source"], block["target"], n_connections, post_vertex_slice,
            synapse_info)
        block["synapse_type"] = synapse_type
        return block

    def __repr__(self):
        return f"FixedNumberPostConnector({self.__n_post})"

    @property
    def allow_self_connections(self) -> bool:
        """
        Do we include connections from a neuron/id to itself?

        :rtype: bool
        """
        return self.__allow_self_connections

    @allow_self_connections.setter
    def allow_self_connections(self, new_value: bool):
        self.__allow_self_connections = new_value

    @property
    @overrides(AbstractGenerateConnectorOnMachine.gen_connector_id)
    def gen_connector_id(self) -> int:
        return ConnectorIDs.FIXED_NUMBER_POST_CONNECTOR.value

    @overrides(AbstractGenerateConnectorOnMachine.gen_connector_params)
    def gen_connector_params(
            self, synapse_info: SynapseInformation) -> NDArray[uint32]:
        allow_self = (
            self.__allow_self_connections or
            synapse_info.pre_population != synapse_info.post_population)
        return numpy.array([
            int(allow_self),
            int(self.__with_replacement),
            self.__n_post], dtype=uint32)

    @property
    @overrides(
        AbstractGenerateConnectorOnMachine.gen_connector_params_size_in_bytes)
    def gen_connector_params_size_in_bytes(self) -> int:
        return 3 * BYTES_PER_WORD

    @overrides(AbstractConnector.validate_connection)
    def validate_connection(
            self, application_edge: ProjectionApplicationEdge,
            synapse_info: SynapseInformation):
        if self.generate_on_machine(synapse_info):
            utility_calls.check_rng(self.__rng, "FixedNumberPostConnector")
