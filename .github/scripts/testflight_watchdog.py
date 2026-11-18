"""Keep the existing TestFlight build workflow enabled and its uploads current."""

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone


def api(method, path, **fields):
    command = ["gh", "api", "--method", method, path]
    for key, value in fields.items():
        command.extend(["-f", f"{key}={value}"])
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(result.stdout) if result.stdout.strip() else None


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def assess(runs, jobs_for, now, upstream_ahead):
    """Count a successful upload step, never a green run that skipped building."""
    active = [run for run in runs if run["status"] != "completed"]
    if active:
        run = active[0]
        if now - timestamp(run["created_at"]) > timedelta(hours=6):
            raise RuntimeError(f"Build has been pending over six hours: {run['html_url']}")
        return False, f"Build already running: {run['html_url']}"

    uploaded_at = None
    last_attempt = None
    for run in runs:
        if run["event"] == "workflow_dispatch" or run["conclusion"] == "failure":
            last_attempt = last_attempt or run
        if run["conclusion"] in {"skipped", "cancelled"}:
            continue
        for job in jobs_for(run["id"]):
            for step in job.get("steps", []):
                if step["name"] == "Fastlane upload to TestFlight" and step["conclusion"] == "success":
                    finished = timestamp(step["completed_at"])
                    uploaded_at = max(uploaded_at, finished) if uploaded_at else finished
        if uploaded_at:
            break

    stale = uploaded_at is None or now - uploaded_at >= timedelta(days=28)
    failed = last_attempt and last_attempt["conclusion"] == "failure" and (
        uploaded_at is None or timestamp(last_attempt["created_at"]) > uploaded_at
    )
    if not stale and not upstream_ahead and not failed:
        return False, f"Latest upload: {uploaded_at.isoformat()}; no upstream updates."

    if last_attempt and now - timestamp(last_attempt["created_at"]) < timedelta(hours=24):
        if failed:
            raise RuntimeError(f"Build failed; retry after 24-hour cooldown: {last_attempt['html_url']}")
        return False, "A build was requested in the last 24 hours; avoiding duplicate requests."

    reasons = []
    if upstream_ahead:
        reasons.append(f"{upstream_ahead} upstream commits available")
    if stale:
        reasons.append("no successful TestFlight upload within 28 days")
    if failed:
        reasons.append("retrying a failed build")
    return True, "; ".join(reasons)


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    branch = os.environ["BUILD_BRANCH"]
    workflow = os.environ["BUILD_WORKFLOW"]
    upstream = os.environ["UPSTREAM_REPO"]
    now = datetime.now(timezone.utc)

    # Refresh enablement even when active to prevent inactivity suspension.
    for filename in ("testflight_watchdog.yml", workflow):
        api("PUT", f"repos/{repo}/actions/workflows/{filename}/enable")

    runs = api("GET", f"repos/{repo}/actions/workflows/{workflow}/runs?branch={branch}&per_page=100")["workflow_runs"]
    upstream_owner = upstream.split("/")[0]
    comparison = api("GET", f"repos/{repo}/compare/{branch}...{upstream_owner}:{branch}")

    def jobs_for(run_id):
        return api("GET", f"repos/{repo}/actions/runs/{run_id}/jobs?per_page=100")["jobs"]

    dispatch, message = assess(runs, jobs_for, now, comparison["ahead_by"])
    print(message)
    if dispatch:
        api("POST", f"repos/{repo}/actions/workflows/{workflow}/dispatches", ref=branch)
        message += f"\n\nRequested {workflow} on {branch}. The build workflow performs signing and upload."
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as output:
            output.write(message + "\n")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"::error::{error}")
        raise SystemExit(1) from error
