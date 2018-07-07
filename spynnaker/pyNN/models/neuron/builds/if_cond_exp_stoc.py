from spynnaker.pyNN.models.abstract_models \
    import AbstractPyNNNeuronModelStandard
from spynnaker.pyNN.models.neuron.implementations.defaults \
    import default_initial_values
from spynnaker.pyNN.models.neuron.neuron_models \
    import NeuronModelLeakyIntegrateAndFire
from spynnaker.pyNN.models.neuron.synapse_types import SynapseTypeExponential
from spynnaker.pyNN.models.neuron.input_types import InputTypeConductance
from spynnaker.pyNN.models.neuron.threshold_types \
    import ThresholdTypeMaassStochastic


class IFCondExpStoc(AbstractPyNNNeuronModelStandard):

    @default_initial_values({"v", "isyn_exc", "isyn_inh"})
    def __init__(
            self, tau_m=20.0, cm=1.0, v_rest=-65.0, v_reset=-65.0,
            v_thresh=-50.0, tau_syn_E=5.0, tau_syn_I=5.0, tau_refrac=0.1,
            i_offset=0.0, e_rev_E=0.0, e_rev_I=-70.0, du_th=0.5, tau_th=20.0,
            v=-65.0, isyn_exc=0.0, isyn_inh=0.0):
        # pylint: disable=too-many-arguments, too-many-locals
        neuron_model = NeuronModelLeakyIntegrateAndFire(
            v, v_rest, tau_m, cm, i_offset, v_reset, tau_refrac)
        synapse_type = SynapseTypeExponential(
            tau_syn_E, tau_syn_I, isyn_exc, isyn_inh)
        input_type = InputTypeConductance(e_rev_E, e_rev_I)
        threshold_type = ThresholdTypeMaassStochastic(
            du_th, tau_th, v_thresh)

        super(IFCondExpStoc, self).__init__(
            model_name="IF_cond_exp_stoc", binary="IF_cond_exp_stoc.aplx",
            neuron_model=neuron_model, input_type=input_type,
            synapse_type=synapse_type, threshold_type=threshold_type)
