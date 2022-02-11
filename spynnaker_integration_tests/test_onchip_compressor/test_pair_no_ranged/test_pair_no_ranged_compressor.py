# Copyright (c) 2017-2019 The University of Manchester
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

from spinnaker_testbase import BaseTestCase
from spynnaker_integration_tests.test_onchip_compressor.many_routes \
    import do_run
from spynnaker_integration_tests.test_onchip_compressor.one_route \
    import do_one_run


class TestPairNoRangeCompressor(BaseTestCase):

    def test_do_run(self):
        self.runsafe(do_run)

    def test_do_one_run(self):
        self.runsafe(do_one_run)
