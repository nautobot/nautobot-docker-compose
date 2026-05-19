from nautobot.apps.jobs import Job, ObjectVar, register_jobs
from nautobot.dcim.models import Device, Location

name = "Test"

class ChooseDevice(Job):
    class Meta:
        name = "Choose a Device"
        description = "This is a simple job to demonstrate how to use ObjectVar to select a device."

    location = ObjectVar(
        model=Location,
        description="Pick a location to validate."
    )

    device = ObjectVar(
        model=Device,
        description="Pick a device to validate.",
        query_params={
            "location": "$location",
        },
    )

    def run(self, *, location, device):
        self.logger.info("You selected the location: %s", location)
        self.logger.info("You selected the device: %s", device)

register_jobs(ChooseDevice)