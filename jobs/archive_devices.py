from nautobot.apps.jobs import Job, IntegerVar, BooleanVar
from nautobot.dcim.models import (
    Device,
    VirtualChassis
)
from nautobot.extras.models import (
    Status,
    Secret,
)
import pandas as pd

name = "Data Population Jobs"


class ArchiveDevicesJob(Job):

    class Meta:
        name = "Archive Devices"      
        description = "Archive devices in Nautobot based on Spectrum, Netim, and Akips ID's."  
        time_limit = 3600
        soft_time_limit = 3600
        has_sensitive_variables = False
    
    max_archive = IntegerVar(
        label='Max Archive',
        default=10,
        description='Set to 0 to apply all changes.'
    )
    
    is_making_changes = BooleanVar(
        label='Make Changes',
        default=False,
        description='Set to True to apply changes.'
    )

    def run(self, max_archive, is_making_changes):


        # These are ignored devices roles that are not found in network tools.
        ignored_device_roles = [
            "SIM Card",
            "Wireless Router",
        ]
        
        counter = 0

        deviceList = Device.objects.exclude(role__name__in=ignored_device_roles)
        archive_status = Status.objects.get_for_model(Device).get(name="Archived")

        # results will go to df then csv
        devices_to_archive = []
        
        # Loops through each device in Device List from Nautobot.
        for device in deviceList:
            if device is None:
                continue
            # if all 3 of spectrum_id, netim_id, akips_id are None, archive device
            if self.check_ids_device(device, archive_status) and (counter < max_archive or max_archive == 0):
                # check if already archived
                if 'Archived' in device.name or device.status == archive_status:
                    continue
                devices_to_archive.append(ArchiveResult(device, True))
                
        
        if is_making_changes:
            for result in devices_to_archive:
                if result.need_archive:
                    self.logger.info(f"Archiving device: {result.device_name}")
                    result.change_implemented = self.archive_device(result.device, archive_status)
                    counter += 1
                    if counter >= max_archive and max_archive != 0:
                        break
        
        # remove 'device' from all DeviceChanges before going to CSV
        for result in devices_to_archive:
            del result.device
            del result.change_implemented
            
        change_csv = self.create_panda_and_csv(devices_to_archive)
        self.create_file("ArchiveResults.csv", change_csv)

    def create_panda_and_csv(self, results):

        df = pd.DataFrame([vars(r) for r in results])
        return df.to_csv()
    
    def check_ids_device(self, device, archive_status):
        """
        Check if all 3 of spectrum_id, netim_id, akips_id are None.
        """
        self.logger.info(f"Checking device: {device}", extra={"object": device})
        # if 'Stack' is in the name, do not archive
        if device.name and 'Stack' in str(device.name):
            return False
        # get custom fields
        spectrum_id, netim_id, akips_id = None, None, None
        
        if 'akips_id' in device.cf:
            akips_id = device.cf['akips_id']
        if 'spectrum_id' in device.cf:
            spectrum_id = device.cf['spectrum_id']
        if 'netim_id' in device.cf:
            netim_id = device.cf['netim_id']
            
        if spectrum_id is None and netim_id is None and akips_id is None:
            self.logger.info(f"Device has no tool ID's.", extra={"object": device})
            # self.archive_device(device, archive_status)
            return True
        else:
            return False
        
    def archive_device(self, device, archive_status, child=False):
        # it is a parent because it doesnt have Stack
        # get virtual chassis devices if they exist and archive them
        # if the name includes 'Archived' or status is 'Archived', do not archive
        if 'Archived' in device.name or device.status == archive_status:
            return False
        
        if not child:
            self.archive_virtual_chassis_members(device, archive_status)
        try:
            device.name = f"{device.name}-Archived"
            device.status = archive_status
            device.validated_save()
            return True
        except Exception as e:
            self.logger.error(f"Failed to archive device: {device.name}", extra={"object": device, "error": str(e)})
            return False
        
    def archive_virtual_chassis_members(self, parent_device, archive_status):
        # try to get VC
        try:
            vc = parent_device.virtual_chassis
            vc_members = vc.members.all()
            for member in vc_members:
                self.archive_device(member, archive_status, True)
        except VirtualChassis.DoesNotExist:
            pass
        except AttributeError:
            pass
        except Exception as e:
            self.logger.error(f"Failed to archive VC members for device: {parent_device.name}", extra={"object": parent_device, "error": str(e)})
            return False

class ArchiveResult:
    def __init__(self, device, need_archive):
        self.device = device
        self.device_name = device.name
        self.device_serial = device.serial
        self.need_archive = need_archive
        self.change_implemented = False
        

    def __str__(self):
        return self.message