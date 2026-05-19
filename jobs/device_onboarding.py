"""Jobs Module."""

from ipaddress import IPv4Address

from celery.utils.serialization import UnpickleableExceptionWrapper
from django.db import models
from nautobot.dcim.models.locations import Location
from nautobot.dcim.models import Device, DeviceType, Manufacturer, Interface
from nautobot.extras.jobs import ChoiceVar, IPAddressVar, Job, ObjectVar, StringVar, BooleanVar
from nautobot.extras.models import Role, Status, Secret, SecretsGroup

from .apihandler import ApiHandler, ApiHandlerError
from .credentials import P42ApigeeCredentials
from .common import get_p42_token
import json
import requests

name = "Device Onboarding"  # pylint: disable=invalid-name


class AuthSettings(models.IntegerChoices):
    """Auth Settings Integet Choices Class."""

    AA_V2C = 1, "AA-v2c (Cisco IOS and Aruba)"
    AA_MERAKI = 2, "AA-Meraki"
    AA_FIREWALL = 3, "AA-Firewall"
    DXC = 4, "DXC-DC Switch"
    SITA_VIPTELLA = 5, "SITA-Viptella"
    SITA_MPLS = 6, "SITA-MPLS"
    ATT_NONVELO = 7, "ATT-NonVelo"
    ATT_VELO = 8, "ATT-Velo"
    UPS = 9, "UPS"


class DeviceOnboarding(Job):
    """Device Onboarding."""
    
    hostname = StringVar(label="Hostname", description="Device Host Name")
    ipaddress = IPAddressVar(label="IP Address", description="Device IP Address")
    location = ObjectVar(
        description="Location for Tools Container.",
        label="Location",
        model=Location,
        required=True,
        query_params={
            "location_type": "Site",
        },
    )
    authentication = ChoiceVar(
        choices=AuthSettings.choices, label="SNMP Authentication", description="Authentication Method"
    )

    debug = BooleanVar(
        label="Job Debug Mode",
        description="Select to run job with additional logging"
    )


    class Meta:  # pylint: disable=too-few-public-methods
        """Meta."""
        name = "Device Onboarding"
        verbose_name = "Device Onboarding Job"
        description = "Device Onboarding Job via Project42 API"

    def run(
        self,
        ipaddress: IPv4Address,
        hostname: str,
        authentication: int,
        location: Location,
        debug: bool,
    ) -> None:  # pylint:disable=arguments-differ
        """Run Method."""

        #Sets debug
        self.debug = debug

        #Auth Group dictionary
        authGroups = {
            "AA-v2c (Cisco IOS and Aruba)": 1, 
            "AA-Meraki": 2,             
            "AA-Firewall": 3,    
            "DXC-DC Switch": 4,
            "SITA-Viptela": 5,
            "SITA-MPLS": 6,
            "ATT-NonVelo": 7,
            "ATT-Velo": 8,
            "UPS": 9,
        }

        snmp_name = ""
        for key, snmp_int in authGroups.items():
            if  int(snmp_int) == int(authentication):
                snmp_name = key
                break

        self.logger.info(f"Onboarding Device: \n{hostname}, \n{ipaddress}, \n{location.name}, \n{snmp_name}")

        results_payload = {
            "emailto": [str(self.user.email)],
            "emailcc": ["DL_Network_Tools@aa.com", "DL_Nautobot@aa.com"],
            "emailtitle": f"{hostname} Device Onboarding",
            "emailrequester": str(self.user),
            "emailmodule": f"""
                Nautobot Device Onboarding
            """, 
            "template": True,
            "supportEmail": "DL_Nautobot@aa.com",
        }

        #UNCOMMENT PROD VS NON-PROD as Needed.
        # base_url = "https://nautobot.aa.com"
        base_url = "https://nautobot-nonprod.aa.com"
        job_url = f"{base_url}{self.job_result.get_absolute_url()}"

        project42_url = Secret.objects.get(name="Project42 URL").get_value()
        try:
            device_add_payload = {
                "devices": [
                    {
                        "ipAddress": str(ipaddress),
                        "hostName": str(hostname.lower()),
                        "authInt": str(authentication),
                        "containerSpectrum": str(location.cf["spectrum_id"]),
                        "siteTag": str(location.name)
                    }
                ],
                "sendEmail": False
            }
            if self.debug:
                self.logger.debug("Device Onboarding Payload: %s", device_add_payload)
        except KeyError as exc:
            self.logger.error(f"Encountered an error trying to build API Payload, please verify error and try again.")
            self.logger.error(f"ERROR: {exc}")
            return

        # Try to perform function to get Apigee Token for P42 API
        try:
            apigee_token = get_p42_token()
        # Exception if API to get token fails
        except:
            self.logger.error("Nautobot was unable to get Apigee Token to run P42 APIs")
            return
        
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {apigee_token}"
        }

        p42_add = project42_url + "/apigw/netmonitor/addDevice"
        #Builds json from payload data
        data = json.dumps(device_add_payload)
        add_device_response = requests.request("POST",p42_add,headers=headers,data=data,verify="/opt/nautobot/aaRootIntermediate.pem")

        if self.debug:
            self.logger.debug(f"Device Add API Code: {add_device_response.status_code} / API Text: {add_device_response.text}")

        spectrum_result = ""
        netim_result = ""
        lm_result = ""
        dns_result = ""
        change_message = ""

        #If P42 API Add was successful (200 status) 
        if str(add_device_response.status_code).startswith("2"):

            results = add_device_response.json()

            # Spectrum Results
            if results["Spectrum"][0]["error"]:
                self.logger.error(
                    f"""Encountered an error while adding device to Spectrum.
                    Please verify cause of error and contact tools team to manually add this device to Spectrum."""
                )
                self.logger.error(f"P42 Spectrum Error Message: {results['Spectrum'][0]['errorMessage']}")
                spectrum_result = f"FAILED: {results['Spectrum'][0]['errorMessage']}"
            else:
                self.logger.info(f"Successfully added to Spectrum")
                spectrum_result = "SUCCESSFUL"

            # LogicMonitor Results
            if results["logicMonitor"][0]["error"]:
                self.logger.error(
                    f"""Encountered an error while adding device to Logic Monitor.
                    Please verify cause of error and contact tools team to manually add this device to Logic Monitor."""
                )
                self.logger.error(f"P42 Logic Monitor Error Message: {results['logicMonitor'][0]['errorMessage']}")
                lm_result = f"FAILED: {results['logicMonitor'][0]['errorMessage']}"
            else:
                self.logger.info(f"Successfully added to Logic Monitor")
                lm_result = "SUCCESSFUL"

            # NetIM Results
            if results["NetIM"][0]["error"]:
                self.logger.error(
                    f"""Encountered an error while adding device to NetIM.
                    Please verify cause of error and contact tools team to manually add this device to NetIM."""
                )
                self.logger.error(f"P42 NetIM Error Message: {results['NetIM'][0]['errorMessage']}")
                netim_result = f"FAILED: {results['NetIM'][0]['errorMessage']}"
            else:
                self.logger.info(f"Successfully added to NetIM")
                netim_result = "SUCCESSFUL"

            # DNS Results
            if results["DNS"][0]["error"]:
                self.logger.error(f"""Encountered an error while adding this device to DNS.
                Please verify cause of error and contact tools team to manually add this device to DNS.""")
                self.logger.error(f"P42 DNS ERROR: {results['DNS'][0]['errorMessage']}")
                dns_result = f"FAILED: {results['DNS'][0]['errorMessage']}"
            else:
                dns_result = "SUCCESSFUL"
                self.logger.info(f"Successfully added Infoblox ID (DNS Record) [A Record: {hostname.lower()}.aalcorp.aa.com / IP: {ipaddress}]")

            if "FAILED" in netim_result or "FAILED" in lm_result or "FAILED" in spectrum_result or "FAILED" in dns_result:
                change_message = """
                    Device has been added but failed on one or more tools.
                    Please see Job Results (link below) to verify cause of failure for the respective tool.
                """
                self.logger.error(change_message)
                results_payload["emailsubject"] = f"Nautobot Device Onboarding | PARTIAL SUCCESS | {hostname}"
                results_payload["emailmessage"] = f"<strong>PARTIAL SUCCESS</strong><br>{change_message}"
            else:
                change_message = "Device has been successfully added to all network tools."
                self.logger.info(change_message)
                results_payload["emailsubject"] = f"Nautobot Device Onboarding | SUCCESS | {hostname}"
                results_payload["emailmessage"] = f"<strong>SUCCESSFUL</strong><br>{change_message}"
            
            results_payload["changedetail"] = f"""
                Hostname = {hostname}<br>
                IP = {ipaddress}<br>
                Location = {location.name}<br>
                SNMP = {snmp_name}<br><br>
                Spectrum = {spectrum_result}<br>
                NetIM = {netim_result}<br>
                LogicMonitor = {lm_result}<br>
                DNS Entry = {dns_result}<br>
                <br>
                <a href="{job_url}">Nautobot Job Results</a>
            """
        #If P42 API Add was not successful (not 200 status)
        else:
            #Error log if error code was returned from P42 API Add
            self.logger.error(
                f"""Encountered an error while adding device to AA Network tools. 
                After verifying cause of error, please contact Nautobot, P42, and/or Network Tools teams for support."""
            )
            self.logger.error(f"Error Code: {add_device_response.status_code} | Error Text: {add_device_response.text}")    
            results_payload["emailsubject"] = f"Nautobot Device Onboarding | FAILED | {hostname}"
            results_payload["emailmessage"] = "<strong>FAILED</strong><br>Unable to add device to tools due to an error with P42 Device Add API."
            results_payload["changedetail"] = f"""
                Hostname = {hostname}<br>
                IP = {ipaddress}<br>
                Location = {location.name}<br>
                SNMP = {snmp_name}<br><br>
                API Error Code: {add_device_response.status_code}<br>
                API Error: {add_device_response.text}<br><br>
                Please use Job Results link below for further details.<br>
                <a href="{job_url}">Nautobot Job Results</a>
            """

        if self.debug:
            self.logger.debug(f"Email Payload: {results_payload}")
        # results_data = json.dumps(results_payload)

        try:
            email_response = requests.request(
                "POST",
                url = "http://edge-microgateway.project42-prod.svc.cluster.local:8000/apigw/utility/relayEmail",
                json = results_payload,
                headers = headers,
            )
            if self.debug:
                self.logger.debug(f"P42 E-Mail API Code: {email_response.status_code} / API Text: {email_response.text}")

            if str(email_response.status_code).startswith("2"):
                self.logger.info("Results successfully emailed")
            else:
                self.logger.error(f"P42 was unable to send results email due to an error.")
                self.logger.error(f"Error Code: {email_response.status_code} | Error Text: {email_response.text}")
        except Exception as e:
            self.logger.error(f"An error occured while generating results email. Email will not be sent. ERROR: {e}")



class UPSOnboarding(Job):
    """UPS Onboarding"""
    
    hostname = StringVar(label="UPS Hostname", description="UPS Host Name")
    ipaddress = IPAddressVar(label="IP Address", description="UPS MGMT IP Address")
    location = ObjectVar(
        description="Location for Tools Container.",
        label="Location",
        model=Location,
        required=True,
        query_params={
            "location_type": "Site",
        },
    )

    debug = BooleanVar(
        label="Job Debug Mode",
        description="Select to run job with additional logging"
    )


    class Meta:  # pylint: disable=too-few-public-methods
        """Meta."""
        name = "UPS Onboarding"
        verbose_name = "UPS Onboarding Job"
        description = "UPS Onboarding Job via Project42 API"

    def run(
        self,
        ipaddress: IPv4Address,
        hostname: str,
        location: Location,
        debug: bool,
    ) -> None:  # pylint:disable=arguments-differ
        """Run Method."""

        #Sets debug
        self.debug = debug

        snmp_name = "AA-UPS"

        self.logger.info(f"Onboarding UPS Device: \n{hostname}, \n{ipaddress}, \n{location.name}")

        results_payload = {
            "emailto": [str(self.user.email)],
            "emailcc": ["DL_Network_Tools@aa.com", "DL_Nautobot@aa.com"],
            "emailtitle": f"{hostname} Device Onboarding",
            "emailrequester": str(self.user),
            "emailmodule": f"""
                Nautobot Device Onboarding
            """, 
            "template": True,
            "supportEmail": "DL_Nautobot@aa.com",
        }

        #UNCOMMENT PROD VS NON-PROD as Needed.
        # base_url = "https://nautobot.aa.com"
        base_url = "https://nautobot-nonprod.aa.com"
        job_url = f"{base_url}{self.job_result.get_absolute_url()}"

        project42_url = Secret.objects.get(name="Project42 URL").get_value()
        try:
            device_add_payload = {
                "devices": [
                    {
                        "ipAddress": str(ipaddress),
                        "hostName": str(hostname.lower()),
                        "authInt": 9, #UPS Auth Int
                        "containerSpectrum": str(location.cf["spectrum_id"]),
                        "siteTag": str(location.name)
                    }
                ],
                "sendEmail": False
            }
            if self.debug:
                self.logger.debug("Device Onboarding Payload: %s", device_add_payload)
        except KeyError as exc:
            self.logger.error(f"Encountered an error trying to build API Payload, please verify error and try again.")
            self.logger.error(f"ERROR: {exc}")
            return

        # Try to perform function to get Apigee Token for P42 API
        try:
            apigee_token = get_p42_token()
        # Exception if API to get token fails
        except:
            self.logger.error("Nautobot was unable to get Apigee Token to run P42 APIs")
            return
        
        headers = {
            "accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {apigee_token}"
        }

        p42_add = project42_url + "/apigw/netmonitor/addDevice"
        #Builds json from payload data
        data = json.dumps(device_add_payload)
        add_device_response = requests.request("POST",p42_add,headers=headers,data=data,verify="/opt/nautobot/aaRootIntermediate.pem")

        if self.debug:
            self.logger.debug(f"Device Add API Code: {add_device_response.status_code} / API Text: {add_device_response.text}")

        spectrum_result = ""
        netim_result = ""
        lm_result = ""
        dns_result = ""
        change_message = ""

        #If P42 API Add was successful (200 status) 
        if str(add_device_response.status_code).startswith("2"):

            results = add_device_response.json()

            # Spectrum Results
            if results["Spectrum"][0]["error"]:
                self.logger.error(
                    f"""Encountered an error while adding device to Spectrum.
                    Please verify cause of error and contact tools team to manually add this device to Spectrum."""
                )
                self.logger.error(f"P42 Spectrum Error Message: {results['Spectrum'][0]['errorMessage']}")
                spectrum_result = f"FAILED: {results['Spectrum'][0]['errorMessage']}"
            else:
                self.logger.info(f"Successfully added to Spectrum")
                spectrum_result = "SUCCESSFUL"

            # DNS Results
            if results["DNS"][0]["error"]:
                self.logger.error(f"""Encountered an error while adding this device to DNS.
                Please verify cause of error and contact tools team to manually add this device to DNS.""")
                self.logger.error(f"P42 DNS ERROR: {results['DNS'][0]['errorMessage']}")
                dns_result = f"FAILED: {results['DNS'][0]['errorMessage']}"
            else:
                dns_result = "SUCCESSFUL"
                self.logger.info(f"Successfully added Infoblox ID (DNS Record) [A Record: {hostname.lower()}.aalcorp.aa.com / IP: {ipaddress}]")

            if "FAILED" in spectrum_result or "FAILED" in dns_result:
                change_message = """
                    Device has been added but failed on one or more tools.
                    Please see Job Results (link below) to verify cause of failure for the respective tool.
                """
                self.logger.error(change_message)
                results_payload["emailsubject"] = f"Nautobot Device Onboarding | PARTIAL SUCCESS | {hostname}"
                results_payload["emailmessage"] = f"<strong>PARTIAL SUCCESS</strong><br>{change_message}"
            else:
                change_message = "Device has been successfully added to all network tools."
                self.logger.info(change_message)
                results_payload["emailsubject"] = f"Nautobot Device Onboarding | SUCCESS | {hostname}"
                results_payload["emailmessage"] = f"<strong>SUCCESSFUL</strong><br>{change_message}"
            
            results_payload["changedetail"] = f"""
                Hostname = {hostname}<br>
                IP = {ipaddress}<br>
                Location = {location.name}<br>
                SNMP = {snmp_name}<br><br>
                Spectrum = {spectrum_result}<br>
                NetIM = N/A for UPS Device<br>
                LogicMonitor = N/A for UPS Device<br>
                DNS Entry = {dns_result}<br>
                <br>
                <a href="{job_url}">Nautobot Job Results</a>
            """
        #If P42 API Add was not successful (not 200 status)
        else:
            #Error log if error code was returned from P42 API Add
            self.logger.error(
                f"""Encountered an error while adding device to AA Network tools. 
                After verifying cause of error, please contact Nautobot, P42, and/or Network Tools teams for support."""
            )
            self.logger.error(f"Error Code: {add_device_response.status_code} | Error Text: {add_device_response.text}")    
            results_payload["emailsubject"] = f"Nautobot Device Onboarding | FAILED | {hostname}"
            results_payload["emailmessage"] = "<strong>FAILED</strong><br>Unable to add device to tools due to an error with P42 Device Add API."
            results_payload["changedetail"] = f"""
                Hostname = {hostname}<br>
                IP = {ipaddress}<br>
                Location = {location.name}<br>
                SNMP = {snmp_name}<br><br>
                API Error Code: {add_device_response.status_code}<br>
                API Error: {add_device_response.text}<br><br>
                Please use Job Results link below for further details.<br>
                <a href="{job_url}">Nautobot Job Results</a>
            """

        if self.debug:
            self.logger.debug(f"Email Payload: {results_payload}")
        # results_data = json.dumps(results_payload)

        try:
            email_response = requests.request(
                "POST",
                url = "http://edge-microgateway.project42-prod.svc.cluster.local:8000/apigw/utility/relayEmail",
                json = results_payload,
                headers = headers,
            )
            if self.debug:
                self.logger.debug(f"P42 E-Mail API Code: {email_response.status_code} / API Text: {email_response.text}")

            if str(email_response.status_code).startswith("2"):
                self.logger.info("Results successfully emailed")
            else:
                self.logger.error(f"P42 was unable to send results email due to an error.")
                self.logger.error(f"Error Code: {email_response.status_code} | Error Text: {email_response.text}")
        except Exception as e:
            self.logger.error(f"An error occured while generating results email. Email will not be sent. ERROR: {e}")

                