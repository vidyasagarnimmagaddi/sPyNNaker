import numpy

from spynnaker.pyNN import exceptions


def write_exp_synapse_param(tau, machine_time_step, n_atoms, spec):

    # Calculate decay and initialisation values
    decay = numpy.exp(numpy.divide(-float(machine_time_step),
                                   numpy.multiply(1000.0, tau)))
    init = numpy.multiply(numpy.multiply(tau, numpy.subtract(1.0, decay)),
                          (1000.0 / float(machine_time_step)))

    # Scale to fixed-point
    scale = float(pow(2, 32))
    rescaled_decay = numpy.multiply(decay, scale).astype("uint32")
    rescaled_init = numpy.multiply(init, scale).astype("uint32")

    # If we only generated a single param
    if rescaled_decay.size == 1 and rescaled_init.size == 1:

        # Copy for all atoms
        # **YUCK** this is inefficient in terms of DSG
        for _ in range(n_atoms):
            spec.write_value(data=rescaled_decay[0])
            spec.write_value(data=rescaled_init[0])

    # Otherwise, if we have generated decays and inits for each atom
    elif rescaled_decay.size == n_atoms and rescaled_init.size == n_atoms:
        # Interleave into one array
        interleaved_params = numpy.empty(decay.size + init.size)
        interleaved_params[0::2] = rescaled_decay
        interleaved_params[1::2] = rescaled_init

        spec.write_array(data=interleaved_params)
    else:
        raise exceptions.SynapticBlockGenerationException(
            "Cannot generate synapse parameters from %u values"
            % rescaled_decay.size)
