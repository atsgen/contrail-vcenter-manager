from unittest import TestCase
from mock import Mock
from pyVmomi import vim  # pylint: disable=no-name-in-module
from vnc_api.vnc_api import VirtualNetwork
from cvm.models import VirtualMachineModel
from cvm.services import VirtualMachineService


class TestVirtualMachineModel(TestCase):

    def setUp(self):
        self.vmware_dpg = self._create_dpg_mock(name='VM Portgroup')
        vmware_vm = self._create_vmware_vm_mock([
            self.vmware_dpg,
            Mock(spec=vim.Network),
        ])
        self.vm_model = VirtualMachineModel(vmware_vm)
        self.vnc_client = Mock()
        self.vnc_client.read_vn = lambda fq_name: self.vn_lookup.get(fq_name[2])
        self.vnc_client.construct_security_group.return_value = None
        self.vcenter_client = self._create_vcenter_client_mock(self.vmware_dpg)
        self.vm_service = VirtualMachineService(None, self.vcenter_client, self.vnc_client, None)

    def test_get_vn_models_for_vm(self):
        vnc_vn = VirtualNetwork()
        self.vn_lookup = {'VM Portgroup': vnc_vn}

        result = self.vm_service._get_vnc_vns_for_vm(self.vm_model)

        self.assertEqual([vnc_vn], [vn_model.vnc_vn for vn_model in result])

    def test_get_vn_models_for_vm_novn(self):
        """ Non-existing VNC VN. """
        self.vn_lookup = {}

        result = self.vm_service._get_vnc_vns_for_vm(self.vm_model)

        self.assertEqual([], result)

    @staticmethod
    def _create_vmware_vm_mock(network):
        vmware_vm = Mock()
        vmware_vm.summary.runtime.host.vm = []
        vmware_vm.network = network
        return vmware_vm

    @staticmethod
    def _create_dpg_mock(**kwargs):
        dpg_mock = Mock(spec=vim.dvs.DistributedVirtualPortgroup)
        for kwarg in kwargs:
            setattr(dpg_mock, kwarg, kwargs[kwarg])
        return dpg_mock

    @staticmethod
    def _create_vcenter_client_mock(vmware_dpg):
        vcenter_client = Mock()
        vcenter_client.get_dpgs_for_vm.return_value = [vmware_dpg]
        vcenter_client.__enter__ = Mock()
        vcenter_client.__exit__ = Mock()
        vcenter_client.get_ip_pool_for_dpg.return_value = None
        return vcenter_client
