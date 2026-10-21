from odoo import _, api, fields, models


class GithubActionsConfig(models.Model):
    """Repository watched by the GitHub Actions status board."""

    _name = "github.actions.config"
    _description = "GitHub Actions configuration"
    _order = "id"

    owner = fields.Char(
        string="Owner",
        required=True,
        default="NexusGit-dot",
        help="Login of the GitHub account or organisation owning the repository.",
    )
    repo = fields.Char(
        string="Repository",
        required=True,
        default="nexusgrid",
        help="Name of the repository to watch.",
    )
    branch = fields.Char(
        string="Branch",
        help="Only show the runs of this branch. Leave empty to show every branch.",
    )
    token = fields.Char(
        string="Access token",
        groups="base.group_system",
        copy=False,
        help="Optional. A token with the 'Actions: read' permission raises the API rate "
        "limit and allows watching a private repository.",
    )
    api_url = fields.Char(
        string="API URL",
        required=True,
        default="https://api.github.com",
    )
    limit = fields.Integer(
        string="Runs to keep",
        default=30,
        help="Number of workflow runs displayed (and kept in database).",
    )
    auto_refresh = fields.Boolean(
        string="Automatic refresh",
        default=True,
        help="Refresh the status every 5 minutes with a scheduled action.",
    )
    last_refresh = fields.Datetime(readonly=True, copy=False)

    _sql_constraints = [
        ("owner_repo_uniq", "unique(owner, repo)", "Only one configuration is needed."),
    ]

    @api.model
    def _get_config(self):
        """Return the configuration record, creating it when it does not exist yet."""
        config = self.sudo().search([], limit=1)
        if not config:
            config = self.sudo().create({})
        return config

    def action_refresh(self):
        """Fetch the workflow runs of the configured repository."""
        self.ensure_one()
        config = self.sudo()
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
