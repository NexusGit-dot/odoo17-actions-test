import logging
from datetime import datetime

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Values returned by the "status" field of the GitHub API
STATUS_SELECTION = [
    ("queued", "Queued"),
    ("in_progress", "Running"),
    ("completed", "Completed"),
    ("waiting", "Waiting"),
    ("pending", "Pending"),
    ("requested", "Requested"),
    ("unknown", "Unknown"),
]

# Values returned by the "conclusion" field of the GitHub API
CONCLUSION_SELECTION = [
    ("success", "Success"),
    ("failure", "Failure"),
    ("cancelled", "Cancelled"),
    ("skipped", "Skipped"),
    ("timed_out", "Timed out"),
    ("action_required", "Action required"),
    ("neutral", "Neutral"),
    ("stale", "Stale"),
    ("startup_failure", "Startup failure"),
]

OUTCOME_SELECTION = [
    ("success", "Success"),
    ("failure", "Failure"),
    ("running", "Running"),
    ("pending", "Pending"),
]


class GithubActionsRun(models.Model):
    """One run of a GitHub Actions workflow."""

    _name = "github.actions.run"
    _description = "GitHub Actions workflow run"
    _order = "run_number desc, id desc"
    _rec_name = "workflow_name"

    # The identifiers of the GitHub API are 64 bits integers (a run number is
    # already above 2**31), while Odoo stores an "Integer" field on a 4 bytes
    # column: they are therefore kept as strings.
    github_id = fields.Char(string="Run ID", required=True, index=True)
    workflow_name = fields.Char(string="Workflow", required=True)
    workflow_id = fields.Char(string="Workflow ID")
    run_number = fields.Integer(string="Run #")
    event = fields.Char(string="Event")
    branch = fields.Char(string="Branch")
    commit = fields.Char(string="Commit", size=12)
    commit_url = fields.Char(string="Commit URL")
    status = fields.Selection(STATUS_SELECTION, string="Status", default="unknown")
    conclusion = fields.Selection(CONCLUSION_SELECTION, string="Conclusion")
    started_at = fields.Datetime(string="Started at")
    completed_at = fields.Datetime(string="Completed at")
    duration = fields.Integer(string="Duration (s)", compute="_compute_duration", store=True)
    duration_display = fields.Char(string="Duration", compute="_compute_duration")
    actor = fields.Char(string="Triggered by")
    html_url = fields.Char(string="URL")
    repository = fields.Char(string="Repository")
    outcome = fields.Selection(
        OUTCOME_SELECTION, string="Result", compute="_compute_outcome", store=True
    )

    # ------------------------------------------------------------------
    # Computed fields
    # ------------------------------------------------------------------
    @api.depends("started_at", "completed_at")
    def _compute_duration(self):
        for run in self:
            if run.started_at and run.completed_at:
                seconds = int((run.completed_at - run.started_at).total_seconds())
                run.duration = max(seconds, 0)
            else:
                run.duration = 0
            if run.duration:
                minutes, seconds = divmod(run.duration, 60)
                run.duration_display = "%dm%02ds" % (minutes, seconds)
            else:
                run.duration_display = ""

    @api.depends("status", "conclusion")
    def _compute_outcome(self):
        for run in self:
            if run.status == "completed":
                run.outcome = "success" if run.conclusion == "success" else "failure"
            elif run.status == "in_progress":
                run.outcome = "running"
            else:
                run.outcome = "pending"

    # ------------------------------------------------------------------
    # GitHub API
    # ------------------------------------------------------------------
    @api.model
    def _api_headers(self, config):
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "odoo-github-actions-status",
        }
        token = (config.token or "").strip()
        if token:
            headers["Authorization"] = "Bearer %s" % token
        return headers

    @api.model
    def _fetch_runs(self, config):
        """Call the GitHub API and return the raw list of workflow runs."""
        owner = (config.owner or "").strip()
        repo = (config.repo or "").strip()
        if not owner or not repo:
            raise UserError(_("Set the owner and the name of the repository to watch."))
        url = "%s/repos/%s/%s/actions/runs" % (config.api_url.rstrip("/"), owner, repo)
        params = {"per_page": max(1, min(config.limit or 30, 100))}
        if config.branch:
            params["branch"] = config.branch.strip()
        try:
            response = requests.get(
                url, headers=self._api_headers(config), params=params, timeout=30
            )
        except requests.exceptions.RequestException as error:
            raise UserError(_("Could not reach the GitHub API: %s") % error) from error

        if response.status_code == 404:
            raise UserError(
                _(
                    "Repository %(owner)s/%(repo)s not found (HTTP 404). "
                    "Check the owner and the name of the repository.",
                    owner=owner,
                    repo=repo,
                )
            )
        if response.status_code in (403, 429):
            message = _("The GitHub API refused the request (HTTP %s).", response.status_code)
            if response.headers.get("X-RateLimit-Remaining") == "0":
                message += _(
                    " The rate limit is exhausted, add an access token to raise it."
                )
            raise UserError(message)
        if response.status_code >= 400:
            raise UserError(
                _("The GitHub API returned HTTP %s: %s")
                % (response.status_code, (response.text or "")[:200])
            )
        try:
            payload = response.json()
        except ValueError as error:
            raise UserError(_("The GitHub API did not return valid JSON.")) from error
        return payload.get("workflow_runs") or []

    @api.model
    def _parse_datetime(self, value):
        """Convert an ISO 8601 timestamp of the API to a naive UTC datetime."""
        if not value:
            return False
        if isinstance(value, datetime):
            return value
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1]
        text = text.replace("T", " ", 1)
        text = text.split(".")[0].split("+")[0].strip()
        try:
            return fields.Datetime.to_datetime(text)
        except (TypeError, ValueError):
            return False

    @api.model
    def _values_from_api(self, raw, config):
        """Convert a raw workflow run of the API into the values of a record."""
        raw = raw or {}
        repository = raw.get("repository")
        repository = repository if isinstance(repository, dict) else {}
        owner = repository.get("owner")
        owner = owner.get("login") if isinstance(owner, dict) else None
        head_commit = raw.get("head_commit")
        head_commit = head_commit if isinstance(head_commit, dict) else {}
        actor = raw.get("actor")
        actor = actor.get("login") if isinstance(actor, dict) else None
        status = raw.get("status")
        conclusion = raw.get("conclusion")
        return {
            "github_id": str(raw.get("id") or ""),
            "workflow_name": raw.get("name") or raw.get("display_title") or _("Workflow"),
            "workflow_id": str(raw.get("workflow_id") or ""),
            "run_number": raw.get("run_number") or 0,
            "event": raw.get("event"),
            "branch": raw.get("head_branch"),
            "commit": (raw.get("head_sha") or "")[:12],
            "commit_url": head_commit.get("url"),
            "status": status if status in dict(STATUS_SELECTION) else "unknown",
            "conclusion": conclusion if conclusion in dict(CONCLUSION_SELECTION) else False,
            "started_at": self._parse_datetime(raw.get("run_started_at") or raw.get("created_at")),
            "completed_at": self._parse_datetime(raw.get("updated_at"))
            if status == "completed"
            else False,
            "actor": actor,
            "html_url": raw.get("html_url"),
            "repository": "%s/%s" % (owner or config.owner, repository.get("name") or config.repo),
        }

    @api.model
    def _sync_runs(self, payload, config):
        """Create/update the records from a raw payload and drop the oldest ones."""
        Run = self.sudo()
        raw_runs = [raw for raw in (payload or []) if raw.get("id")]
        identifiers = [str(raw["id"]) for raw in raw_runs]
        existing = {
            run.github_id: run
            for run in Run.search([("github_id", "in", identifiers)]) if run.github_id
        }
        for raw in raw_runs:
            values = self._values_from_api(raw, config)
            record = existing.get(values["github_id"])
            if record:
                record.write(values)
            else:
                Run.create(values)
        # Keep only the most recent runs
        keep = max(1, min(config.limit or 30, 100))
        obsolete = Run.search([], order="run_number desc, id desc", offset=keep)
        if obsolete:
            obsolete.unlink()
        return len(raw_runs)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_refresh(self):
        """Refresh the status.

        Called from the list header button, so it must also work when no
        record is selected.
        """
        config = self.env["github.actions.config"]._get_config()
        runs = self.env["github.actions.run"]._fetch_runs(config)
        count = self.env["github.actions.run"]._sync_runs(runs, config)
        config.write({"last_refresh": fields.Datetime.now()})
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("GitHub Actions"),
                "message": _("%s workflow run(s) updated.") % count,
                "type": "success",
                "sticky": False,
            },
        }

    def action_open_run(self):
        """Open the run on GitHub in a new tab."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": self.html_url,
            "target": "new",
        }

    @api.model
    def _cron_refresh(self):
        """Refresh the status without ever failing the scheduled action."""
        config = self.env["github.actions.config"]._get_config()
        if not config.auto_refresh:
            return
        try:
            runs = self._fetch_runs(config)
            self._sync_runs(runs, config)
            config.write({"last_refresh": fields.Datetime.now()})
        except UserError as error:
            _logger.warning("Could not refresh the GitHub Actions status: %s", error)
