# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import fixtures

from keystone.common import fernet_utils as utils


class KeyRepository(fixtures.Fixture):
    def __init__(self, config_fixture):
        super(KeyRepository, self).__init__()
        self.config_fixture = config_fixture

    def setUp(self):
        super(KeyRepository, self).setUp()
        directory = self.useFixture(fixtures.TempDir()).path
        self.config_fixture.config(group='fernet_tokens',
                                   key_repository=directory)

        fernet_utils = utils.FernetUtils()
        fernet_utils.create_key_directory()
        fernet_utils.initialize_key_repository()
