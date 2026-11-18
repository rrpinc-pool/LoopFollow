import unittest
from datetime import datetime, timedelta, timezone

from testflight_watchdog import assess


NOW = datetime(2026, 11, 18, 12, tzinfo=timezone.utc)


def run(age, *, status="completed", conclusion="success", event="schedule", identity=1):
    return {
        "id": identity, "status": status, "conclusion": conclusion, "event": event,
        "created_at": (NOW - timedelta(days=age)).isoformat(),
        "html_url": f"https://github.com/example/app/actions/runs/{identity}",
    }


def upload(age, conclusion="success"):
    return [{"steps": [{"name": "Fastlane upload to TestFlight", "conclusion": conclusion,
                        "completed_at": (NOW - timedelta(days=age)).isoformat()}]}]


class WatchdogTests(unittest.TestCase):
    def test_fresh_upload_does_not_rebuild(self):
        self.assertFalse(assess([run(2)], lambda _: upload(2), NOW, 0)[0])

    def test_new_upstream_commits_request_build(self):
        self.assertTrue(assess([run(2)], lambda _: upload(2), NOW, 3)[0])

    def test_monthly_refresh_without_code_changes(self):
        self.assertTrue(assess([run(28)], lambda _: upload(28), NOW, 0)[0])

    def test_green_skipped_build_does_not_hide_old_upload(self):
        runs = [run(1, identity=2), run(35)]
        self.assertTrue(assess(runs, lambda rid: [] if rid == 2 else upload(35), NOW, 0)[0])

    def test_running_build_is_not_duplicated(self):
        self.assertFalse(assess([run(0.01, status="queued", conclusion=None)], lambda _: [], NOW, 10)[0])

    def test_stuck_build_fails_visibly(self):
        with self.assertRaisesRegex(RuntimeError, "six hours"):
            assess([run(1, status="queued", conclusion=None)], lambda _: [], NOW, 0)

    def test_failure_cooldown_then_retry(self):
        with self.assertRaisesRegex(RuntimeError, "cooldown"):
            assess([run(0.1, conclusion="failure")], lambda _: [], NOW, 0)
        self.assertTrue(assess([run(2, conclusion="failure")], lambda _: [], NOW, 0)[0])

    def test_recent_failed_attempt_retries_even_with_fresh_older_upload(self):
        runs = [run(2, conclusion="failure", identity=2), run(10)]
        self.assertTrue(assess(runs, lambda rid: [] if rid == 2 else upload(10), NOW, 0)[0])

    def test_artifact_failure_after_upload_counts_as_uploaded(self):
        self.assertFalse(assess([run(2, conclusion="failure")], lambda _: upload(1.99), NOW, 0)[0])

    def test_cancelled_no_build_run_does_not_block_refresh(self):
        runs = [run(0.1, conclusion="cancelled"), run(29, identity=2)]
        self.assertTrue(assess(runs, lambda _: upload(29), NOW, 0)[0])

    def test_no_history_triggers_first_build(self):
        self.assertTrue(assess([], lambda _: [], NOW, 0)[0])


if __name__ == "__main__":
    unittest.main()
