"""Views for Terraform plan viewer."""
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods

from .s3_client import S3Client
from .jenkins_client import JenkinsClient


def dashboard(request):
    """Display dashboard with all environments and their latest plans."""
    s3 = S3Client()
    environments = s3.list_environments()

    env_data = []
    for env in environments:
        latest = s3.get_latest_plan(env)
        plans = s3.list_plans(env)
        env_data.append({
            "name": env,
            "latest": latest,
            "plan_count": len(plans),
            "plans": plans[:5],  # Show last 5 plans
        })

    return render(request, "plans/dashboard.html", {
        "environments": env_data,
    })


def plan_detail(request, plan_id: str):
    """Display details for a specific plan."""
    s3 = S3Client()
    plan = s3.get_plan(plan_id)

    if not plan:
        return render(request, "plans/error.html", {
            "error": f"Plan not found: {plan_id}",
        }, status=404)

    jenkins = JenkinsClient()
    jenkins_status = jenkins.get_job_status()

    return render(request, "plans/detail.html", {
        "plan": plan,
        "jenkins_status": jenkins_status,
    })


@require_http_methods(["POST"])
def approve_plan(request, plan_id: str):
    """Approve and apply a plan."""
    s3 = S3Client()
    plan = s3.get_plan(plan_id)

    if not plan:
        return JsonResponse({"error": "Plan not found"}, status=404)

    current_status = plan.get("status", {}).get("status", "")
    if current_status not in ("pending", "failed"):
        return JsonResponse({
            "error": f"Plan cannot be approved (status: {current_status})"
        }, status=400)

    # Update status to approved
    s3.update_status(plan_id, "approved")

    # Trigger Jenkins
    trigger_ansible = request.POST.get("trigger_ansible") == "true"
    jenkins = JenkinsClient()
    result = jenkins.trigger_apply(
        environment=plan["environment"],
        plan_id=plan_id,
        trigger_ansible=trigger_ansible,
    )

    if result["success"]:
        return redirect("plan_detail", plan_id=plan_id)
    else:
        # Revert status on failure
        s3.update_status(plan_id, "pending")
        return render(request, "plans/error.html", {
            "error": f"Failed to trigger apply: {result['error']}",
        }, status=500)


def health_check(request):
    """Health check endpoint for K8s probes."""
    return HttpResponse("OK")
