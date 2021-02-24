/*
 * Copyright (c) 2017-2019 The University of Manchester
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

/*!
 * @dir
 * @brief Implementation of simulator for a single neural population on a
 *      SpiNNaker CPU core. Or rather of a slice of a population.
 *
 * @file
 * @brief This file contains the main function of the application framework,
 *      which the application programmer uses to configure and run applications.
 *
 * This is the main entrance class for most of the neural models. The following
 * Figure shows how all of the c code
 * interacts with each other and what classes
 * are used to represent over arching logic
 * (such as plasticity, spike processing, utilities, synapse types, models)
 *
 * @image html spynnaker_c_code_flow.png
 */

#include "c_main_neuron.h"
#include "c_main_synapse.h"
#include "c_main_common.h"
#include "regions.h"
#include "profile_tags.h"

//! The combined provenance from synapses and neurons
struct combined_provenance {
    struct neuron_provenance neuron_provenance;
    struct synapse_provenance synapse_provenance;
    //! Maximum backgrounds queued
    uint32_t max_backgrounds_queued;
    //! Background queue overloads
    uint32_t n_background_queue_overloads;
};

//! values for the priority for each callback
typedef enum callback_priorities {
    MC = -1, DMA = 0, USER = 0, TIMER = 0, SDP = 1, BACKGROUND = 1
} callback_priorities;

const struct common_regions COMMON_REGIONS = {
    .system = SYSTEM_REGION,
    .provenance = PROVENANCE_DATA_REGION,
    .profiler = PROFILER_REGION,
    .recording = RECORDING_REGION
};

const struct common_priorities COMMON_PRIORITIES = {
    .sdp = SDP,
    .dma = DMA,
    .timer = TIMER
};

const struct neuron_regions NEURON_REGIONS = {
    .neuron_params = NEURON_PARAMS_REGION,
    .neuron_recording = NEURON_RECORDING_REGION
};

const struct synapse_regions SYNAPSE_REGIONS = {
    .synapse_params = SYNAPSE_PARAMS_REGION,
    .direct_matrix = DIRECT_MATRIX_REGION,
    .synaptic_matrix = SYNAPTIC_MATRIX_REGION,
    .pop_table = POPULATION_TABLE_REGION,
    .synapse_dynamics = SYNAPSE_DYNAMICS_REGION,
    .structural_dynamics = STRUCTURAL_DYNAMICS_REGION,
    .bitfield_filter = BIT_FIELD_FILTER_REGION
};

const struct synapse_priorities SYNAPSE_PRIORITIES = {
    .process_synapses = USER,
    .receive_packet = MC
};

// Globals

//! The current timer tick value.
// the timer tick callback returning the same value.
uint32_t time;

//! timer tick period (in microseconds)
static uint32_t timer_period;

//! The number of timer ticks to run for before being expected to exit
static uint32_t simulation_ticks = 0;

//! Determines if this model should run for infinite time
static uint32_t infinite_run;

//! The recording flags indicating if anything is recording
static uint32_t recording_flags = 0;

//! The number of background tasks queued / running
static uint32_t n_backgrounds_queued = 0;

//! The number of times the background couldn't be added
static uint32_t n_background_overloads = 0;

//! The maximum number of background tasks queued
static uint32_t max_backgrounds_queued = 0;

//! timer count for tdma of certain models; exported
uint global_timer_count;

//! \brief Callback to store provenance data (format: neuron_provenance).
//! \param[out] provenance_region: Where to write the provenance data
static void c_main_store_provenance_data(address_t provenance_region) {
    struct combined_provenance *prov = (void *) provenance_region;
    prov->n_background_queue_overloads = n_background_overloads;
    prov->max_backgrounds_queued = max_backgrounds_queued;
    store_neuron_provenance(&prov->neuron_provenance);
    store_synapse_provenance(&prov->synapse_provenance);
}

//! \brief the function to call when resuming a simulation
void resume_callback(void) {

    // Reset recording
    recording_reset();

    // try resuming neuron
    if (!neuron_resume()) {
        log_error("failed to resume neuron.");
        rt_error(RTE_SWERR);
    }

    // Resume synapses
    // NOTE: at reset, time is set to UINT_MAX ahead of timer_callback(...)
    synapses_resume(time + 1);
}

void process_ring_buffers(timer_t time, uint32_t n_neurons,
        uint32_t n_synapse_types, weight_t *ring_buffers) {
    // Transfer the input from the ring buffers into the input buffers
    for (uint32_t neuron_index = 0; neuron_index < n_neurons;
            neuron_index++) {
        // Loop through all synapse types
        for (uint32_t synapse_type_index = 0;
                synapse_type_index < n_synapse_types; synapse_type_index++) {
            // Get index in the ring buffers for the current time slot for
            // this synapse type and neuron
            uint32_t ring_buffer_index = synapse_row_get_ring_buffer_index(
                    time, synapse_type_index, neuron_index,
                    synapse_type_index_bits, synapse_index_bits, synapse_delay_mask);

            // Convert ring-buffer entry to input and add on to correct
            // input for this synapse type and neuron
            neuron_add_inputs(
                    synapse_type_index, neuron_index,
                    ring_buffers[ring_buffer_index]);

            // Clear ring buffer
            ring_buffers[ring_buffer_index] = 0;
        }
    }

    // Print the neuron inputs.
    #if LOG_LEVEL >= LOG_DEBUG
        log_debug("Inputs");
        neuron_print_inputs();
    #endif // LOG_LEVEL >= LOG_DEBUG
}

//! \brief Background activites called from timer
//! \param timer_count the number of times this call back has been
//!        executed since start of simulation
//! \param[in] local_time: The time step being executed
void background_callback(uint timer_count, uint local_time) {
    profiler_write_entry_disable_irq_fiq(PROFILER_ENTER | PROFILER_TIMER);

    log_debug("Timer tick %u \n", local_time);

    synaptogenesis_do_timestep_update();

    // Now do neuron time step update
    neuron_do_timestep_update(local_time, timer_count);

    profiler_write_entry_disable_irq_fiq(PROFILER_EXIT | PROFILER_TIMER);
    n_backgrounds_queued--;
}

//! \brief Timer interrupt callback
//! \param[in] timer_count: the number of times this call back has been
//!            executed since start of simulation
//! \param[in] unused: unused parameter kept for API consistency
void timer_callback(uint timer_count, UNUSED uint unused) {
    // Disable interrupts to stop DMAs and MC getting in the way of this bit
    uint32_t state = spin1_int_disable();

    time++;

    // Clear any outstanding spikes
    spike_processing_clear_input_buffer(time);

    spin1_mode_restore(state);
    state = spin1_irq_disable();

    // Also do synapses timestep update, as this is time-critical
    synapses_do_timestep_update(time);

    /* if a fixed number of simulation ticks that were specified at startup
     * then do reporting for finishing */
    if (simulation_is_finished()) {

        // Enter pause and resume state to avoid another tick
        simulation_handle_pause_resume(resume_callback);

        // Pause neuron processing
        neuron_pause();

        // Pause common functions
        common_pause(recording_flags);

        // Subtract 1 from the time so this tick gets done again on the next
        // run
        time--;

        simulation_ready_to_read();
        spin1_mode_restore(state);
        return;
    }

    // Push the rest to the background
    if (!spin1_schedule_callback(background_callback, timer_count, time, BACKGROUND)) {
        // We have failed to do this timer tick!
        n_background_overloads++;
    } else {
        n_backgrounds_queued++;
        if (n_backgrounds_queued > max_backgrounds_queued) {
            max_backgrounds_queued++;
        }
    }

    spin1_mode_restore(state);
}

//! \brief Initialises the model by reading in the regions and checking
//!        recording data.
//! \return True if it successfully initialised, false otherwise
static bool initialise(void) {
    log_debug("Initialise: started");

    data_specification_metadata_t *ds_regions;
    if (!initialise_common_regions(
            &timer_period, &simulation_ticks, &infinite_run, &time,
            &recording_flags, c_main_store_provenance_data, timer_callback,
            COMMON_REGIONS, COMMON_PRIORITIES, &ds_regions)) {
        return false;
    }

    // Setup neurons
    uint32_t n_rec_regions_used;
    if (!initialise_neuron_regions(
            ds_regions, NEURON_REGIONS,  &n_rec_regions_used)) {
        return false;
    }

    // Setup synapses
    if (!initialise_synapse_regions(
            ds_regions, SYNAPSE_REGIONS, SYNAPSE_PRIORITIES,
            n_rec_regions_used)) {
        return false;
    }

    log_debug("Initialise: finished");
    return true;
}

//! \brief The entry point for this model.
void c_main(void) {

    // Start the time at "-1" so that the first tick will be 0
    time = UINT32_MAX;

    // initialise the model
    if (!initialise()) {
        rt_error(RTE_API);
    }

    simulation_run();
}
