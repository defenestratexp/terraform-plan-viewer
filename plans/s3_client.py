"""S3 client for reading Terraform plans."""
import json
from datetime import datetime, timezone
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from django.conf import settings


class S3Client:
    """Client for interacting with S3 bucket containing Terraform plans."""

    def __init__(self):
        self.s3 = boto3.client("s3", region_name=settings.S3_REGION)
        self.bucket = settings.S3_BUCKET

    def list_environments(self) -> list[str]:
        """List all environments that have plans."""
        try:
            response = self.s3.list_objects_v2(
                Bucket=self.bucket,
                Delimiter="/",
            )
            environments = []
            for prefix in response.get("CommonPrefixes", []):
                env = prefix["Prefix"].rstrip("/")
                if env != "latest":
                    environments.append(env)
            return sorted(environments)
        except ClientError:
            return []

    def list_plans(self, environment: str) -> list[dict]:
        """List all plans for an environment."""
        try:
            response = self.s3.list_objects_v2(
                Bucket=self.bucket,
                Prefix=f"{environment}/",
                Delimiter="/",
            )
            plans = []
            for prefix in response.get("CommonPrefixes", []):
                plan_path = prefix["Prefix"].rstrip("/")
                timestamp = plan_path.split("/")[-1]
                if timestamp == "latest":
                    continue

                metadata = self._get_metadata(plan_path)
                status = self._get_status(plan_path)

                plans.append({
                    "plan_id": plan_path,
                    "timestamp": timestamp,
                    "environment": environment,
                    "metadata": metadata,
                    "status": status,
                    "staleness": self._calculate_staleness(metadata),
                })

            return sorted(plans, key=lambda x: x["timestamp"], reverse=True)
        except ClientError:
            return []

    def get_plan(self, plan_id: str) -> Optional[dict]:
        """Get details for a specific plan."""
        try:
            metadata = self._get_metadata(plan_id)
            status = self._get_status(plan_id)
            plan_text = self._get_plan_text(plan_id)

            parts = plan_id.split("/")
            environment = parts[0]
            timestamp = parts[1] if len(parts) > 1 else ""

            return {
                "plan_id": plan_id,
                "timestamp": timestamp,
                "environment": environment,
                "metadata": metadata,
                "status": status,
                "plan_text": plan_text,
                "staleness": self._calculate_staleness(metadata),
            }
        except ClientError:
            return None

    def get_latest_plan(self, environment: str) -> Optional[dict]:
        """Get the latest plan for an environment."""
        plans = self.list_plans(environment)
        if plans:
            return self.get_plan(plans[0]["plan_id"])
        return None

    def _get_metadata(self, plan_id: str) -> dict:
        """Get metadata.json for a plan."""
        try:
            response = self.s3.get_object(
                Bucket=self.bucket,
                Key=f"{plan_id}/metadata.json",
            )
            return json.loads(response["Body"].read().decode("utf-8"))
        except ClientError:
            return {}

    def _get_status(self, plan_id: str) -> dict:
        """Get status.json for a plan."""
        try:
            response = self.s3.get_object(
                Bucket=self.bucket,
                Key=f"{plan_id}/status.json",
            )
            return json.loads(response["Body"].read().decode("utf-8"))
        except ClientError:
            return {"status": "unknown"}

    def _get_plan_text(self, plan_id: str) -> str:
        """Get plan.txt content."""
        try:
            response = self.s3.get_object(
                Bucket=self.bucket,
                Key=f"{plan_id}/plan.txt",
            )
            return response["Body"].read().decode("utf-8")
        except ClientError:
            return "Plan text not available"

    def update_status(self, plan_id: str, new_status: str) -> bool:
        """Update the status of a plan."""
        try:
            current_status = self._get_status(plan_id)
            created_at = current_status.get("created_at", datetime.now(timezone.utc).isoformat())

            status_data = {
                "status": new_status,
                "created_at": created_at,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            self.s3.put_object(
                Bucket=self.bucket,
                Key=f"{plan_id}/status.json",
                Body=json.dumps(status_data, indent=2),
                ContentType="application/json",
            )
            return True
        except ClientError:
            return False

    def _calculate_staleness(self, metadata: dict) -> dict:
        """Calculate staleness level based on plan timestamp."""
        timestamp_str = metadata.get("timestamp", "")
        if not timestamp_str:
            return {"level": "unknown", "age_seconds": 0, "message": "Unknown age"}

        try:
            plan_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            age_seconds = (now - plan_time).total_seconds()

            if age_seconds > settings.STALENESS_CRITICAL:
                hours = int(age_seconds / 3600)
                return {
                    "level": "critical",
                    "age_seconds": age_seconds,
                    "message": f"Plan is {hours} hours old - infrastructure may have changed",
                }
            elif age_seconds > settings.STALENESS_WARNING:
                minutes = int(age_seconds / 60)
                return {
                    "level": "warning",
                    "age_seconds": age_seconds,
                    "message": f"Plan is {minutes} minutes old - consider re-planning",
                }
            else:
                minutes = int(age_seconds / 60)
                return {
                    "level": "ok",
                    "age_seconds": age_seconds,
                    "message": f"Plan is {minutes} minutes old",
                }
        except (ValueError, TypeError):
            return {"level": "unknown", "age_seconds": 0, "message": "Unknown age"}
