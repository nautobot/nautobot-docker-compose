from nautobot.extras.jobs import Job, BooleanVar
from .common import get_p42_token, get_devices_from_tool, create_panda_and_csv
from nautobot.extras.models import Status
from nautobot.dcim.models import Device, VirtualChassis, Interface
from nautobot.ipam.models import IPAddress
import re
from datetime import datetime


name = "Data Population Jobs"

class DeviceChange:
    def __init__(self, provider, serial, field_changed, current_value, change_value, device_name, device_id=None):
        self.provider = provider
        self.serial = serial
        self.field_changed = field_changed
        self.current_value = current_value
        self.change_value = change_value
        self.device_name = device_name
        self.device_id = device_id
        self.change_status = "Not Applied"

class ToolIDCleanupJob(Job):
    
    # Device roles to exclude from tool ID operations (not typically found in network tools)
    IGNORED_DEVICE_ROLES = ["SIM Card", "Wireless Router", "Inventory", "Wireless Access Point", "Epik GW"]
    
    class Meta:
        name = "Tool ID Cleanup"
        description = "Remove tool IDs from Nautobot devices that are no longer found in network tools and archive devices without tool IDs."
        time_limit = 3600
        soft_time_limit = 3600
        has_sensitive_variables = False

    is_running_tool_id_changes = BooleanVar(
        label='Run Tool ID Changes',
        default=True,
        description='Set to true to run tool ID removal changes.'
    )
    
    is_running_archive = BooleanVar(
        label='Run Archive Step',
        default=False,
        description='Set to true to archive devices that have no tool IDs. Only devices with statuses: Active, Decommissioning, Maintenance, or Onboarding Failed can be archived.'
    )
    
    is_adding_tool_ids = BooleanVar(
        label='Add Tool IDs',
        default=False,
        description='Set to true to add missing tool IDs to devices found in network tools.'
    )
    
    is_removing_from_archived_to_active = BooleanVar(
        label='Remove From Archived to Active',
        default=False,
        description='Set to true to move archived devices with tool IDs back to active status.'
    )

    is_making_changes = BooleanVar(
        label='Make Changes',
        default=False,
        description='Set to true to apply changes.'
    )

    def run(self, is_running_tool_id_changes, is_running_archive, is_adding_tool_ids, is_removing_from_archived_to_active, is_making_changes):
        self.logger.info(f"TOOL ID CLEANUP JOB: Starting with options - Tool ID Changes: {is_running_tool_id_changes}, Archive: {is_running_archive}, Add Tool IDs: {is_adding_tool_ids}, Remove From Archived: {is_removing_from_archived_to_active}, Making Changes: {is_making_changes}")
        
        # Validate that at least one option is selected
        if not is_running_tool_id_changes and not is_running_archive and not is_adding_tool_ids and not is_removing_from_archived_to_active:
            self.logger.error("TOOL ID CLEANUP JOB: At least one option (Tool ID Changes, Archive, Add Tool IDs, or Remove From Archived) must be selected")
            return
        
        all_changes = []
        
        # STEP 1: Tool ID Cleanup (only if selected)
        if is_running_tool_id_changes:
            self.logger.info("TOOL ID CLEANUP JOB: Starting Step 1 - Tool ID cleanup process")
            
            token = get_p42_token()
            
            # Get device data from all tools
            devices_netim = get_devices_from_tool(token, "netim", 0)  # period=0 for full sync
            devices_spectrum = get_devices_from_tool(token, "spectrum", 0)
            devices_akips = get_devices_from_tool(token, "akips", 0)
            devices_logicmonitor = get_devices_from_tool(token, "logicmonitor", 0)
            
            # Count LogicMonitor devices with/without serials for logging
            lm_with_serial_count = len([device for device in devices_logicmonitor if device.get('lm_serialnumber') and device.get('lm_serialnumber').strip() != ""])
            lm_no_serial_count = len(devices_logicmonitor) - lm_with_serial_count
            if lm_no_serial_count > 0:
                self.logger.info(f"TOOL ID CLEANUP JOB: {lm_no_serial_count} LogicMonitor devices have no serial (will use name matching for addition/removal)")
            
            # Log initial counts
            self.logger.info(f"TOOL ID CLEANUP JOB: Retrieved data - NetIM: {len(devices_netim)} devices, Spectrum: {len(devices_spectrum)} devices, AKIPS: {len(devices_akips)} devices, LogicMonitor: {len(devices_logicmonitor)} devices ({lm_with_serial_count} with serials)")
            
            # Apply NetIM data filtering (same as main job)
            original_netim_count = len(devices_netim)
        
            # Apply NetIM data filtering (same as main job)
            original_netim_count = len(devices_netim)
            
            # Remove F5 devices
            devices_netim = [device for device in devices_netim if 'netim_manufacturer' not in device or device['netim_manufacturer'] is None or not device['netim_manufacturer'].startswith("F5")]
            f5_filtered_count = original_netim_count - len(devices_netim)
            if f5_filtered_count > 0:
                self.logger.info(f"TOOL ID CLEANUP JOB: Filtered out {f5_filtered_count} F5 devices from NetIM data")
            
            # Clean URLs from NetIM device names
            urls_to_remove = [".aalcorp.aa.com", ".controlnet.equant.net", ".corpaa.aa.com"]
            url_name_changes = 0
            for device in devices_netim:
                original_name = device['netim_modelname']
                for url in urls_to_remove:
                    if url in device['netim_modelname']:
                        device['netim_modelname'] = device['netim_modelname'].replace(url, "")
                        url_name_changes += 1
                device['netim_modelname'] = device['netim_modelname'].upper()
            
            if url_name_changes > 0:
                self.logger.info(f"TOOL ID CLEANUP JOB: Cleaned URLs from {url_name_changes} NetIM device names")
            
            # Get all Nautobot devices (excluding ignored roles)
            devices_nautobot = Device.objects.all().exclude(role__name__in=self.IGNORED_DEVICE_ROLES)
            
            # Create tool ID removal changes (use full lists - name matching supported for all)
            spectrum_changes = self.create_tool_id_removal_changes(devices_nautobot, devices_spectrum, "spectrum")
            netim_changes = self.create_tool_id_removal_changes(devices_nautobot, devices_netim, "netim")
            akips_changes = self.create_tool_id_removal_changes_akips(devices_nautobot, devices_akips, "akips")
            logicmonitor_changes = self.create_tool_id_removal_changes(devices_nautobot, devices_logicmonitor, "logicmonitor")
            
            all_changes.extend(spectrum_changes)
            all_changes.extend(netim_changes)
            all_changes.extend(akips_changes)
            all_changes.extend(logicmonitor_changes)
            
            # Log summary
            total_removals = len(all_changes)
            self.logger.info(f"TOOL ID CLEANUP JOB: Step 1 completed - Found {total_removals} tool IDs to remove - Spectrum: {len(spectrum_changes)}, NetIM: {len(netim_changes)}, AKIPS: {len(akips_changes)}, LogicMonitor: {len(logicmonitor_changes)}")
            
            # Apply tool ID changes if requested
            if is_making_changes and total_removals > 0:
                self.logger.info(f"TOOL ID CLEANUP JOB: Applying {total_removals} tool ID removal changes...")
                
                successful_changes = 0
                failed_changes = 0
                
                for change in all_changes:
                    try:
                        change.change_status = self.apply_change(change)
                        if "applied" in change.change_status.lower():
                            successful_changes += 1
                        else:
                            failed_changes += 1
                    except Exception as e:
                        change.change_status = f"Failed: {e}"
                        failed_changes += 1
                        self.logger.error(f"TOOL ID CLEANUP JOB: Exception applying change for device '{change.device_name}': {e}")
                
                self.logger.info(f"TOOL ID CLEANUP JOB: Tool ID changes applied - {successful_changes} successful, {failed_changes} failed")
            elif total_removals > 0:
                self.logger.info(f"TOOL ID CLEANUP JOB: {total_removals} tool ID removals identified but not applied (is_making_changes=False)")
            else:
                self.logger.info(f"TOOL ID CLEANUP JOB: No tool ID removals needed")
                
        
        # STEP 2: Add missing tool IDs to devices found in network tools (only if selected)
        tool_id_additions = []
        if is_adding_tool_ids:
            self.logger.info("TOOL ID CLEANUP JOB: Starting Step 2 - Add missing tool IDs")
            
            # Only get tool data if we haven't already fetched it in step 1
            if not is_running_tool_id_changes:
                token = get_p42_token()
                
                # Get device data from all tools
                devices_netim = get_devices_from_tool(token, "netim", 0)
                devices_spectrum = get_devices_from_tool(token, "spectrum", 0)
                devices_akips = get_devices_from_tool(token, "akips", 0)
                devices_logicmonitor = get_devices_from_tool(token, "logicmonitor", 0)
                
                self.logger.info(f"TOOL ID CLEANUP JOB: Retrieved data for tool ID addition - NetIM: {len(devices_netim)} devices, Spectrum: {len(devices_spectrum)} devices, AKIPS: {len(devices_akips)} devices, LogicMonitor: {len(devices_logicmonitor)} devices")
                
                # Apply same filtering as step 1
                original_netim_count = len(devices_netim)
                devices_netim = [device for device in devices_netim if 'netim_manufacturer' not in device or device['netim_manufacturer'] is None or not device['netim_manufacturer'].startswith("F5")]
                
                # Clean URLs from NetIM device names
                urls_to_remove = [".aalcorp.aa.com", ".controlnet.equant.net", ".corpaa.aa.com"]
                for device in devices_netim:
                    for url in urls_to_remove:
                        if url in device['netim_modelname']:
                            device['netim_modelname'] = device['netim_modelname'].replace(url, "")
                    device['netim_modelname'] = device['netim_modelname'].upper()
            
            # Use full lists for addition - name matching is now supported when serial is not available
            tool_id_additions = self.add_missing_tool_ids(devices_netim, devices_spectrum, devices_akips, devices_logicmonitor, is_making_changes)
            
            self.logger.info(f"TOOL ID CLEANUP JOB: Step 2 completed - {len(tool_id_additions)} tool ID additions processed")
        
        # STEP 3: Archive devices without tool IDs (only if selected)
        archive_changes = []
        if is_running_archive:
            self.logger.info("TOOL ID CLEANUP JOB: Starting Step 3 - Archive devices without tool IDs")
            
            archive_changes = self.archive_devices_without_tool_ids(is_making_changes)
            
            self.logger.info(f"TOOL ID CLEANUP JOB: Step 3 completed - {len(archive_changes)} devices processed for archiving")
        
        # STEP 4: Remove archived devices with tool IDs back to active (only if selected)
        unarchive_changes = []
        if is_removing_from_archived_to_active:
            self.logger.info("TOOL ID CLEANUP JOB: Starting Step 4 - Remove archived devices with tool IDs back to active")
            
            unarchive_changes = self.unarchive_devices_with_tool_ids(is_making_changes)
            
            self.logger.info(f"TOOL ID CLEANUP JOB: Step 4 completed - {len(unarchive_changes)} devices processed for unarchiving")
        
        # Create CSV files
        if all_changes:
            csv_content = create_panda_and_csv(all_changes)
            self.create_file("tool_id_cleanup_changes.csv", csv_content)
        
        if archive_changes:
            archive_csv_content = create_panda_and_csv(archive_changes)
            self.create_file("archived_devices.csv", archive_csv_content)
            
        if tool_id_additions:
            additions_csv_content = create_panda_and_csv(tool_id_additions)
            self.create_file("tool_id_additions.csv", additions_csv_content)
            
        if unarchive_changes:
            unarchive_csv_content = create_panda_and_csv(unarchive_changes)
            self.create_file("unarchived_devices.csv", unarchive_csv_content)
        
        # Final summary
        total_tool_id_changes = len([c for c in all_changes if c.change_status and "applied" in c.change_status.lower()])
        total_archive_changes = len([c for c in archive_changes if hasattr(c, 'change_status') and c.change_status and "applied" in c.change_status.lower()])
        total_addition_changes = len([c for c in tool_id_additions if hasattr(c, 'change_status') and c.change_status and "applied" in c.change_status.lower()])
        total_unarchive_changes = len([c for c in unarchive_changes if hasattr(c, 'change_status') and c.change_status and "applied" in c.change_status.lower()])
        
        self.logger.info(f"TOOL ID CLEANUP JOB: Job completed - Tool ID removals applied: {total_tool_id_changes}, Archive changes applied: {total_archive_changes}, Tool ID additions applied: {total_addition_changes}, Unarchive changes applied: {total_unarchive_changes}")

    def archive_devices_without_tool_ids(self, is_making_changes):
        """Archive devices that have no tool IDs (similar to device_fetch_period logic)"""
        archived_devices = []
        
        self.logger.info(f"DEVICE ARCHIVING: Starting device archiving process - Making Changes: {is_making_changes}")
        
        # Only devices with these statuses can be moved to Archived
        allowed_statuses = ["Active", "Decommissioning", "Maintenance", "Onboarding Failed"]
        devices_eligible_for_archiving = Device.objects.filter(status__name__in=allowed_statuses).exclude(role__name__in=self.IGNORED_DEVICE_ROLES)
        self.logger.info(f"DEVICE ARCHIVING: Checking {devices_eligible_for_archiving.count()} devices with statuses {allowed_statuses} for archiving (excluding roles: {self.IGNORED_DEVICE_ROLES})")
        
        devices_to_archive = 0
        successful_archives = 0
        failed_archives = 0
        
        for device in devices_eligible_for_archiving:
            netim_id = device.cf.get('netim_id')
            spectrum_id = device.cf.get('spectrum_id')
            akips_id = device.cf.get('akips_id')
            logicmonitor_id = device.cf.get('logicmonitor_id')
            
            # Check if device has no tool IDs
            if ((spectrum_id is None or spectrum_id == "") and 
                (netim_id is None or netim_id == "") and 
                (akips_id is None or akips_id == "") and
                (logicmonitor_id is None or logicmonitor_id == "")):
                
                devices_to_archive += 1
                
                # Create archive change object
                archive_change = DeviceChange(
                    provider="archive", 
                    serial=device.serial, 
                    field_changed="Status", 
                    current_value=device.status.name, 
                    change_value="Archived", 
                    device_name=device.name, 
                    device_id=device.id
                )
                
                if is_making_changes:
                    try:
                        archive_change.change_status = self.archive_device(device)
                        if "archived" in archive_change.change_status.lower():
                            successful_archives += 1
                        else:
                            failed_archives += 1
                    except Exception as e:
                        archive_change.change_status = f"Failed: {e}"
                        failed_archives += 1
                        self.logger.error(f"DEVICE ARCHING: Exception archiving device '{device.name}': {e}")
                else:
                    archive_change.change_status = "Not Applied"
                
                archived_devices.append(archive_change)
                
        
        if is_making_changes:
            self.logger.info(f"DEVICE ARCHING SUMMARY: Found {devices_to_archive} devices eligible for archiving - {successful_archives} successful, {failed_archives} failed")
        else:
            self.logger.info(f"DEVICE ARCHING SUMMARY: Found {devices_to_archive} devices eligible for archiving (changes not applied)")
        
        return archived_devices

    def archive_device(self, device):
        """Archive a single device by changing its status to Archived, removing from virtual chassis, and removing IP addresses"""
        try:
            # Get the "Archived" status
            archived_status = Status.objects.get_for_model(Device).get(name="Archived")
            
            # Store original status for logging
            original_status = device.status.name
            original_name = device.name
            
            # Remove device from virtual chassis if it's a member
            vc_removed = False
            if device.virtual_chassis:
                vc_name = device.virtual_chassis.name
                vc_master = device.virtual_chassis.master
                
                # If this device is the VC master, we need to handle it specially
                if vc_master and vc_master.id == device.id:
                    self.logger.warning(f"DEVICE ARCHING: Device '{device.name}' is the master of virtual chassis '{vc_name}'. Removing VC master designation.")
                    device.virtual_chassis.master = None
                    device.virtual_chassis.validated_save()
                
                # Remove device from virtual chassis
                device.virtual_chassis = None
                vc_removed = True
                self.logger.debug(f"DEVICE ARCHING: Removed device '{device.name}' from virtual chassis '{vc_name}'")
            
            # Remove all IP addresses assigned to this device
            ip_addresses = IPAddress.objects.filter(assigned_object_id=device.id)
            ip_count = ip_addresses.count()
            if ip_count > 0:
                ip_list = [str(ip.address) for ip in ip_addresses]
                for ip in ip_addresses:
                    ip.assigned_object_id = None
                    ip.assigned_object_type = None
                    ip.validated_save()
                self.logger.debug(f"DEVICE ARCHING: Removed {ip_count} IP address(es) from device '{device.name}': {', '.join(ip_list)}")
            
            # Create timestamp for archived name (same format as jobhook)
            time_stamp = str(datetime.now()).split(".")[0]
            archived_name = f"{device.name} - Archived ({time_stamp})"
            
            # Update device status and name
            device.status = archived_status
            device.name = archived_name
            device.validated_save()
            
            status_msg = f"Device archived - Status changed from {original_status} to Archived, name updated to {archived_name}"
            if vc_removed:
                status_msg += ", removed from virtual chassis"
            if ip_count > 0:
                status_msg += f", removed {ip_count} IP address(es)"
            
            self.logger.debug(f"DEVICE ARCHING: Successfully archived device '{original_name}' (ID: {device.id}) - {status_msg}")
            return status_msg
            
        except Status.DoesNotExist:
            self.logger.error(f"DEVICE ARCHING: 'Archived' status not found in Nautobot")
            return "Failed: Archived status not found"
        except Exception as e:
            self.logger.error(f"DEVICE ARCHING: Error archiving device '{device.name}': {e}")
            return f"Failed: {e}"

    def unarchive_devices_with_tool_ids(self, is_making_changes):
        """Move archived devices that have tool IDs back to active status"""
        unarchive_changes = []
        
        self.logger.info(f"DEVICE UNARCHING: Starting device unarching process - Making Changes: {is_making_changes}")
        
        archived_devices = Device.objects.filter(status__name="Archived").exclude(role__name__in=self.IGNORED_DEVICE_ROLES)
        self.logger.info(f"DEVICE UNARCHING: Checking {archived_devices.count()} archived devices for unarching (excluding roles: {self.IGNORED_DEVICE_ROLES})")
        
        devices_to_unarchive = 0
        successful_unarchives = 0
        failed_unarchives = 0
        
        for device in archived_devices:
            netim_id = device.cf.get('netim_id')
            spectrum_id = device.cf.get('spectrum_id')
            akips_id = device.cf.get('akips_id')
            logicmonitor_id = device.cf.get('logicmonitor_id')
            
            # Check if device has any tool IDs (including LogicMonitor)
            if ((spectrum_id is not None and spectrum_id != "") or 
                (netim_id is not None and netim_id != "") or 
                (akips_id is not None and akips_id != "") or
                (logicmonitor_id is not None and logicmonitor_id != "")):
                
                devices_to_unarchive += 1
                
                # Create unarchive change object
                unarchive_change = DeviceChange(
                    provider="unarchive", 
                    serial=device.serial, 
                    field_changed="Status", 
                    current_value="Archived", 
                    change_value="Active", 
                    device_name=device.name, 
                    device_id=device.id
                )
                
                if is_making_changes:
                    try:
                        unarchive_change.change_status = self.unarchive_device(device)
                        if "unarchived" in unarchive_change.change_status.lower():
                            successful_unarchives += 1
                        else:
                            failed_unarchives += 1
                    except Exception as e:
                        unarchive_change.change_status = f"Failed: {e}"
                        failed_unarchives += 1
                        self.logger.error(f"DEVICE UNARCHING: Exception unarching device '{device.name}': {e}")
                else:
                    unarchive_change.change_status = "Not Applied"
                
                unarchive_changes.append(unarchive_change)
                
        
        if is_making_changes:
            self.logger.info(f"DEVICE UNARCHING SUMMARY: Found {devices_to_unarchive} devices eligible for unarching - {successful_unarchives} successful, {failed_unarchives} failed")
        else:
            self.logger.info(f"DEVICE UNARCHING SUMMARY: Found {devices_to_unarchive} devices eligible for unarching (changes not applied)")
        
        return unarchive_changes

    def unarchive_device(self, device):
        """Unarchive a single device by changing its status to Active and cleaning the name"""
        try:
            # Get the "Active" status
            active_status = Status.objects.get_for_model(Device).get(name="Active")
            
            # Store original status and name for logging
            original_status = device.status.name
            original_name = device.name
            
            # Clean the device name by removing "- Archived" suffix and timestamp
            cleaned_name = self.clean_device_name_from_archived(device.name)
            
            # Update device status and name
            device.status = active_status
            device.name = cleaned_name
            
            try:
                device.validated_save()
                self.logger.debug(f"DEVICE UNARCHING: Successfully unarchived device (ID: {device.id}) - Status changed from '{original_status}' to 'Active', name changed from '{original_name}' to '{cleaned_name}'")
                return f"Device unarchived - Status changed from {original_status} to Active, name changed from '{original_name}' to '{cleaned_name}'"
                
            except Exception as validation_error:
                # Check if it's a name conflict error
                error_str = str(validation_error)
                if 'name' in error_str and 'already exists' in error_str:
                    self.logger.warning(f"DEVICE UNARCHING: Name conflict for device '{cleaned_name}' - attempting to resolve by finding next available stack number")
                    
                    # Find the next available stack number
                    new_name = self.find_next_available_stack_name(cleaned_name)
                    
                    if new_name != cleaned_name:
                        self.logger.debug(f"DEVICE UNARCHING: Resolved name conflict - using '{new_name}' instead of '{cleaned_name}'")
                        device.name = new_name
                        device.validated_save()
                        
                        self.logger.debug(f"DEVICE UNARCHING: Successfully unarchived device (ID: {device.id}) with conflict resolution - Status changed from '{original_status}' to 'Active', name changed from '{original_name}' to '{new_name}'")
                        return f"Device unarchived with name conflict resolution - Status changed from {original_status} to Active, name changed from '{original_name}' to '{new_name}'"
                    else:
                        self.logger.error(f"DEVICE UNARCHING: Could not resolve name conflict for device '{cleaned_name}': {validation_error}")
                        return f"Failed: Could not resolve name conflict - {validation_error}"
                else:
                    # Re-raise if it's not a name conflict error
                    raise validation_error
            
        except Status.DoesNotExist:
            self.logger.error(f"DEVICE UNARCHING: 'Active' status not found in Nautobot")
            return "Failed: Active status not found"
        except Exception as e:
            self.logger.error(f"DEVICE UNARCHING: Error unarching device '{device.name}': {e}")
            return f"Failed: {e}"

    def add_missing_tool_ids(self, devices_netim, devices_spectrum, devices_akips, devices_logicmonitor, is_making_changes):
        """Add missing tool IDs to Nautobot devices that are found in network tools"""
        tool_id_additions = []
        
        # Get all Nautobot devices (excluding ignored roles)
        devices_nautobot = Device.objects.all().exclude(role__name__in=self.IGNORED_DEVICE_ROLES)
        
        self.logger.info(f"TOOL ID ADDITION: Starting tool ID addition process - Checking {devices_nautobot.count()} Nautobot devices")
        
        # Process all providers using the unified function
        netim_additions = self.add_tool_ids_from_api(devices_nautobot, devices_netim, "netim", is_making_changes)
        tool_id_additions.extend(netim_additions)
        
        spectrum_additions = self.add_tool_ids_from_api(devices_nautobot, devices_spectrum, "spectrum", is_making_changes)
        tool_id_additions.extend(spectrum_additions)
        
        akips_additions = self.add_tool_ids_from_api(devices_nautobot, devices_akips, "akips", is_making_changes)
        tool_id_additions.extend(akips_additions)
        
        logicmonitor_additions = self.add_tool_ids_from_api(devices_nautobot, devices_logicmonitor, "logicmonitor", is_making_changes)
        tool_id_additions.extend(logicmonitor_additions)
        
        if is_making_changes:
            successful_additions = len([c for c in tool_id_additions if c.change_status and "applied" in c.change_status.lower()])
            failed_additions = len([c for c in tool_id_additions if c.change_status and "failed" in c.change_status.lower()])
            self.logger.info(f"TOOL ID ADDITION SUMMARY: {successful_additions} successful additions, {failed_additions} failed additions")
        else:
            self.logger.info(f"TOOL ID ADDITION SUMMARY: Found {len(tool_id_additions)} potential tool ID additions (changes not applied)")
        
        return tool_id_additions

    def add_tool_ids_from_api(self, devices_nautobot, devices_api, provider, is_making_changes):
        """
        Unified function to add tool IDs from any provider's API data.
        Handles NetIM, Spectrum, AKIPS, and LogicMonitor with provider-specific logic.
        """
        additions = []
        
        # Provider-specific key mappings
        if provider == "netim":
            serial_key = "netim_serialnumber"
            id_key = "netim_netimid"
            name_key = "netim_modelname"
        elif provider == "spectrum":
            serial_key = "spectrum_serialnumber"
            id_key = "spectrum_modelhandle"
            name_key = "spectrum_modelname"
        elif provider == "akips":
            serial_key = "akips_serialnumber"
            id_key = "akips_hostname"  # AKIPS uses hostname as the ID
            name_key = "akips_hostname"
        elif provider == "logicmonitor":
            serial_key = "lm_serialnumber"
            id_key = "lm_lmid"
            name_key = "lm_devicename"
        else:
            self.logger.error(f"TOOL ID ADDITION: Unknown provider '{provider}'")
            return additions
        
        self.logger.info(f"TOOL ID ADDITION: Processing {len(devices_api)} {provider.upper()} devices for tool ID addition")
        
        devices_processed = 0
        
        # AKIPS has a different structure with members - serial matching only
        if provider == "akips":
            # Track which Nautobot devices we've already matched to avoid duplicates
            matched_nautobot_ids = set()
            
            for akips_device in devices_api:
                devices_processed += 1
                
                if devices_processed % 500 == 0:
                    self.logger.debug(f"TOOL ID ADDITION: Processed {devices_processed}/{len(devices_api)} {provider.upper()} devices...")
                
                akips_id = akips_device.get("akips_hostname", "")
                if not akips_id:
                    continue
                
                members = akips_device.get("members", [])
                
                if members and len(members) > 0:
                    for idx, member in enumerate(members, start=1):
                        member_serial = member.get("akips_serialnumber", "")
                        member_serial_clean = str(member_serial).strip().upper() if member_serial else ""
                        
                        matched_device = None
                        
                        # Try serial matching first if serial exists
                        if member_serial_clean:
                            matched_device = self.find_matching_nautobot_device(member_serial, "", devices_nautobot, provider)
                        
                        # Fallback to hostname matching if no serial or serial didn't match
                        if not matched_device and akips_id:
                            matched_device = self.find_matching_nautobot_device_by_name(akips_id, devices_nautobot, member_serial)
                            if matched_device:
                                self.logger.debug(f"TOOL ID ADDITION: Matched device '{matched_device.name}' to AKIPS hostname '{akips_id}' by name (no serial)")
                        
                        if matched_device and matched_device.id not in matched_nautobot_ids:
                            current_tool_id = matched_device.cf.get(f"{provider}_id")
                            if not current_tool_id:
                                addition = self._create_and_apply_addition(matched_device, provider, akips_id, is_making_changes)
                                if addition:
                                    additions.append(addition)
                                    matched_nautobot_ids.add(matched_device.id)
        else:
            # Standard processing for NetIM, Spectrum, LogicMonitor
            # Track which Nautobot devices we've already matched to avoid duplicates
            matched_nautobot_ids = set()
            
            for api_device in devices_api:
                devices_processed += 1
                
                if devices_processed % 500 == 0:
                    self.logger.debug(f"TOOL ID ADDITION: Processed {devices_processed}/{len(devices_api)} {provider.upper()} devices...")
                
                api_serial = api_device.get(serial_key, "")
                api_id = api_device.get(id_key, "")
                api_name = api_device.get(name_key, "")
                api_mac = api_device.get('lm_mac', "") if provider == 'logicmonitor' else None
                
                # Skip if no ID to add
                if not api_id:
                    continue
                
                matched_device = None
                
                # Try serial matching first if serial exists
                if api_serial and str(api_serial).strip():
                    matched_device = self.find_matching_nautobot_device(api_serial, "", devices_nautobot, provider)
                
                # For LogicMonitor, try MAC matching if serial didn't work (only for UPS devices)
                if not matched_device and provider == 'logicmonitor' and api_mac and str(api_mac).strip():
                    # Only use MAC matching for UPS devices (devices without serial numbers)
                    api_snmpgroup = api_device.get('lm_snmpgroup', '')
                    if api_snmpgroup and 'UPS' in api_snmpgroup.upper():
                        matched_device = self.find_matching_nautobot_device_by_mac(api_mac, devices_nautobot)
                        if matched_device:
                            self.logger.debug(f"TOOL ID ADDITION: Matched UPS device '{matched_device.name}' to LogicMonitor device by MAC address '{api_mac}'")
                
                # Fallback to name matching if no serial/MAC or neither matched
                if not matched_device and api_name and str(api_name).strip():
                    matched_device = self.find_matching_nautobot_device_by_name(api_name, devices_nautobot, api_serial)
                    if matched_device:
                        self.logger.debug(f"TOOL ID ADDITION: Matched device '{matched_device.name}' to {provider.upper()} device '{api_name}' by name (no serial/MAC in API data)")
                
                if matched_device and matched_device.id not in matched_nautobot_ids:
                    current_tool_id = matched_device.cf.get(f"{provider}_id")
                    
                    # Only add if tool ID is missing
                    if not current_tool_id:
                        addition = self._create_and_apply_addition(matched_device, provider, api_id, is_making_changes)
                        if addition:
                            additions.append(addition)
                            matched_nautobot_ids.add(matched_device.id)
        
        self.logger.debug(f"TOOL ID ADDITION: Completed {provider.upper()} processing - {len(additions)} tool IDs scheduled for addition")
        return additions

    def _create_and_apply_addition(self, matched_device, provider, api_id, is_making_changes):
        """Helper to create a DeviceChange and optionally apply it."""
        addition_change = DeviceChange(
            provider=provider,
            serial=matched_device.serial,
            field_changed="API ID",
            current_value=None,
            change_value=api_id,
            device_name=matched_device.name,
            device_id=matched_device.id
        )
        
        if is_making_changes:
            try:
                addition_change.change_status = self.apply_tool_id_addition(matched_device, provider, api_id)
            except Exception as e:
                addition_change.change_status = f"Failed: {e}"
                self.logger.error(f"TOOL ID ADDITION: Exception adding {provider.upper()} ID to device '{matched_device.name}': {e}")
        else:
            addition_change.change_status = "Not Applied"
        
        self.logger.debug(f"TOOL ID ADDITION: Device '{matched_device.name}' (Serial: {matched_device.serial}) matched - adding {provider.upper()} ID '{api_id}'")
        return addition_change

    def _normalize_serial(self, serial):
        """Normalize serial values for matching."""
        if serial is None:
            return ""
        return str(serial).strip().upper()

    def _serials_are_compatible(self, nautobot_serial, api_serial):
        """Allow name fallback only when serials match or one side lacks a serial."""
        normalized_nautobot_serial = self._normalize_serial(nautobot_serial)
        normalized_api_serial = self._normalize_serial(api_serial)

        if not normalized_nautobot_serial or not normalized_api_serial:
            return True

        return normalized_nautobot_serial == normalized_api_serial

    def find_matching_nautobot_device(self, api_serial, api_name, devices_nautobot, provider):
        """Find matching Nautobot device using serial-only matching logic"""
        
        # First try serial matching
        if api_serial and str(api_serial).strip():
            api_serial_clean = self._normalize_serial(api_serial)
            
            for device in devices_nautobot:
                if device.serial and str(device.serial).strip():
                    nautobot_serial_clean = self._normalize_serial(device.serial)
                    if nautobot_serial_clean == api_serial_clean:
                        return device
        
        return None

    def find_matching_nautobot_device_by_name(self, api_name, devices_nautobot, api_serial=None):
        """Find a matching Nautobot device by name using fuzzy matching.
        
        Supports:
        - Case-insensitive matching
        - Domain suffix stripping (.aalcorp.aa.com, .corpaa.aa.com, etc.)
        - Partial/endswith matching for serial-less devices
        """
        if not api_name:
            return None
        
        # Clean the API name - strip domain suffixes and normalize
        cleaned_api_name = self._clean_name_for_matching(api_name)
        
        # First, try for an exact match on the cleaned name
        for device in devices_nautobot:
            if device.name:
                cleaned_device_name = self._clean_name_for_matching(device.name)
                if cleaned_device_name == cleaned_api_name and self._serials_are_compatible(device.serial, api_serial):
                    return device
        
        # Second pass: try partial/endswith matching
        for device in devices_nautobot:
            if device.name:
                cleaned_device_name = self._clean_name_for_matching(device.name)
                # Check if one name ends with the other
                if (cleaned_device_name.endswith(cleaned_api_name) or cleaned_api_name.endswith(cleaned_device_name)) and self._serials_are_compatible(device.serial, api_serial):
                    return device
        
        return None
    
    def _clean_name_for_matching(self, name):
        """Clean device name by removing common domain suffixes for fuzzy matching."""
        if not name:
            return ""
        
        urls_to_remove = [".aalcorp.aa.com", ".controlnet.equant.net", ".corpaa.aa.com"]
        cleaned_name = name.strip().upper()
        
        for url in urls_to_remove:
            if cleaned_name.lower().endswith(url.lower()):
                cleaned_name = cleaned_name[:-len(url)]
                break
        
        return cleaned_name
    
    def _normalize_mac_address(self, mac):
        """
        Normalize MAC address to uppercase with colons (AA:BB:CC:DD:EE:FF).
        Handles various input formats: aa:bb:cc:dd:ee:ff, aa-bb-cc-dd-ee-ff, aabbccddeeff
        """
        if not mac:
            return None
        
        # Remove common separators and convert to uppercase
        mac_clean = mac.replace(':', '').replace('-', '').replace('.', '').upper().strip()
        
        # Validate length (should be 12 hex characters)
        if len(mac_clean) != 12:
            return mac.upper().strip()  # Return as-is if invalid format
        
        # Format as AA:BB:CC:DD:EE:FF
        return ':'.join(mac_clean[i:i+2] for i in range(0, 12, 2))
    
    def find_matching_nautobot_device_by_mac(self, api_mac, devices_nautobot):
        """Find a matching Nautobot device by MAC address on its interfaces.
        
        For LogicMonitor serial-less devices, MAC is stored on the device's interface.
        """
        if not api_mac:
            return None
        
        normalized_api_mac = self._normalize_mac_address(api_mac)
        if not normalized_api_mac:
            return None
        
        # Query Interface model directly for the MAC address
        matching_interface = Interface.objects.filter(mac_address__iexact=normalized_api_mac).first()
        if matching_interface and matching_interface.device:
            return matching_interface.device
        
        return None

    def apply_tool_id_addition(self, device, provider, tool_id):
        """Apply the tool ID addition to the device."""
        field_name = f"{provider}_id"
        
        self.logger.debug(f"TOOL ID ADDITION START: Device='{device.name}', ID={device.id}, Serial='{device.serial}', Provider='{provider}', ToolID='{tool_id}', CurrentValue='{device.cf.get(field_name)}'")
        
        try:
            if tool_id is not None:
                tool_id = str(tool_id)
            
            self.logger.debug(f"TOOL ID ADDITION: Setting device.cf['{field_name}'] = '{tool_id}'")
            device.cf[field_name] = tool_id
            
            self.logger.debug(f"TOOL ID ADDITION: Calling validated_save() for device '{device.name}'")
            device.validated_save()
            
            # Verify the change was applied
            device.refresh_from_db()
            new_value = device.cf.get(field_name)
            self.logger.debug(f"TOOL ID ADDITION SUCCESS (validated_save): Device='{device.name}', Field='{field_name}', NewValue='{new_value}', Expected='{tool_id}', Match={new_value == tool_id}")
            
            return f"Change applied - {provider.upper()} ID '{tool_id}' added"

        except Exception as e:
            self.logger.warning(f"TOOL ID ADDITION: validated_save() failed for device '{device.name}': {e}. Attempting fallback...")
            
            try:
                self.logger.debug(f"TOOL ID ADDITION: Attempting direct update for device '{device.name}' (pk={device.pk})")
                
                # Fallback to direct update - must merge with existing custom field data
                # First get current custom field data
                device.refresh_from_db()
                current_cf_data = device._custom_field_data.copy() if device._custom_field_data else {}
                current_cf_data[field_name] = tool_id
                
                rows_updated = Device.objects.filter(pk=device.pk).update(_custom_field_data=current_cf_data)
                self.logger.debug(f"TOOL ID ADDITION: Direct update returned rows_updated={rows_updated}")
                
                # Refresh and verify the change was applied
                device.refresh_from_db()
                new_value = device.cf.get(field_name)
                self.logger.debug(f"TOOL ID ADDITION SUCCESS (direct update): Device='{device.name}', Field='{field_name}', NewValue='{new_value}', Expected='{tool_id}', Match={new_value == tool_id}, RowsUpdated={rows_updated}")
                
                return f"Change applied via fallback - {provider.upper()} ID '{tool_id}' added"
                
            except Exception as fallback_e:
                self.logger.error(f"TOOL ID ADDITION FAILED: Device='{device.name}', Both methods failed. validated_save error: {e}, direct update error: {fallback_e}")
                return f"Failed on both attempts: {fallback_e}"

    def clean_device_name_from_archived(self, device_name):
        """
        Remove '- Archived' suffix and any parenthetical timestamp from device name.
        """
        if not device_name:
            return device_name
            
        # Remove ' - Archived' and any following content including parenthetical timestamps
        cleaned_name = re.sub(r'\s*-\s*Archived.*$', '', device_name).strip()
        return cleaned_name

    def find_next_available_stack_name(self, base_name):
        """
        Find the next available stack name by appending ' Stack N' where N is an incrementing number.
        Used to resolve name conflicts when unarchiving devices.
        
        Args:
            base_name: The base device name (e.g., 'LAX-HGR3-ASW011')
        
        Returns:
        Find the next available stack name by appending ' - Stack N' where N is an incrementing number.
        Used to resolve name conflicts when unarchiving devices.
        
        Args:
            base_name: The base device name (e.g., 'LAX-HGR3-ASW011')
        
        Returns:
            str: Available name with stack number (e.g., 'LAX-HGR3-ASW011 - Stack 2')
        """
        # Try stack numbers from 2 to 100
        for stack_num in range(2, 101):
            candidate_name = f"{base_name} - Stack {stack_num}"
            if not Device.objects.filter(name=candidate_name).exists():
                return candidate_name
        
        # If all stack numbers are taken, use timestamp as last resort
        import time
        timestamp = int(time.time())
        return f"{base_name} - Stack {timestamp}"

    def create_tool_id_removal_changes(self, devices_nautobot, devices_api, provider):
        """Create changes to remove tool IDs from devices no longer found in the tool.
        
        Handles NetIM, Spectrum, and LogicMonitor. AKIPS uses a separate function due to its unique data structure.
        Matching is done by serial number OR name. If either matches, keep the ID.
        """
        changes = []
        
        # Provider-specific key mappings
        if provider == "netim":
            serial_key = "netim_serialnumber"
            name_key = "netim_modelname"
            id_field = "netim_id"
        elif provider == "spectrum":
            serial_key = "spectrum_serialnumber"
            name_key = "spectrum_modelname"
            id_field = "spectrum_id"
        elif provider == "logicmonitor":
            serial_key = "lm_serialnumber"
            name_key = "lm_devicename"
            id_field = "logicmonitor_id"
        else:
            self.logger.error(f"TOOL ID CLEANUP: Unknown provider '{provider}' - use create_tool_id_removal_changes_akips for AKIPS")
            return changes
        
        # Build a set of serial numbers from API data for fast lookup
        api_serials = {
            device.get(serial_key, '').strip().upper() 
            for device in devices_api 
            if device.get(serial_key) and device.get(serial_key).strip()
        }
        
        # Build name records so fallback matching can enforce serial compatibility.
        api_name_records = [
            {
                "name": device.get(name_key, '').strip().upper(),
                "serial": self._normalize_serial(device.get(serial_key, '')),
            }
            for device in devices_api
            if device.get(name_key) and device.get(name_key).strip()
        ]
        
        # Build a set of MAC addresses for LogicMonitor UPS devices only (normalized format)
        api_macs = set()
        if provider == "logicmonitor":
            for device in devices_api:
                # Only add MAC for UPS devices (devices without serial numbers)
                snmpgroup = device.get('lm_snmpgroup', '')
                if snmpgroup and 'UPS' in snmpgroup.upper():
                    mac = device.get('lm_mac', '')
                    if mac and mac.strip():
                        normalized_mac = self._normalize_mac_address(mac)
                        if normalized_mac:
                            api_macs.add(normalized_mac)
        
        self.logger.info(f"TOOL ID CLEANUP: Starting {provider.upper()} ID cleanup process - Checking {devices_nautobot.count()} Nautobot devices against {len(api_serials)} serials, {len(api_macs)} MACs, and {len(api_name_records)} names")
        
        devices_with_tool_id = 0
        devices_found_in_api = 0
        devices_to_clear = 0
        
        for device in devices_nautobot:
            current_tool_id = device.cf.get(id_field, None)
            
            # Only process devices that have the tool ID
            if current_tool_id is None or current_tool_id == "":
                continue
                
            devices_with_tool_id += 1
            device_serial = (device.serial or '').strip().upper()
            device_found = False
            
            # Check if device serial exists in API serials
            if device_serial and device_serial in api_serials:
                device_found = True
                devices_found_in_api += 1
                self.logger.debug(f"TOOL ID CLEANUP: Device '{device.name}' (Serial: {device.serial}) found in {provider.upper()} by serial - keeping ID {current_tool_id}")
            
            # For LogicMonitor, try MAC matching if serial didn't match
            if not device_found and provider == "logicmonitor" and api_macs:
                # Get MAC addresses from device interfaces (for serial-less LogicMonitor devices)
                device_interfaces = Interface.objects.filter(device=device, mac_address__isnull=False).exclude(mac_address='')
                for interface in device_interfaces:
                    if interface.mac_address:
                        normalized_device_mac = self._normalize_mac_address(str(interface.mac_address))
                        if normalized_device_mac and normalized_device_mac in api_macs:
                            device_found = True
                            devices_found_in_api += 1
                            self.logger.debug(f"TOOL ID CLEANUP: Device '{device.name}' (MAC: {interface.mac_address} on {interface.name}) found in {provider.upper()} by MAC - keeping ID {current_tool_id}")
                            break
            
            if not device_found:
                # Fallback to name matching
                parsed_name = self.clean_device_name_from_archived(device.name).upper()
                normalized_device_serial = self._normalize_serial(device.serial)
                
                for api_record in api_name_records:
                    api_name = api_record["name"]
                    if not api_name:
                        continue

                    exact_match = parsed_name == api_name
                    partial_match = parsed_name.endswith(api_name)
                    if not exact_match and not partial_match:
                        continue

                    if not self._serials_are_compatible(normalized_device_serial, api_record["serial"]):
                        continue

                    device_found = True
                    devices_found_in_api += 1
                    if exact_match:
                        self.logger.debug(f"TOOL ID CLEANUP: Device '{device.name}' found in {provider.upper()} by exact name match - keeping ID {current_tool_id}")
                    else:
                        self.logger.debug(f"TOOL ID CLEANUP: Device '{device.name}' found in {provider.upper()} by partial name match (endswith) '{api_name}' - keeping ID {current_tool_id}")
                    break
            
            if not device_found:
                devices_to_clear += 1
                self.logger.debug(f"TOOL ID CLEANUP: Device '{device.name}' (ID: {device.id}, Serial: {device.serial}) not found in {provider.upper()} - scheduling {provider.upper()} ID '{current_tool_id}' for removal")
                changes.append(DeviceChange(provider, device.serial, "API ID", current_tool_id, None, device.name, device.id))
        
        self.logger.info(f"TOOL ID CLEANUP SUMMARY: {provider.upper()} - Devices with {provider.upper()} ID: {devices_with_tool_id}, Found in API: {devices_found_in_api}, Scheduled for ID removal: {devices_to_clear}")
        return changes

    def create_tool_id_removal_changes_akips(self, devices_nautobot, devices_api, provider):
        """Create changes to remove AKIPS IDs from devices no longer found in AKIPS.
        
        AKIPS has a unique data structure with nested 'members' containing serial numbers,
        so it requires its own function. Matching is done by serial number OR name.
        If either matches, keep the ID.
        """
        changes = []
        self.logger.info(f"TOOL ID CLEANUP: Starting {provider.upper()} ID cleanup process - Checking {len(devices_nautobot)} Nautobot devices against {len(devices_api)} API devices")
        
        # Build lookup structures for AKIPS data
        # Set of all member serial numbers for fast serial lookup
        akips_serials = set()
        # Hostname records keep serial context so conflicting serials do not match by name.
        akips_name_records = []
        
        for device_akips in devices_api:
            akips_hostname = device_akips.get('akips_hostname', '').strip().upper()
            if akips_hostname:
                member_serials = set()
                for member in device_akips.get('members', []):
                    serial = self._normalize_serial(member.get('akips_serialnumber', ''))
                    if serial:
                        akips_serials.add(serial)
                        member_serials.add(serial)
                akips_name_records.append({"name": akips_hostname, "serials": member_serials})
        
        self.logger.info(f"TOOL ID CLEANUP: Built lookup set with {len(akips_serials)} AKIPS member serials and {len(akips_name_records)} hostnames for name matching")
        
        devices_with_tool_id = 0
        devices_found_in_api = 0
        devices_to_clear = 0
        
        for device in devices_nautobot:
            current_akips_id = device.cf.get(provider + "_id", None)
            
            # Only process devices that have the akips_id
            if current_akips_id is None or current_akips_id == "":
                continue
                
            devices_with_tool_id += 1
            device_serial = (device.serial or '').strip().upper()
            device_found = False
            
            # First try serial matching.
            if device_serial and device_serial in akips_serials:
                device_found = True
                devices_found_in_api += 1
                self.logger.debug(f"TOOL ID CLEANUP: Device '{device.name}' (Serial: {device.serial}) found in AKIPS by serial - keeping ID {current_akips_id}")
            else:
                # Fallback to name matching when either side is missing serial context.
                # If the matching AKIPS hostname has member serials, a serialized Nautobot
                # device must match one of those member serials. If AKIPS has no member
                # serials for that hostname, the API side is serial-less and name can match.
                parsed_name = self.clean_device_name_from_archived(device.name).upper()
                
                for record in akips_name_records:
                    akips_hostname = record["name"]
                    # Use endswith for more accurate partial matching
                    if not parsed_name.endswith(akips_hostname):
                        continue

                    if record["serials"] and device_serial and device_serial not in record["serials"]:
                        continue

                    device_found = True
                    devices_found_in_api += 1
                    self.logger.debug(f"TOOL ID CLEANUP: Device '{device.name}' found in AKIPS by name match (endswith) '{akips_hostname}' - keeping ID {current_akips_id}")
                    break
            
            if not device_found:
                devices_to_clear += 1
                self.logger.debug(f"TOOL ID CLEANUP: Device '{device.name}' (ID: {device.id}, Serial: {device.serial}) not found in AKIPS - scheduling AKIPS ID '{current_akips_id}' for removal")
                changes.append(DeviceChange(provider, device.serial, "API ID", current_akips_id, None, device.name, device.id))
        
        self.logger.info(f"TOOL ID CLEANUP SUMMARY: {provider.upper()} - Devices with {provider.upper()} ID: {devices_with_tool_id}, Found in API: {devices_found_in_api}, Scheduled for ID removal: {devices_to_clear}")
        return changes

    def apply_change(self, change):
        """Apply a tool ID removal change to a device in Nautobot."""
        try:
            if change.device_id:
                device = Device.objects.get(id=change.device_id)
            else:
                device = Device.objects.get(serial=change.serial)
                
            if change.field_changed == "API ID":
                # Remove the tool ID - use empty string instead of None
                device.cf[change.provider + "_id"] = ""
                device.validated_save()
                self.logger.debug(f"TOOL ID REMOVAL: Removed {change.provider.upper()} ID '{change.current_value}' from device '{device.name}' (ID: {device.id})")
                return f"Change applied - {change.provider.upper()} ID removed"
                
        except Device.DoesNotExist:
            self.logger.error(f"TOOL ID REMOVAL: Device not found - Serial: {change.serial}, Device ID: {change.device_id}")
            return f"Failed: Device not found"
        except Exception as e:
            self.logger.error(f"TOOL ID REMOVAL: Error applying change to device '{change.device_name}': {e}")
            return f"Failed: {e}"
