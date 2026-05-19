"""Job to find duplicate devices by serial number or name."""

from nautobot.apps.jobs import Job
from nautobot.dcim.models import Device
from nautobot.extras.models import Status
from django.db.models import Count
import pandas as pd

name = "Data Population Jobs"


class FindDuplicateDevices(Job):
    """Find devices with duplicate serial numbers or duplicate names and output to CSV."""

    class Meta:
        name = "Find Duplicate Devices"
        description = "Finds devices with duplicate serial numbers or duplicate names and outputs results to CSV files."
        has_sensitive_variables = False

    def run(self):
        self.logger.info("Starting duplicate device scan...")

        # find only serial numbers
        duplicate_serials = (
            Device.objects.exclude(serial__isnull=True)
            .exclude(serial__exact="")
            .values("serial")
            .annotate(count=Count("id"))
            .filter(count__gt=1)
        )

        self.logger.info(f"Found {len(duplicate_serials)} serial numbers with duplicates")

        # list comprehension - turn serials into list
        duplicate_serial_values = [dup["serial"] for dup in duplicate_serials]
        duplicate_serial_devices = []
        
        # get all duplicate device data
        devices = (
            Device.objects.filter(serial__in=duplicate_serial_values)
            .select_related("status", "role", "location", "device_type", "device_type__manufacturer", "primary_ip4")
            .order_by("serial", "name")
        )
        
        
        # get only data we want
        for device in devices:
            duplicate_serial_devices.append({
                "duplicate_type": "Serial",
                "duplicate_value": device.serial,
                "device_name": device.name,
                "device_id": str(device.id),
                "serial": device.serial,
                "status": device.status.name if device.status else "N/A",
                "role": device.role.name if device.role else "N/A",
                "location": device.location.name if device.location else "N/A",
                "device_type": device.device_type.model if device.device_type else "N/A",
                "manufacturer": device.device_type.manufacturer.name if device.device_type and device.device_type.manufacturer else "N/A",
                "primary_ip": str(device.primary_ip4.address).split('/')[0] if device.primary_ip4 else "N/A",
                "netim_id": device.cf.get("netim_id", ""),
                "spectrum_id": device.cf.get("spectrum_id", ""),
                "akips_id": device.cf.get("akips_id", ""),
            })

        ## DO THE SAME FOR NAMES ##
        
        # Find duplicate names (excluding empty/null names)
        duplicate_names = (
            Device.objects.exclude(name__isnull=True)
            .exclude(name__exact="")
            .values("name")
            .annotate(count=Count("id"))
            .filter(count__gt=1)
        )

        self.logger.info(f"Found {len(duplicate_names)} device names with duplicates")

        # Collect all devices with duplicate names using a single optimized query
        duplicate_name_values = [dup["name"] for dup in duplicate_names]
        duplicate_name_devices = []
        
        # Single query with select_related to avoid N+1 queries
        devices = (
            Device.objects.filter(name__in=duplicate_name_values)
            .select_related("status", "role", "location", "device_type", "device_type__manufacturer", "primary_ip4")
            .order_by("name", "serial")
        )
        
        for device in devices:
            duplicate_name_devices.append({
                "duplicate_type": "Name",
                "duplicate_value": device.name,
                "device_name": device.name,
                "device_id": str(device.id),
                "serial": device.serial if device.serial else "N/A",
                "status": device.status.name if device.status else "N/A",
                "role": device.role.name if device.role else "N/A",
                "location": device.location.name if device.location else "N/A",
                "device_type": device.device_type.model if device.device_type else "N/A",
                "manufacturer": device.device_type.manufacturer.name if device.device_type and device.device_type.manufacturer else "N/A",
                "primary_ip": str(device.primary_ip4.address).split('/')[0] if device.primary_ip4 else "N/A",
                "netim_id": device.cf.get("netim_id", ""),
                "spectrum_id": device.cf.get("spectrum_id", ""),
                "akips_id": device.cf.get("akips_id", ""),
            })

        # Combine all duplicates for a single CSV
        all_duplicates = duplicate_serial_devices + duplicate_name_devices

        # Create CSV for duplicate serials
        if duplicate_serial_devices:
            df_serial = pd.DataFrame(duplicate_serial_devices)
            csv_serial = df_serial.to_csv(index=False)
            self.create_file("duplicate_serials.csv", csv_serial)
            self.logger.info(f"Created duplicate_serials.csv with {len(duplicate_serial_devices)} entries")
        else:
            self.logger.info("No duplicate serial numbers found")

        # Create CSV for duplicate names
        if duplicate_name_devices:
            df_name = pd.DataFrame(duplicate_name_devices)
            csv_name = df_name.to_csv(index=False)
            self.create_file("duplicate_names.csv", csv_name)
            self.logger.info(f"Created duplicate_names.csv with {len(duplicate_name_devices)} entries")
        else:
            self.logger.info("No duplicate device names found")

        # Create combined CSV
        if all_duplicates:
            df_all = pd.DataFrame(all_duplicates)
            csv_all = df_all.to_csv(index=False)
            self.create_file("all_duplicates.csv", csv_all)
            self.logger.info(f"Created all_duplicates.csv with {len(all_duplicates)} total entries")

        # Summary
        self.logger.info(f"Summary: {len(duplicate_serials)} duplicate serial groups, {len(duplicate_names)} duplicate name groups")
        self.logger.info(f"Total duplicate devices: {len(duplicate_serial_devices)} by serial, {len(duplicate_name_devices)} by name")
