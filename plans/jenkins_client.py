"""Jenkins client for triggering Terraform apply jobs."""
import requests
from django.conf import settings


class JenkinsClient:
    """Client for interacting with Jenkins to trigger builds."""

    def __init__(self):
        self.base_url = settings.JENKINS_URL.rstrip("/")
        self.user = settings.JENKINS_USER
        self.token = settings.JENKINS_TOKEN
        self.job = settings.JENKINS_JOB

    def trigger_apply(self, environment: str, plan_id: str, trigger_ansible: bool = False) -> dict:
        """Trigger a Jenkins job to apply a saved Terraform plan.

        Args:
            environment: The target environment (e.g., 'dev', 'pxeserver')
            plan_id: The S3 path to the plan (e.g., 'dev/20241206-123456')
            trigger_ansible: Whether to trigger Ansible after apply

        Returns:
            dict with 'success' boolean and 'message' or 'error'
        """
        if not self.token:
            return {
                "success": False,
                "error": "Jenkins API token not configured",
            }

        url = f"{self.base_url}/job/{self.job}/buildWithParameters"

        params = {
            "ACTION": "apply-saved",
            "ENVIRONMENT": environment,
            "PLAN_ID": plan_id,
            "TRIGGER_ANSIBLE": "true" if trigger_ansible else "false",
        }

        try:
            response = requests.post(
                url,
                params=params,
                auth=(self.user, self.token),
                timeout=30,
            )

            if response.status_code in (200, 201):
                return {
                    "success": True,
                    "message": f"Apply job triggered for {plan_id}",
                }
            elif response.status_code == 401:
                return {
                    "success": False,
                    "error": "Jenkins authentication failed",
                }
            elif response.status_code == 404:
                return {
                    "success": False,
                    "error": f"Jenkins job '{self.job}' not found",
                }
            else:
                return {
                    "success": False,
                    "error": f"Jenkins returned status {response.status_code}",
                }

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "error": "Jenkins request timed out",
            }
        except requests.exceptions.ConnectionError:
            return {
                "success": False,
                "error": f"Could not connect to Jenkins at {self.base_url}",
            }
        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "error": str(e),
            }

    def get_job_status(self) -> dict:
        """Get the status of the Jenkins job."""
        if not self.token:
            return {"available": False, "error": "Jenkins API token not configured"}

        url = f"{self.base_url}/job/{self.job}/api/json"

        try:
            response = requests.get(
                url,
                auth=(self.user, self.token),
                timeout=10,
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    "available": True,
                    "name": data.get("name"),
                    "url": data.get("url"),
                    "buildable": data.get("buildable", False),
                    "last_build": data.get("lastBuild", {}).get("number"),
                }
            else:
                return {"available": False, "error": f"Status {response.status_code}"}

        except requests.exceptions.RequestException as e:
            return {"available": False, "error": str(e)}
