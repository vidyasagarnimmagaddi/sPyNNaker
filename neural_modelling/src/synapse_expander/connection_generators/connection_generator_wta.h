/*
 * Copyright (c) 2024 The University of Manchester
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/**
 * \dir
 * \brief Connection generators
 * \file
 * \brief Winner Takes All connection generator implementation
 */

#include <stdbool.h>
#include <synapse_expander/generator_types.h>

//! \brief The parameters to be passed around for this connector
struct wta {
	// How many values there are in each WTA group
    uint32_t n_values;
};

/**
 * \brief Initialise the wta connection generator
 * \param[in,out] region: Region to read parameters from.  Should be updated
 *                        to position just after parameters after calling.
 * \return A data item to be passed in to other functions later on
 */
static void *connection_generator_wta_initialise(void **region) {
    // Allocate the data structure for parameters
    struct wta *params = spin1_malloc(sizeof(struct wta));
    struct wta *params_sdram = *region;

    // Copy the parameters into the data structure
    *params = *params_sdram;
    *region = &params_sdram[1];

    log_debug("WTA connector, n_values = %u", params->n_values);

    return params;
}

/**
 * \brief Free the wta connection generator
 * \param[in] generator: The generator to free
 */
static void connection_generator_wta_free(void *generator) {
    sark_free(generator);
}

static inline bool make_wta_conn(param_generator_t weight_generator,
		param_generator_t delay_generator, matrix_generator_t matrix_generator,
		uint32_t pre, uint32_t post, unsigned long accum weight_scale,
		accum timestep_per_delay) {
	accum weight = param_generator_generate(weight_generator);
	uint16_t delay = rescale_delay(
			param_generator_generate(delay_generator), timestep_per_delay);
	if (!matrix_generator_write_synapse(matrix_generator, pre, post,
			weight, delay, weight_scale)) {
		log_error("Matrix not sized correctly!");
		return false;
	}
	return true;
}

static inline void div_mod(uint32_t dividend, uint32_t divisor, uint32_t *div,
		uint32_t *mod) {
	uint32_t remainder = dividend;
	uint32_t count = 0;
	while (remainder >= divisor) {
		remainder -= divisor;
		count++;
	}
	*div = count;
	*mod = remainder;
}

/**
 * \brief Generate connections with the wta connection generator
 * \param[in] generator: The generator to use to generate connections
 * \param[in] pre_slice_start: The start of the slice of the pre-population
 *                             being generated
 * \param[in] pre_slice_count: The number of neurons in the slice of the
 *                             pre-population being generated
 * \param[in] post_slice_start: The start of the slice of the post-population
 *                              being generated
 * \param[in] post_slice_count: The number of neurons in the slice of the
 *                              post-population being generated
 */
static bool connection_generator_wta_generate(
        void *generator, uint32_t pre_lo, uint32_t pre_hi,
        uint32_t post_lo, uint32_t post_hi, uint32_t post_index,
        uint32_t post_slice_start, uint32_t post_slice_count,
        unsigned long accum weight_scale, accum timestep_per_delay,
        param_generator_t weight_generator, param_generator_t delay_generator,
        matrix_generator_t matrix_generator) {
    struct wta *obj = generator;

    // Get the actual ranges to generate within
    uint32_t post_start = max(post_slice_start, post_lo);
    uint32_t post_end = min(post_slice_start + post_slice_count - 1, post_hi);

    // Work out where we are in the generation
    // We need to connect each pre-neuron to each post-neuron in each group
    // (but not to itself).  We are currently generating a subset of the post
    // neurons, so we need to work out which group we are in within that subset,
    // and which is the first post-neuron in the group that we are generating
    // for now.
    uint32_t post_group;
    uint32_t post_value;
    div_mod(post_start, obj->n_values, &post_group, &post_value);

    // Work out where the pre-neurons start and end for the group that we are
    // in at the start of the post-neurons.  The group might not have enough
    // neurons in it, so we check just in case.
    uint32_t pre_start = pre_lo + post_group * obj->n_values;
    uint32_t pre_end = min(pre_start + obj->n_values, pre_hi + 1);
    uint32_t n_values = pre_end - pre_start;

    // Go through the post neurons in this slice
    for (uint32_t post = post_start; post <= post_end; post++) {
		uint32_t local_post = post - post_slice_start;

		// Go through each of the "values" in this group that can target this
		// post neuron (each of which is a pre-neuron)
		for (uint32_t value = 0; value < n_values; value++) {
			if (value != post_value) {
				uint32_t pre = pre_start + value;
				if (!make_wta_conn(weight_generator, delay_generator,
						matrix_generator, pre, local_post, weight_scale,
						timestep_per_delay)) {
				    return false;
				}
			}
		}

		// Work out next loop iteration.  If we have reached the end of a group
		// of values, we need to move onto the next group.
		post_value += 1;
		if (post_value == obj->n_values) {
			post_value = 0;
			pre_start += obj->n_values;
			pre_end = min(pre_start + obj->n_values, pre_hi + 1);
			if (pre_start >= pre_hi) {
				break;
			}
			n_values = pre_end - pre_start;
		}
    }

    return true;
}
