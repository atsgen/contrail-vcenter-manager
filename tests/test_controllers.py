import logging
from unittest import TestCase

from mock import Mock
from pyVmomi import vim, vmodl  # pylint: disable=no-name-in-module

from cvm.controllers import (GuestNetHandler, PowerStateHandler, UpdateHandler,
                             VmReconfiguredHandler, VmRemovedHandler,
                             VmRenamedHandler, VmwareController,
                             VmwareToolsStatusHandler)

logging.disable(logging.CRITICAL)


def construct_update_set(name, value, obj=None):
    property_change = Mock(val=value)
    property_change.configure_mock(name=name)
    object_update = Mock(changeSet=[property_change], obj=obj)
    property_filter_update = Mock(objectSet=[object_update])
    update_set = Mock(filterSet=[property_filter_update])
    return update_set


class TestVmwareController(TestCase):
    def setUp(self):
        self.database = Mock()
        self.vm_service = Mock(database=self.database)
        self.vmi_service = Mock()
        self.vn_service = Mock()
        self.vrouter_port_service = Mock()

        vm_renamed_handler = VmRenamedHandler(self.vm_service, self.vmi_service, self.vrouter_port_service)
        vm_removed_handler = VmRemovedHandler(self.vm_service, self.vmi_service, Mock())
        vm_reconfigured_handler = VmReconfiguredHandler(self.vm_service, self.vn_service,
                                                        self.vmi_service, self.vrouter_port_service)
        guest_net_handler = GuestNetHandler(self.vmi_service, self.vrouter_port_service)
        vmware_tools_handler = VmwareToolsStatusHandler(self.vm_service)
        power_state_handler = PowerStateHandler(self.vm_service, self.vrouter_port_service)
        handlers = [
            vm_renamed_handler,
            vm_removed_handler,
            vm_reconfigured_handler,
            guest_net_handler,
            vmware_tools_handler,
            power_state_handler,
        ]
        update_handler = UpdateHandler(handlers)
        lock = Mock(__enter__=Mock(), __exit__=Mock())
        self.vmware_controller = VmwareController(self.vm_service, None, self.vmi_service, None,
                                                  update_handler, lock)

    def test_handle_update_delete_vm(self):
        update_set = construct_update_set('latestPage', Mock(spec=vim.event.VmRemovedEvent()))
        self.vmware_controller.handle_update(update_set)
        self.assertTrue(self.vmware_controller._vmi_service.remove_vmis_for_vm_model.called)
        self.assertTrue(self.vmware_controller._vm_service.remove_vm.called)

    def test_handle_update_deleted_vm(self):
        """
        When an event for an already deleted VM is received,
        the controller should do nothing.
        """
        update_set = construct_update_set('latestPage', Mock(spec=vim.event.VmCreatedEvent()))
        self.vm_service.update.side_effect = vmodl.fault.ManagedObjectNotFound

        self.vmware_controller.handle_update(update_set)

        self.database.save.assert_not_called()
        self.vmi_service.update_vmis_for_vm_model.assert_not_called()

    def test_handle_tools_status(self):
        vmware_vm = Mock()
        update_set = construct_update_set('guest.toolsRunningStatus', 'guestToolsNotRunning', vmware_vm)

        self.vmware_controller.handle_update(update_set)

        self.vm_service.update_vmware_tools_status.assert_called_once_with(
            vmware_vm, 'guestToolsNotRunning'
        )

    def test_handle_tools_deleted_vm(self):
        """
        When 'guest.toolsRunningStatus' change for an already deleted VM is received,
        the controller should do nothing.
        """
        update_set = construct_update_set('guest.toolsRunningStatus', 'guestToolsNotRunning')
        self.vm_service.update_vmware_tools_status.side_effect = vmodl.fault.ManagedObjectNotFound

        self.vmware_controller.handle_update(update_set)

    def test_vm_renamed(self):
        update_set = construct_update_set('latestPage', Mock(spec=vim.event.VmRenamedEvent()))

        self.vmware_controller.handle_update(update_set)

        self.vm_service.rename_vm.assert_called_once()
        self.vmi_service.rename_vmis.assert_called_once()

    def test_virtual_ethernet_card(self):
        event = Mock(spec=vim.event.VmReconfiguredEvent())
        device_spec = Mock()
        device_spec.device = Mock(spec=vim.vm.device.VirtualE1000())
        event.configSpec.deviceChange = [device_spec]
        update_set = construct_update_set('latestPage', event)

        self.vmware_controller.handle_update(update_set)

        self.vm_service.update_vm_models_interfaces.assert_called_once()
        self.vn_service.update_vns.assert_called_once()
        self.vmi_service.update_vmis.assert_called_once()
        self.vrouter_port_service.sync_ports.assert_called_once()

    def test_guest_net(self):
        update_set = construct_update_set('guest.net', [Mock()])

        self.vmware_controller.handle_update(update_set)

        self.vmi_service.update_nic.assert_called_once()
        self.vrouter_port_service.sync_ports.assert_called_once()

    def test_power_state(self):
        vmware_vm = Mock()
        update_set = construct_update_set('runtime.powerState', 'poweredOn', vmware_vm)

        self.vmware_controller.handle_update(update_set)

        self.vm_service.update_power_state.assert_called_once_with(vmware_vm, 'poweredOn')
        self.vrouter_port_service.sync_port_states.assert_called_once()
