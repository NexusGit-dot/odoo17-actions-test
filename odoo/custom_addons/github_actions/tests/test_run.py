from datetime import datetime

from odoo.tests.common import TransactionCase


def make_run(**overrides):
    """Build a raw workflow run like the GitHub API returns it."""
    payload = {
        "id": 39664208720,
        "name": "Odoo CI",
        "workflow_id": 1234,
        "run_number": 42,
        "event": "push",
        "head_branch": "main",
        "head_sha": "87138db185f08165c098a5d1633169983f2d70f6",
        "status": "completed",
        "conclusion": "success",
        "run_started_at": "2026-10-21T19:44:11Z",
        "updated_at": "2026-10-21T19:46:39Z",
        "html_url": "https://github.com/NexusGit-dot/odoo17-actions-test/actions/runs/39664208720",
        "actor": {"login": "NexusGit-dot"},
        "repository": {
            "name": "odoo17-actions-test",
            "owner": {"login": "NexusGit-dot"},
        },
    }
    payload.update(overrides)
    return payload


class TestGithubActionsRun(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Run = self.env["github.actions.run"]
        self.Config = self.env["github.actions.config"]
        self.config = self.Config._get_config()

    def test_config_is_a_singleton(self):
        self.assertTrue(self.config)
        self.assertEqual(self.Config._get_config().id, self.config.id)

    def test_parse_datetime(self):
        """The ISO 8601 timestamps of the API are converted to UTC datetimes."""
        self.assertEqual(
            self.Run._parse_datetime("2026-10-21T19:44:11Z"),
            datetime(2026, 10, 21, 19, 44, 11),
        )
        self.assertEqual(
            self.Run._parse_datetime("2026-10-21T19:44:11.123456Z"),
            datetime(2026, 10, 21, 19, 44, 11),
        )
        self.assertFalse(self.Run._parse_datetime(None))
        self.assertFalse(self.Run._parse_datetime("not a date"))

    def test_values_from_api(self):
        """A raw payload is mapped to the fields of the record."""
        values = self.Run._values_from_api(make_run(), self.config)
        self.assertEqual(values["github_id"], "39664208720")
        self.assertEqual(values["workflow_name"], "Odoo CI")
        self.assertEqual(values["branch"], "main")
        self.assertEqual(values["commit"], "87138db185f0")
        self.assertEqual(values["status"], "completed")
        self.assertEqual(values["conclusion"], "success")
        self.assertEqual(values["actor"], "NexusGit-dot")
        self.assertEqual(values["repository"], "NexusGit-dot/odoo17-actions-test")
        self.assertEqual(values["started_at"], datetime(2026, 10, 21, 19, 44, 11))
        self.assertEqual(values["completed_at"], datetime(2026, 10, 21, 19, 46, 39))

    def test_values_from_api_with_unknown_values(self):
        """Unknown statuses are not stored as invalid selections."""
        values = self.Run._values_from_api(
            make_run(status="brand_new", conclusion="whatever"), self.config
        )
        self.assertEqual(values["status"], "unknown")
        self.assertFalse(values["conclusion"])

    def test_sync_creates_the_records(self):
        """The runs of the payload are stored in database."""
        payload = [
            make_run(id=1, run_number=1, status="completed", conclusion="success"),
            make_run(id=2, run_number=2, status="completed", conclusion="failure"),
            make_run(id=3, run_number=3, status="in_progress", conclusion=None),
        ]
        count = self.Run._sync_runs(payload, self.config)
        self.assertEqual(count, 3)
        self.assertEqual(self.Run.search_count([]), 3)

        success = self.Run.search([("github_id", "=", "1")])
        self.assertEqual(success.outcome, "success")
        self.assertEqual(success.duration, 148)

        failure = self.Run.search([("github_id", "=", "2")])
        self.assertEqual(failure.outcome, "failure")

        running = self.Run.search([("github_id", "=", "3")])
        self.assertEqual(running.outcome, "running")
        self.assertFalse(running.completed_at)

    def test_sync_is_idempotent(self):
        """Refreshing the same payload updates the records instead of duplicating them."""
        payload = [make_run(id=1, run_number=1)]
        self.Run._sync_runs(payload, self.config)
        self.Run._sync_runs(payload, self.config)
        self.assertEqual(self.Run.search_count([]), 1)
        self.assertEqual(self.Run.search([("github_id", "=", "1")]).run_number, 1)

    def test_sync_drops_the_oldest_runs(self):
        """Only the most recent runs are kept in database."""
        payload = [make_run(id=index, run_number=index) for index in range(1, 6)]
        self.config.write({"limit": 3})
        self.Run._sync_runs(payload, self.config)
        self.assertEqual(self.Run.search_count([]), 3)
        kept = self.Run.search([])
        self.assertEqual(max(kept.mapped("run_number")), 5)

    def test_action_open_run_returns_a_url(self):
        """The button of the list opens the run on GitHub."""
        self.Run._sync_runs([make_run()], self.config)
        run = self.Run.search([("github_id", "=", "39664208720")])
        action = run.action_open_run()
        self.assertEqual(action["type"], "ir.actions.act_url")
        self.assertEqual(action["url"], make_run()["html_url"])
