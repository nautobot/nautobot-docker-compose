import re
import csv
from io import StringIO

from nautobot.extras.jobs import Job, BooleanVar
from nautobot.dcim.models import Device, Location
from nautobot.extras.models import Tag, SecretsGroup
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist



name = "Device classification"

class DeviceClassificationJob(Job):
    """
    A Nautobot Job to classify device names based on predefined patterns
    and generate a CSV report, specifically targeting a filtered set of Nautobot devices,
    using self.create_file() for output.
    """

    debug = BooleanVar(
        description="Enable for more verbose log messages", default=False
        )

    
    class Meta:
        name = "Device Classifier"
        description = "Classifies a specific subset of Nautobot device names and generates a CSV report using self.create_file()."

    def update_device_secretsGroup(self, device_name, group, debug):
        """
        Update the device secrets group based on the classification group.
        """

        if debug:
            self.logger.debug(f"Secrets group for '{device_name}'classification group '{group}'")


        secretsGroupDict = {"Managed By AA": "Nautobot AA ISE",
                            "Managed By AT&T": "ATT_RO_Tacacs",
                            "Managed By DXC": "DXC_credentials",
                            "Managed By SITA": "SITA_Credentials",
                            "Managed By Unknown": "No Secrets Assigned"}

        try:
            deviceObject = Device.objects.get(name=device_name)
            deviceSecretGroup = deviceObject.secrets_group
        except ObjectDoesNotExist:
            print("No device found with that name")
            return            
        except MultipleObjectsReturned:
            self.logger.warning(f"Multiple devices found with name '{device_name}'.")
            return            


        if debug:
                self.logger.debug(f"SecretsGroup for device '{device_name}:{deviceObject}': {deviceSecretGroup}") 

        for keys, val in secretsGroupDict.items():
            if keys == group:
                if deviceSecretGroup is None:
                    self.logger.warning(f"deviceSecretGroup is None for device '{device_name}'. Trying to assign a new one.")
                    newSecret = SecretsGroup.objects.get(name=val)
                    deviceObject.secrets_group = newSecret
                    deviceObject.save()
                    continue
                
                else:
                    try:
                        newSecret = SecretsGroup.objects.get(name=val)
                        deviceObject.secrets_group = newSecret
                        deviceObject.save()
                    except SecretsGroup.DoesNotExist:
                        self.logger.error(f"SecretsGroup with name '{val}' does not exist for device '{device_name}'")
                        break 
                    except Exception as e:
                        self.logger.error(f"Unexpected error assigning secrets group to device '{device_name}': {e}")
                        return  
                break
            
        

    def classify_single_device(self, debug, device_name):
        """
        Internal helper to classify a single device name.
        """      

        if debug:
                self.logger.debug(f"Now working on {device_name}")
        
        # --- Group 3 Regex (Most specific, catch-all for DXC patterns) ---
        group3_regex = re.compile(
            r"^(AA(?:CDC|PDC|SCC)\d*-"
            r"[\w-]+?-"
            r"(?:ASW|DSW|SW)\d+"
            r"(?: Stack \d+)?(?:-[\w-]+)?(?: - Archived)?$|" # Added (?: - Archived)?
            r"^AA(?:CDC|PDC)-DCW-DSW\d+)(?: - Archived)?$" # Added (?: - Archived)?
        )

        # --- Group 1 Regex (Most specific, catch-all for AT&T patterns) ---
        group1_regex = re.compile(
            # Branch 6: Numeric patterns (e.g., 89011003300023625785-1, 89011003300048929154 for SIM cards
            r"^\d+(?:-\d+)?(?: - Archived)?$|" # Matches digits, optional hyphen+digits, optional - Archived, then end of string

            # Branch 1: General AA-prefixed patterns
            r"^(AA(?:AC|AD|AE|AP|DC)?"
            r"(?:US|CAN|INT|EC|GB)?"
            r"[A-Z0-9]{2,6}\d{2,3}-"
            r"(?:R|V|CRW|CW|VM|SW|FW|RT|AP|FT|HT|B2C)\d+[A-Z]?"
            r"(?:-[\w-]+)*"
            r"(?:\.[\w\.-]+)?(?: Stack \d+)?(?: - Archived)?$"
            r"|"

            # Branch 2: Generalized AACC patterns
            r"^AACC(?:BR|DO|MX|TT|UK)[A-Z]{3}\d+-"
            r"(?:R|V|CRW|CW|VM|SW|FW|RT|AP|FT|HT|B2C)\d+[A-Z]?"
            r"(?:-[\w-]+)*"
            r"(?:\.[\w\.-]+)?(?: Stack \d+)?(?: - Archived)?$"
            r"|"

            # Branch 3: Generalized AARO patterns
            r"^AARO(?:AR|MX|PE)[A-Z]{3}\d+-"
            r"(?:R|V|CRW|CW|VM|SW|FW|RT|AP|FT|HT|B2C)\d+[A-Z]?"
            r"(?:-[\w-]+)*"
            r"(?:\.[\w\.-]+)?(?: Stack \d+)?(?: - Archived)?$"
            r"|"

            # Branch 4: Enhanced AADCGBLON / AACGGBLON patterns
            r"^AA(?:DC|CG)GBLON\d+-(?:SW|FW|RT|AP|R)\d{2}(?:-[\w-]+)*(?: - Archived)?$"
            r"|"

            # Branch 5: Existing AADCUS...SW patterns
            r"^AADCUS[A-Z]{2}\d{3}-SW\d{2}(?:-[\w-]+)*(?: Stack \d+)?(?: - Archived)?$)"
        )
        
        # --- Group 4 Regex (Newly added for SITA patterns) ---
        group4_regex = re.compile(
            r"^(?:" # Start of main non-capturing group for Group 4 alternatives
            # Pattern 1: P + 3-letter code + numbers (PACA038, PCPH123T)
            r"P[A-Z]{3}\d+[A-Z]?|"
            # Pattern 2: SITA + code + P + code + numbers (SITA-ACA-PACA044, SITA_LIM_PLIM997)
            r"SITA[-_][A-Z]{3}[-_]P[A-Z]{3}\d+"
            r")" # Close main non-capturing group
            r"(?: - Archived)?$" # Optional " - Archived" suffix for the entire group
        )    

        # --- Group 2 Regex for AA managed devices ---
        group2_regex = re.compile(
            r"^(?:" # Start of the main non-capturing group for all alternatives, with leading anchor
            
            # Branch 1: Any device name without a hyphen
            r"[^-]+|"

            # Branch 2: Specific AADD patterns without initial hyphens
            r"AADD(?:IDHCP|IFDNS|IGM|INI|IPDNS|IRE|ISDNS)(?:CDC|PDC|DFW|CDFW)\d*|"

            # Branch 3: AA prefixed names, NOT caught by Group 3 or Group 1
            r"AA(?:[A-Z]{1,10}|\d{1,10}){1,5}-(?:CSW|ASW|DSW|S|RSW|SSW|SW|TSW)\d*[A-Z]?(?:[- ]Stack \d+)?(?:-\d+)?|"

            # Branch 4: General location/switch/device pattern
            r"[\w]{2,5}(?:-[\w]+)*-(?:ASW|CSW|DSW|BSW|LSW|FW|RSW|SSW|SW|LAB)\d*[A-Z]?(?:[- ]Stack \d+)?(?:[\.-][\w\.-]+)?|"


            # Branch 5: Simpler word-hyphen-word-digits patterns
            r"(?:[A-Za-z0-9]+)-(?:switch|lab|router|firewall|ap|sw)\d+[A-Z]?"
            r")" # Closing the main non-capturing group
            r"(?: - Archived)?$" # Matching (?: - Archived)? before the final $
        ) 

        if group3_regex.fullmatch(device_name.strip()):
            if debug:
                self.logger.debug(f"Classified '{device_name}' as 'Managed By DXC'")
            return "Managed By DXC"
        elif group1_regex.fullmatch(device_name.strip()):
            if debug:
                self.logger.debug(f"Classified '{device_name}' as 'Managed By AT&T'")
            return "Managed By AT&T"
        elif group4_regex.fullmatch(device_name): # NEW: Check Group 4 here
            if debug:
                self.logger.debug(f"Classified '{device_name}' as 'Managed By SITA'")
            return "Managed By SITA"
        else:
            if group2_regex.fullmatch(device_name.strip()):
                if debug:
                    self.logger.debug(f"Classified '{device_name}' as 'Managed By AA'")
                return "Managed By AA"
            else:
                if debug:
                    self.logger.debug(f"Classified '{device_name}' as 'Managed By Unknown'")
            return "Managed By Unknown"
        
        
    def update_device_tags(self, device_name, group, debug):
        """
        Update the device tags based on the classification group.
        """

        try:
            deviceObject = Device.objects.get(name=device_name)
            deviceType = deviceObject.device_type.model
        except Device.DoesNotExist:
            self.logger.warning(f"No device found with name '{device_name}'")
            return
        except Device.MultipleObjectsReturned:
            self.logger.warning(f"Multiple devices found with name '{device_name}'")
            return       

        if group == "Managed By Unknown":
            self.logger.warning(f"Device '{device_name}' does not match any known classification patterns. Skipping.")
            newTag = Tag.objects.get(name="Managed By Unknown")
            deviceObject.tags.add(newTag)
            return

        if deviceObject.tags.all():
            for existingDeviceTag in deviceObject.tags.all():
                if debug:
                    self.logger.debug(f"Existing tag for {device_name}: {existingDeviceTag.name}")
                if existingDeviceTag.name == group:
                    if debug:
                        self.logger.debug(f"Device {device_name} already has tag: {group}")
                    if deviceType == "SIM Card": # Update the secrets group only if the device is not a SIM Card                            
                            continue
                    else:
                        self.update_device_secretsGroup(device_name, group, debug)
                    continue
                else:
                    deviceObject.tags.clear()
                    if debug:
                        self.logger.debug(f"Clearing tags for {device_name} and adding new tag: {group}")
                    newTag = Tag.objects.get(name=group)

                    if debug:
                        self.logger.debug(f"Adding tag '{newTag.name}' to device '{device_name}'")
                    deviceObject.tags.add(newTag)
                    if deviceType == "SIM Card": # Update the secrets group only if the device is not a SIM Card                            
                            continue
                    else:
                        self.update_device_secretsGroup(device_name, group, debug)

                    try:
                        deviceObject.validated_save()  # Save the device object after updating tags                       

                    except Exception as e:
                        self.logger.error(f"Failed to save device '{device_name}' after updating tags: {e}")
        else:                       
            deviceObject.tags.clear()
            if debug:
                self.logger.debug(f"Clearing tags for {device_name} and adding new tag: {group}")
            newTag = Tag.objects.get(name=group)

            if debug:
                self.logger.debug(f"Adding tag '{newTag.name}' to device '{device_name}'")
            deviceObject.tags.add(newTag)
            if deviceType == "SIM Card": # Update the secrets group only if the device is not a SIM Card                    
                    return
            else:
                # Update the secrets group based on the classification group
                self.update_device_secretsGroup(device_name, group, debug)
            try:
                deviceObject.validated_save()  # Save the device object after updating tags                

            except Exception as e:
                self.logger.error(f"Failed to save device '{device_name}' after updating tags: {e}")       


    def run(self, debug):
        """
        The main logic for the Nautobot Job.
        """
        self.logger.info("Starting device classification job for filtered Nautobot devices - changes detected.")

        self.debug = debug        

        allDevices = Device.objects.filter(status__name="Active").exclude(role__name="SIM Card").exclude(device_type__model__icontains="Meraki")        

        # Extract names from the queryset
        devices_to_process = [ device.name for device in allDevices ]

        if not devices_to_process:
            self.logger.warning("No devices found matching the filter criteria. Exiting.")
            return

        self.logger.info(f"Processing {len(devices_to_process)} device names from Nautobot's filtered devices.")        

        for device_name in devices_to_process:            
            if debug:
                self.logger.debug(f"Within the run for loop")            
            group = self.classify_single_device(debug, device_name)
            self.update_device_tags(device_name, group, debug)   # Update the secrets group will be called within the update_device_tags method

        self.logger.info("Job completed.")
        
