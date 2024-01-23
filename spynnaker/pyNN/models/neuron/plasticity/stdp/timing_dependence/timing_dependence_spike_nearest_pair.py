# Copyright (c) 2017 The University of Manchester
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

from numpy import floating
from numpy.typing import NDArray
from typing import Iterable
from spinn_utilities.overrides import overrides
from spinn_front_end_common.utilities.constants import BYTES_PER_WORD
from spinn_front_end_common.interface.ds import DataSpecificationBase
from spynnaker.pyNN.data import SpynnakerDataView
from spynnaker.pyNN.models.neuron.plasticity.stdp.common import (
    get_exp_lut_array)
from spynnaker.pyNN.models.neuron.plasticity.stdp.synapse_structure import (
    SynapseStructureWeightOnly)
from .abstract_timing_dependence import AbstractTimingDependence


class TimingDependenceSpikeNearestPair(AbstractTimingDependence):
    """
    A timing dependence STDP rule based on nearest pairs.
    """
    __slots__ = (
        "__tau_minus",
        "__tau_minus_data",
        "__tau_plus",
        "__tau_plus_data",
        "__a_plus",
        "__a_minus")
    __PARAM_NAMES = ('tau_plus', 'tau_minus')
    default_parameters = {'tau_plus': 20.0, 'tau_minus': 20.0}

    def __init__(self, tau_plus: float = default_parameters['tau_plus'],
                 tau_minus: float = default_parameters['tau_minus'],
                 A_plus: float = 0.01, A_minus: float = 0.01):
        r"""
        :param float tau_plus: :math:`\tau_+`
        :param float tau_minus: :math:`\tau_-`
        :param float A_plus: :math:`A^+`
        :param float A_minus: :math:`A^-`
        """
        super().__init__(SynapseStructureWeightOnly())
        self.__tau_plus = tau_plus
        self.__tau_minus = tau_minus
        self.__a_plus = A_plus
        self.__a_minus = A_minus

        ts = SpynnakerDataView.get_simulation_time_step_ms()
        self.__tau_plus_data = get_exp_lut_array(ts, self.__tau_plus)
        self.__tau_minus_data = get_exp_lut_array(ts, self.__tau_minus)

    @property
    def tau_plus(self) -> float:
        r"""
        :math:`\tau_+`

        :rtype: float
        """
        return self.__tau_plus

    @property
    def tau_minus(self) -> float:
        r"""
        :math:`\tau_-`

        :rtype: float
        """
        return self.__tau_minus

    @property
    def A_plus(self) -> float:
        r"""
        :math:`A^+`

        :rtype: float
        """
        return self.__a_plus

    @A_plus.setter
    def A_plus(self, new_value: float):
        self.__a_plus = new_value

    @property
    def A_minus(self) -> float:
        r"""
        :math:`A^-`

        :rtype: float
        """
        return self.__a_minus

    @A_minus.setter
    def A_minus(self, new_value: float):
        self.__a_minus = new_value

    @overrides(AbstractTimingDependence.is_same_as)
    def is_same_as(
            self, timing_dependence: AbstractTimingDependence) -> bool:
        if not isinstance(timing_dependence, TimingDependenceSpikeNearestPair):
            return False
        return (self.__tau_plus == timing_dependence.tau_plus and
                self.__tau_minus == timing_dependence.tau_minus)

    @property
    def vertex_executable_suffix(self) -> str:
        """
        The suffix to be appended to the vertex executable for this rule.

        :rtype: str
        """
        return "nearest_pair"

    @property
    def pre_trace_n_bytes(self) -> int:
        """
        The number of bytes used by the pre-trace of the rule per neuron.

        :rtype: int
        """
        # Pair rule requires no pre-synaptic trace when only the nearest
        # Neighbours are considered and, a single 16-bit R1 trace
        return 0

    @overrides(AbstractTimingDependence.get_parameters_sdram_usage_in_bytes)
    def get_parameters_sdram_usage_in_bytes(self) -> int:
        return BYTES_PER_WORD * (len(self.__tau_plus_data) +
                                 len(self.__tau_minus_data))

    @property
    def n_weight_terms(self) -> int:
        """
        The number of weight terms expected by this timing rule.

        :rtype: int
        """
        return 1

    @overrides(AbstractTimingDependence.write_parameters)
    def write_parameters(
            self, spec: DataSpecificationBase, global_weight_scale: float,
            synapse_weight_scales: NDArray[floating]):
        # Write lookup tables
        spec.write_array(self.__tau_plus_data)
        spec.write_array(self.__tau_minus_data)

    @overrides(AbstractTimingDependence.get_parameter_names)
    def get_parameter_names(self) -> Iterable[str]:
        return self.__PARAM_NAMES
