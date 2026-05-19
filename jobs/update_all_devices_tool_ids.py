from nautobot.extras.jobs import Job, ChoiceVar, IntegerVar, BooleanVar
from .common import get_p42_token
from nautobot.extras.models import Secret, Status
import requests
from nautobot.dcim.models import Device, Interface
import json
from nautobot.ipam.models import IPAddress, IPAddressToInterface
from nautobot.dcim.choices import InterfaceTypeChoices
import pandas as pd
from django.db.models import Func, F
from django.db.models import Q

from django.db.models.functions import Trim

name = "Data Population Jobs"


class UpdateAllDeviceToolIDs(Job):
    
    period = IntegerVar(
        label='Period',
        default=0
    )
    
    max_changes = IntegerVar(
        label='Max Changes',
        default=0,
        description='Set to 0 to apply all changes.'
    )
    
    is_making_changes = BooleanVar(
        label='Make Changes',
        default=False,
        description='Set to True to apply changes.'
    )
    

    class Meta:
        name = "Update All Device Tool IDs"
        description = "Update all devices in Nautobot based on Spectrum, Netim, and Akips data."
    
    def preprocess_devices(self, devices, serial_key, hostname_key=None):
        """
        Preprocesses a list of devices into dictionaries for quick lookups by serial and hostname.
        """
        devices_by_serial = {}
        devices_by_hostname = {}



        for device in devices:
            # Retrieve and clean the serial number if it exists and is not None
            serial = device.get(serial_key)
            if serial is not None:
                serial = serial.strip()  # Clean trailing whitespace/newlines
                devices_by_serial[serial] = device
            else:
                serial = None
                
            # if serial is none, loop thru the "members" array if that exists and get its serial
            if serial is None:
                if device.get("members"):
                    for member in device["members"]:
                        serial = member.get(serial_key)
                        if serial is not None:
                            serial = serial.strip()
                            # append the parent akips_hostname and akips_ipaddress and akips_id
                            member["akips_hostname"] = device.get("akips_hostname")
                            member["akips_ipaddress"] = device.get("akips_ipaddress")
                            member["akips_id"] = device.get("akips_hostname")
                            devices_by_serial[serial] = member
                        else:
                            serial = None

            # Do similar processing for hostname if provided
            if hostname_key:
                hostname = device.get(hostname_key)
                if hostname is not None:
                    hostname = hostname.strip()  # Clean trailing whitespace/newlines
                    devices_by_hostname[hostname] = device
                else:
                    hostname = None

        return devices_by_serial, devices_by_hostname


    def run(self, period, max_changes, is_making_changes):
        token = get_p42_token()
        
        # Get device data from each tool
        devices_netim = self.get_devices(token, "netim", period)
        devices_spectrum = self.get_devices(token, "spectrum", period)
        devices_akips = self.get_devices(token, "akips", period)
        
        all_changes = []
        
        deleted_devices = self.get_deleted_devices(period)
        # add a device change to change based on tool, serial, hostname
        api_changes_from_delete_api = self.create_id_changes_from_delete_api(deleted_devices)
            
        devices_nautobot = Device.objects.all()
        self.logger.info(f"Found {len(devices_nautobot)} devices in Nautobot")

        # Preprocess devices for each tool
        spectrum_by_serial, spectrum_by_hostname = self.preprocess_devices(devices_spectrum, 'spectrum_serialnumber', 'spectrum_modelname')
        netim_by_serial, netim_by_hostname = self.preprocess_devices(devices_netim, 'netim_serialnumber', 'netim_modelname')
        akips_by_serial, akips_by_hostname = self.preprocess_devices(devices_akips, 'akips_serialnumber', 'akips_hostname')
        
        # print every single spectrum serial and hostname 
        for device_nautobot in devices_nautobot:
            self.logger.info(f"Checking device {device_nautobot.name}")
            
            if not device_nautobot.serial:
                self.logger.debug(f"Device {device_nautobot.name} has no serial number, skipping.")
                continue
            
            # Create changes for Spectrum, Netim, and Akips
            all_changes.append(self.create_tool_id_change(
                "Spectrum", "spectrum_id", "spectrum_modelhandle", device_nautobot,
                spectrum_by_serial, spectrum_by_hostname
            ))
            all_changes.append(self.create_tool_id_change(
                "Netim", "netim_id", "netim_netimid", device_nautobot,
                netim_by_serial, netim_by_hostname
            ))
            all_changes.append(self.create_tool_id_change(
                "Akips", "akips_id", "akips_hostname", device_nautobot,
                akips_by_serial, akips_by_hostname
            ))
        
        self.logger.info(f"Found {len(all_changes)} changes to apply.")
        # Filter out None changes
        all_changes = [change for change in all_changes if change]

        # for all changes, implement the change and update the status
        count = 0
        
        if is_making_changes:
            for change in all_changes:
                if max_changes != 0 and count >= max_changes:
                    self.logger.info(f"Max changes reached. Stopping at {max_changes} changes.")
                    break
                new_status = self.apply_change(change)
                change.change_status = new_status
                count += 1
            
        # Generate and save CSV
        change_csv = create_panda_and_csv(all_changes)
        self.create_file("ToolIDChanges.csv", change_csv)
        
        return "Success"
    
    def get_deleted_devices(self, period):
        # if period = 0, return none
        if period == 0:
            return []
        
        url = Secret.objects.get(name="Project42 URL").get_value() + f"/apigw/netmonitor/nautobotToolSync?tool=deletes&previousPeriod={period}"
        token = get_p42_token()
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            "accept": "application/json",
        }
        
        response = requests.get(url, headers=headers, verify="/opt/nautobot/aaRootIntermediate.pem")
        devices = json.loads(response.text)
        
        return devices
    
    def create_id_changes_from_delete_api(self, devices):
        # tool, serial, hostname
        # find device. if tool is akips, you can use serial or hostname to find device in nautobot
        device = None
        
        changes = []
        for device in devices:
            if device["tool"] == "akips":
                device = Device.objects.filter(Q(serial=device["serial"]) | Q(name=device["hostname"]))
            else:
                device = Device.objects.filter(serial=device["serial"])
            
            if device:
                change = DeviceChange(device["tool"], device["serial"], "API ID", device[device['tool'] + "_id"], None, device["name"])
                changes.append(change)
    
    def apply_change(self, change):
        # change in this will only be the tool id change
        # get the device from nautobot
        self.logger.info(f"Applying change for {change.provider} ID for {change.device_name}")
        try: 
            device = Device.objects.get(name=change.device_name)
            # update the field
            if change.change_value == "None":
                device.cf[change.field_changed] = None
            else:
                device.cf[change.field_changed] = change.change_value
            device.validated_save()
            return "Success"
        except Exception as e:
            return f"Failed: {e}"

    def get_devices(self, token, tool, period):
        self.logger.info(f"Getting devices from {tool} for the last {period} weeks")
        url = Secret.objects.get(name="Project42 URL").get_value() + f"/apigw/netmonitor/nautobotToolSync?tool={tool}&previousPeriod={period}"
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            "accept": "application/json",
        }
        
        response = requests.get(url, headers=headers, verify="/opt/nautobot/aaRootIntermediate.pem")
        devices = json.loads(response.text)
        
        self.logger.info(f"Found {len(devices)} devices from {tool}")
        return devices
    
    def create_tool_id_change(self, tool, field_changed, id_key, device_nautobot, devices_by_serial, devices_by_hostname):
        """
        Generic method to create a DeviceChange if there is a mismatch in tool ID.
        """
        # Retrieve tool ID based on serial or hostname
        device_id = self.get_tool_id(device_nautobot.serial, device_nautobot.name, devices_by_serial, devices_by_hostname, id_key)
        
        # Check for changes and create a DeviceChange if there is a difference
        self.logger.debug(f"{tool} ID for {device_nautobot.name}: {device_id}")
        if device_nautobot.cf.get(field_changed) != device_id:
            change = DeviceChange(tool, device_nautobot.serial, field_changed, device_nautobot.cf.get(field_changed), device_id, device_nautobot.name)
            self.logger.debug(f"DeviceChange created with change_value: {change.change_value}")
            return change
        
        # check if its none -> something
        if device_nautobot.cf.get(field_changed) == None and device_id != None:
            change = DeviceChange(tool, device_nautobot.serial, field_changed, device_nautobot.cf.get(field_changed), device_id, device_nautobot.name)
            self.logger.debug(f"DeviceChange created with change_value: {change.change_value}")
            return change
        
        # check if its something -> none 
        if device_nautobot.cf.get(field_changed) != None and device_id == None:
            change = DeviceChange(tool, device_nautobot.serial, field_changed, device_nautobot.cf.get(field_changed), device_id, device_nautobot.name)
            self.logger.debug(f"DeviceChange created with change_value: {change.change_value}")
            return change
        return None

    def get_tool_id(self, serial, hostname, devices_by_serial, devices_by_hostname, id_key):
        """
        Efficiently retrieves the tool ID by looking up in preprocessed dictionaries.
        """
        if not serial:  # Skip if serial is None or empty
            self.logger.debug("Serial number is empty or None, skipping lookup.")
            return None

        # Attempt to find a match by serial
        device = devices_by_serial.get(serial.strip())
        if device:
            self.logger.debug(f"Serial match found for {serial} with ID: {device.get(id_key)}")
            return device.get(id_key)

        # If no serial match, attempt to find by hostname
        # if hostname:
        #     device = devices_by_hostname.get(hostname.strip())
        #     if device:
        #         self.logger.debug(f"Hostname match found for {hostname} with ID: {device.get(id_key)}")
        #         return device.get(id_key)

        self.logger.debug(f"No match found for serial: {serial} or hostname: {hostname}")
        return None
    
class DeviceChange:
    def __init__(self, provider, serial, field_changed, current_value, change_value, device_name):
        self.provider = provider
        self.device_name = device_name
        self.serial = serial
        self.field_changed = field_changed
        self.current_value = current_value
        self.change_value = str(change_value)
        self.change_status = "Not Implemented"
        
    def __str__(self):
        return f"{self.provider} {self.device_name} {self.field_changed} {self.current_value} {self.change_value}"



def create_panda_and_csv(changes):
    # Create a DataFrame and explicitly ensure 'change_value' is formatted as a string with a prefix
    df = pd.DataFrame([vars(change) for change in changes])
    df['change_value'] = df['change_value'].apply(lambda x: f"'{x}" if isinstance(x, str) and x.startswith("0x") else str(x))

    # Convert to CSV without automatic formatting adjustments
    return df.to_csv(index=False, quoting=1)  # quoting=1 applies minimal quoting, preserving original values