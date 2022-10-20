# Copyright (c) 2022 The University of Manchester
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
import pyNN.spiNNaker as p
import numpy
from pyNN.space import Grid2D
from data_specification.enums import DataType
from spynnaker.pyNN.external_devices_models import (
    AbstractEthernetTranslator, AbstractMulticastControllableDevice)
from spinnaker_testbase.base_test_case import BaseTestCase
from spynnaker.pyNN.external_devices_models \
    .abstract_multicast_controllable_device import SendType


class TestTranslator(AbstractEthernetTranslator):

    def translate_control_packet(self, multicast_packet):
        print(f"Received key={multicast_packet.key},"
              f" voltage={multicast_packet.payload / DataType.S1615.max}")


class TestDevice(AbstractMulticastControllableDevice):

    @property
    def device_control_partition_id(self):
        # This should be unique to the device, but is otherwise unimportant
        return "Test"

    @property
    def device_control_key(self):
        # This should be unique to the device
        return 0

    @property
    def device_control_uses_payload(self):
        # This returns True to receive the voltage,
        # or False if only the key is desired
        return True

    @property
    def device_control_min_value(self):
        # Return the minimum value accepted by the device.  If the membrane
        # voltage is below this value, this value will be used.
        return 0

    @property
    def device_control_max_value(self):
        # Return the maximum value accepted by the device.  If the membrane
        # voltage is above this value, this value will be used.
        return 100

    @property
    def device_control_timesteps_between_sending(self):
        # The number of timesteps between sending values.  Controls the
        # update rate of the value.
        return 10

    @property
    def device_control_send_type(self):
        # The type of the value - one of the SendType values
        return SendType.SEND_TYPE_ACCUM

    @property
    def device_control_scaling_factor(self):
        # The amount to multiply the voltage by before transmission
        return 1.0


def do_run():

    # Setup the simulation
    p.setup(1.0)

    # Run time if send_fake_spikes is False
    run_time = 60000

    # Constants
    Y_SHIFT = 0
    X_SHIFT = 16
    WIDTH = 346
    HEIGHT = 260

    # Creates 512 neurons per core
    SUB_WIDTH = 16
    SUB_HEIGHT = 16

    # Set the number of neurons per core to a rectangle
    # (creates 512 neurons per core)
    p.set_number_of_neurons_per_core(p.IF_curr_exp, (SUB_WIDTH, SUB_HEIGHT))

    dev = p.Population(None, p.external_devices.SPIFRetinaDevice(
            pipe=0, width=WIDTH, height=HEIGHT, sub_width=SUB_WIDTH,
            sub_height=SUB_HEIGHT, input_x_shift=X_SHIFT,
            input_y_shift=Y_SHIFT))

    # Make a kernel and convolution connector
    k_shape = numpy.array([5, 5], dtype='int32')
    k_size = numpy.prod(k_shape)
    kernel = (numpy.arange(k_size) - (k_size / 2)).reshape(k_shape) * 0.1
    conn = p.ConvolutionConnector(kernel)

    # Start with an input shape, and deduce the output shape
    in_shape = (WIDTH, HEIGHT)
    out_shape = conn.get_post_shape(in_shape)

    # Make a 2D target Population and record it
    capture = p.Population(
        (out_shape[0] * out_shape[1]), p.IF_curr_exp(), label="out",
        structure=Grid2D(out_shape[0] / out_shape[1]))

    p.Projection(dev, capture, conn, p.Convolution())

    # Create the model that will generate the voltage
    pop = p.external_devices.EthernetControlPopulation(
        n_neurons=1,
        model=p.external_devices.ExternalDeviceLifControl(
            devices=[TestDevice()],
            create_edges=False,
            translator=TestTranslator()),
        label="test")

    # Connect the stimulation to the population
    p.Projection(capture, pop, p.OneToOneConnector(),
                 p.StaticSynapse(weight=0.1))

    # Run the simulation then stop
    p.run(run_time)
    p.end()


class TestOverlappingNetwork(BaseTestCase):

    def test_run(self):
        self.runsafe(do_run)