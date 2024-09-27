"""Module for running design jobs."""
import os
from time import sleep
from pynautobot import api

nb = api(url=os.environ["PROD_NAUTOBOT_URL"], token=os.environ["PROD_NAUTOBOT_TOKEN"], verify=False)

design_job = nb.extras.jobs.get(name="Initial Data")

job_run = nb.extras.jobs.run(job_id=design_job.id, data={"dryrun": False})
result = nb.extras.job_results.get(job_run.job_result.id)

job_statuses = ["PENDING", "FAILURE", "COMPLETED", "CANCELLED", "CREATED", "SUCCESS"]

while result.status.value not in job_statuses:
    result = nb.extras.job_results.get(job_run.job_result.id)
    print("Job is running...")
    sleep(1)

if result.status.value != "SUCCESS":
    msg = f"Design Job DRYRUN failed with traceback `{result.traceback}`"
    raise Exception(msg)

print(f"Job completed with status `{result.status.value}`")
