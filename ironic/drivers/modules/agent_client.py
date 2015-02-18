# Copyright 2014 Rackspace, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from oslo_config import cfg
from oslo_serialization import jsonutils
import requests

from ironic.common import exception
from ironic.common.i18n import _
from ironic.openstack.common import log

agent_opts = [
    cfg.StrOpt('agent_api_version',
               default='v1',
               help='API version to use for communicating with the ramdisk '
                    'agent.')
]

CONF = cfg.CONF
CONF.register_opts(agent_opts, group='agent')

LOG = log.getLogger(__name__)


class AgentClient(object):
    """Client for interacting with nodes via a REST API."""
    def __init__(self):
        self.session = requests.Session()

    def _get_command_url(self, node):
        agent_url = node.driver_internal_info.get('agent_url')
        if not agent_url:
            # (lintan) Keep backwards compatible with booted nodes before this
            # change. Remove this after Kilo.
            agent_url = node.driver_info.get('agent_url')
        if not agent_url:
            raise exception.IronicException(_('Agent driver requires '
                                              'agent_url in '
                                              'driver_internal_info'))
        return ('%(agent_url)s/%(api_version)s/commands' %
                {'agent_url': agent_url,
                 'api_version': CONF.agent.agent_api_version})

    def _get_command_body(self, method, params):
        return jsonutils.dumps({
            'name': method,
            'params': params,
        })

    def _command(self, node, method, params, wait=False):
        url = self._get_command_url(node)
        body = self._get_command_body(method, params)
        request_params = {
            'wait': str(wait).lower()
        }
        headers = {
            'Content-Type': 'application/json'
        }
        response = self.session.post(url,
                                     params=request_params,
                                     data=body,
                                     headers=headers)

        # TODO(russellhaering): real error handling
        return response.json()

    def get_commands_status(self, node):
        url = self._get_command_url(node)
        headers = {'Content-Type': 'application/json'}
        res = self.session.get(url, headers=headers)
        return res.json()['commands']

    def prepare_image(self, node, image_info, wait=False):
        """Call the `prepare_image` method on the node."""
        LOG.debug('Preparing image %(image)s on node %(node)s.',
                  {'image': image_info.get('id'),
                   'node': node.uuid})
        params = {'image_info': image_info}

        # this should be an http(s) URL
        configdrive = node.instance_info.get('configdrive')
        if configdrive is not None:
            params['configdrive'] = configdrive

        return self._command(node=node,
                             method='standby.prepare_image',
                             params=params,
                             wait=wait)

    def start_iscsi_target(self, node, iqn):
        """Expose the node's disk as an ISCSI target."""
        params = {'iqn': iqn}
        return self._command(node=node,
                             method='iscsi.start_iscsi_target',
                             params=params,
                             wait=True)

    def install_bootloader(self, node, root_uuid, efi_system_part_uuid=None):
        """Install a boot loader on the image."""
        params = {'root_uuid': root_uuid,
                  'efi_system_part_uuid': efi_system_part_uuid}
        return self._command(node=node,
                             method='image.install_bootloader',
                             params=params,
                             wait=True)

    def get_clean_steps(self, node, ports):
        params = {
            'node': node.as_dict(),
            'ports': [port.as_dict() for port in ports]
        }
        return self._command(node=node,
                             method='clean.get_clean_steps',
                             params=params,
                             wait=True)

    def execute_clean_step(self, step, node, ports):
        params = {
            'step': step,
            'node': node.as_dict(),
            'ports': [port.as_dict() for port in ports],
            'clean_version': node.driver_internal_info.get(
                'hardware_manager_version')
        }
        return self._command(node=node,
                             method='clean.execute_clean_step',
                             params=params,
                             wait=False)
