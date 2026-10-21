# GitHub Actions Status

Displays the CI status of a GitHub repository **inside Odoo**.

The module calls the GitHub REST API
(`/repos/<owner>/<repo>/actions/runs`) and shows the workflow runs in a list:
workflow name, result badge, branch, commit, duration and a link to the run
on GitHub.

## Menus

| Menu | What |
|---|---|
| `CI (GitHub Actions) > Workflow runs` | the list of the runs, with a **Refresh** button |
| `CI (GitHub Actions) > Configuration` | owner, repository, branch, token, refresh options |

## Configuration

| Field | Meaning |
|---|---|
| `owner` | GitHub login of the owner, e.g. `NexusGit-dot` |
| `repo` | name of the repository, e.g. `nexusgrid` |
| `branch` | optional, restricts the list to one branch |
| `token` | optional, a token with the `Actions: read` permission (administrators only) |
| `limit` | number of runs displayed and kept in database |
| `auto_refresh` | refresh every 5 minutes with the scheduled action |

The public repositories are readable without a token, but the GitHub API
allows only 60 requests per hour and per IP address. A token raises that
limit to 5000 requests per hour.

## How it works

* the runs are fetched by `github.actions.run._fetch_runs()` and stored in the
  `github.actions.run` table, so the list opens instantly and keeps working
  when the network or the API is down;
* the scheduled action *GitHub Actions: refresh the CI status* updates the
  table every 5 minutes;
* the button **Refresh** forces an immediate update;
* a failed call never breaks the scheduled action: the last known status is
  kept and the error is only written in the server log.

## Tests

```bash
odoo-bin -d <database> -i github_actions --test-enable --test-tags=/github_actions
```
