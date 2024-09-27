"""Module for syncing git to Nautobot."""
import os
from time import sleep
from pynautobot import api

nb = api(url=os.environ["PROD_NAUTOBOT_URL"], token=os.environ["PROD_NAUTOBOT_TOKEN"], verify=False)

sync_repo_job = nb.extras.jobs.get(name="Git Repository: Sync")
jobs_repo = nb.extras.git_repositories.get(name="Jobs Repo")

job_run = nb.extras.jobs.run(job_id=sync_repo_job.id, data={"repository": jobs_repo.id})
result = nb.extras.job_results.get(job_run.job_result.id)

job_statuses = ["PENDING", "FAILED", "COMPLETED", "CANCELLED", "CREATED", "SUCCESS"]

while result.status.value not in job_statuses:
    result = nb.extras.job_results.get(job_run.job_result.id)
    print("Git Sync is running...")
    sleep(1)


print(f"Git Sync Job completed with status `{result.status.value}`")
