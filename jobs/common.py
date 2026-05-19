
from nautobot.extras.models import  SecretsGroup, Secret
from nautobot.extras.choices import  SecretsGroupAccessTypeChoices, SecretsGroupSecretTypeChoices
import json
import requests
import pandas as pd
from django.db.models import Q, Count
from django.db.models import Func, F
from nautobot.dcim.models import Device, Interface

def get_p42_token():

        # Get Apigee API token
        apigee_url = Secret.objects.get(name="Apigee URL").get_value()

        secrets_group = SecretsGroup.objects.get(name__exact="P42_API_Token_Creds")
        key = secrets_group.get_secret_value(
            access_type=SecretsGroupAccessTypeChoices.TYPE_GENERIC,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_KEY,
        )

        secret = secrets_group.get_secret_value(
            access_type=SecretsGroupAccessTypeChoices.TYPE_GENERIC,
            secret_type=SecretsGroupSecretTypeChoices.TYPE_SECRET,
        )

        payload = {
            "client_id": key,
            "client_secret": secret,
            "grant_type": "client_credentials"
        }

        payload = json.dumps(payload)
        headers = {"Content-Type": "application/json"}
        response = requests.request("POST", apigee_url, data = payload, headers = headers)
        response = json.loads(response.text)


        return response['token']


# def create_panda_and_csv(self, changes):
#     df = pd.DataFrame([vars(change) for change in changes])
#     return df.to_csv()

def create_panda_and_csv(array):
    # Create a DataFrame and explicitly ensure 'change_value' is formatted as a string with a prefix
    df = pd.DataFrame([vars(item) for item in array])

    # Convert to CSV without automatic formatting adjustments
    return df.to_csv(index=False, quoting=1)  # quoting=1 applies minimal quoting, preserving original values

def get_devices_from_tool(token, tool, period):

    # call end
    url = Secret.objects.get(name="Project42 URL").get_value() + "/apigw/netmonitor/nautobotToolSync?tool=" + tool + "&previousPeriod=" + str(period)

    headers = {
        'Authorization': 'Bearer ' + token,
        'Content-Type': 'application/json',
            "accept": "application/json",
    }

    response = requests.request("GET", url, headers=headers,verify=False)

    response = json.loads(response.text)
    return response

def _normalize_mac_address(mac):
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

def get_device(model_name, serial_number, provider=None, mac_address=None):
        found_devices = []
        if serial_number != None and serial_number != "":
            # Clean the input serial number by removing trailing newline or whitespace characters
            serial_number = serial_number.strip()

            # Annotate the Device objects to trim any trailing newlines or whitespace in the serial field
            found_devices = Device.objects.annotate(
                cleaned_serial=Trim(F('serial'))
            ).filter(cleaned_serial__iexact=serial_number)
        
        # Try MAC address matching if no serial match and MAC is provided (for LogicMonitor serial-less devices)
        if (not found_devices or len(found_devices) == 0) and mac_address and mac_address.strip():
            normalized_mac = _normalize_mac_address(mac_address)
            if normalized_mac:
                # Search by MAC address on interfaces
                matching_interface = Interface.objects.filter(mac_address__iexact=normalized_mac).first()
                if matching_interface and matching_interface.device:
                    found_devices = [matching_interface.device]

        # remove archived devices
        # found_devices = found_devices.exclude(status=Status.objects.get_for_model(Device).get(name="Archived"))
        # self.logger.info(f"Getting device {model_name}, {serial_number}, Found Devices: {len(found_devices)}")
        # Only match by name if:
        # 1. No devices found by serial number or MAC AND
        # 2. Model name exists AND
        # 3. EITHER the API serial number is empty/None OR the Nautobot device has empty/None serial
        if  (not found_devices or len(found_devices) == 0) and model_name != None and model_name != "":
            # Only proceed with name matching if:
            # - API serial and MAC are both empty/None (pure name-based match), OR
            # - API serial is empty/None, MAC was provided but did not match, and there is exactly one
            #   device with this name whose serial is empty/None (safe, unambiguous fallback).
            if (serial_number == None or serial_number == "") and (mac_address == None or mac_address == ""):
                # No serial and no MAC provided from API: use straightforward name-based lookup.
                found_devices = Device.objects.filter(name=model_name)
            elif serial_number == None or serial_number == "":
                # Has MAC from API but no serial.
                # MAC lookup above did not find a match. As a safe fallback, only match by name if there is
                # exactly one device with this name and its serial is empty/None. This avoids ambiguous merges
                # while preventing duplicate creation when there is an obvious candidate.
                potential_devices = Device.objects.filter(name=model_name)
                devices_with_empty_serial = [
                    device for device in potential_devices
                    if not device.serial or device.serial.strip() == ""
                ]
                if len(devices_with_empty_serial) == 1:
                    found_devices = [devices_with_empty_serial[0]]
            else:
                # API has serial, but no match found - check if any devices with this name have empty serials
                potential_devices = Device.objects.filter(name=model_name)
                found_devices = [device for device in potential_devices if not device.serial or device.serial.strip() == ""]
            # self.logger.info(f"Getting device by name {model_name}, {serial_number}, Found Devices: {len(found_devices)}")


        if found_devices and len(found_devices) == 1:
            return found_devices[0]
        else:
            return None

def get_netim_id(self, ip, apigee_token):
    """Performs an API call to P42 to get the netim_id. Finds matching ID by IP Address used for creation.

    Args:
        ip (str): IP Address of device
        apigee_token (str): bearer apigee token for running P42 API's

    Returns:
        netim_id (str): returns netim_id
    """
    url = Secret.objects.get(name="Project42 URL").get_value() + "/apigw/netmonitor/netImRetreiver"
    querystring = {"ip":ip}

    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {apigee_token}"
    }
    netim_id = ""
    self.logger.info("Waiting for NetIM ID (30 secs)")
    time.sleep(30)
    response = requests.request("GET", url, headers=headers, params=querystring, verify="/opt/nautobot/aaRootIntermediate.pem")
    results = json.loads(response.text)
    i = 1

    # While loop that will multiple times to to reattempt pulling netIM ID until it succeeds.
    while i <= 3 and results == "nullId":
        self.logger.warning(f"Waiting on NetIM ID, waiting 10 seconds to try again (reattempt {i} of 3)")
        time.sleep(10)
        response = requests.request("GET", url, headers=headers, params=querystring, verify="/opt/nautobot/aaRootIntermediate.pem")
        results = json.loads(response.text)
        i += 1

    #If the API has an error or if the response returns empty after timer ends
    if not str(response.status_code).startswith("2"):
        self.logger.warning(f'An API Error occurred while trying to get the new NetIM ID.')
        self.logger.debug(f"Response Code: {response.status_code} / Response Text: {response.text}")

    elif results == "nullId":
        self.logger.warning(f'Unable to get new NetIM ID due to time-out.')

    #If the API response is successful and has the needed data
    else:
        netim_id = results
        self.logger.info(f"NetIM ID Successfully retrieved [NetIM ID: {netim_id}]")

    return netim_id

def _tool_id_search(self, tool, deviceIP, apigee_token):
    tool_id = ""
    url = Secret.objects.get(name="Project42 URL").get_value() + "/apigw/netmonitor/toolIdSearch"
    params = {"tool": tool, "ip": deviceIP}
    headers = {
        "accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {apigee_token}",
    }

    response = requests.request(
        "GET",
        url,
        headers=headers,
        params=params,
        verify="/opt/nautobot/aaRootIntermediate.pem",
    )

    #Uncomment for debugging
    # self.logger.debug(f"API Status Code: {response.status_code} / API Response: {response.text}")

    # Returns None if API fails
    if not str(response.status_code).startswith("2"):
        self.logger.error(f'Encountered an API error trying to get {tool} ID')          

    #Updates tool_id before return if there was a match, does NOT equal nullId
    else:

        results = response.json()

        if 'id' in results:
            # if results['serial'] == serial:
            tool_id = str(results['id'])
            # else:
            #     self.logger.error(f"ID for '{deviceIP}' found in '{tool}' but its S/N does not match device in Nautobot. ID will not be used for Archiving.") 
    
    return tool_id

class Trim(Func):
    function = 'BTRIM'
    template = "%(function)s(%(expressions)s, '\n')"