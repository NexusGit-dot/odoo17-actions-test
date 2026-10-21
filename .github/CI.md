# GitHub Actions for Odoo 17

Two workflows are provided:

| Workflow | File | Trigger | Purpose |
|---|---|---|---|
| **Odoo CI** | `.github/workflows/ci.yml` | push / PR on any branch, manual | lint + install + unit tests |
| **Odoo Deploy** | `.github/workflows/deploy.yml` | manual, `v*` tag | pull the code on a server and restart Odoo |

The same `ci.yml` works in two situations:

* **full Odoo fork** (this repository): the Odoo sources are already there, the
  workflow uses them directly;
* **addon-only repository**: the workflow downloads the matching Odoo core as
  a tarball (`codeload.github.com/odoo/odoo/tar.gz/refs/heads/17.0`, ~170 MB)
  and adds the addons of the repository to its `--addons-path`. A tarball is
  used instead of `git clone` because it does not transfer the git history.

## 1. Before the first run

The workflows only run on **your own** repository. The `origin` remote currently
points to the official Odoo repository, so add your own fork first:

```bash
cd /path/to/Odoo17/odoo17
git remote add mine git@github.com:<your-user>/<your-repo>.git
git push mine main
```

Then open the repository on GitHub: the **Actions** tab lists the two
workflows. They are enabled as soon as the files are pushed to the default
branch.

## 2. What the CI does

### Job `lint` (ruff)

```bash
ruff check --config .github/ruff-custom-addons.toml odoo/custom_addons
```

* the **custom addons must be clean** -> this step blocks the pipeline;
* the python files changed by the push/PR are also checked, but only as a
  warning (the upstream Odoo sources are linted by Odoo's own runbot);
* `.github/ruff-custom-addons.toml` extends the root `ruff.toml` and only
  removes the rules that Odoo does not enforce itself, so code copied from the
  Odoo core does not raise false positives.

To fix the issues automatically:

```bash
ruff check --config .github/ruff-custom-addons.toml --fix odoo/custom_addons
```

### Job `addons-check`

Runs `.github/scripts/check_addons.py`, a static checker (no database, no
Odoo runtime) that verifies for every module of `odoo/custom_addons`:

* the manifest is a valid python literal and contains the required keys;
* the version starts with the series (`17.0`);
* every file listed in `data` exists;
* every directory containing `.py` files is an importable package
  (`__init__.py`);
* every `.xml` file is well formed;
* every `.csv` file has a constant number of columns.

### Job `test` (Odoo unit tests)

Starts a PostgreSQL 15 service, installs the Odoo dependencies and runs:

```bash
python odoo-bin \
  --addons-path="addons,odoo/addons,odoo/custom_addons" \
  --db_host=127.0.0.1 --db_port=5432 --db_user=odoo --db_password=odoo \
  -d ci_<run number> \
  -i app_one \
  --test-enable \
  --test-tags=/app_one \
  --without-demo=all \
  --stop-after-init \
  --workers=0 --max-cron-threads=0 \
  --log-level=test
```

`odoo-bin` exits with the code `1` as soon as one test fails, so the job
fails without any extra parsing of the logs. The full log is uploaded as an
artifact (`odoo-test-logs-<run number>`).

By default only the tests of the modules of `odoo/custom_addons` are executed
(`--test-tags` is built from the detected modules), which keeps the job fast
and avoids the flakiness of the upstream test suite. Use the
`workflow_dispatch` inputs to change that:

* `modules`: `app_one,my_other_module` - modules to install and test;
* `test_tags`: `*` to run every test, or `/app_one:TestProperty.test_name` to
  run a single test.

## 3. Writing the tests of a module

```python
# odoo/custom_addons/app_one/tests/__init__.py
from . import test_property

# odoo/custom_addons/app_one/tests/test_property.py
from odoo.tests.common import TransactionCase


class TestProperty(TransactionCase):

    def test_create_property(self):
        prop = self.env['property'].create({'name': 'Villa'})
        self.assertEqual(prop.name, 'Villa')
```

The `tests` package is **not** imported in the `__init__.py` of the module:
Odoo loads `odoo.addons.<module>.tests` by itself.

Run them locally with the same command as the CI (see above), or with:

```bash
python odoo-bin -d test_db -i app_one --test-enable --test-tags=/app_one \
    --stop-after-init --log-level=test
```

## 4. Deployment

`.github/workflows/deploy.yml` connects to your server over SSH, updates the
code and restarts the Odoo service. Add the following secrets in
**Settings -> Secrets and variables -> Actions**:

| Secret | Example | Description |
|---|---|---|
| `DEPLOY_HOST` | `odoo.example.com` | server address |
| `DEPLOY_PORT` | `22` | SSH port (optional) |
| `DEPLOY_USER` | `deploy` | user allowed to run `sudo systemctl` |
| `DEPLOY_SSH_KEY` | `-----BEGIN OPENSSH PRIVATE KEY----- ...` | private key |
| `DEPLOY_PATH` | `/opt/odoo` | directory containing the git clone |
| `DEPLOY_URL` | `https://odoo.example.com` | used for the HTTP check (optional) |
| `ODOO_SERVICE` | `odoo17` | systemd unit of Odoo |
| `ODOO_DB` | `production` | database to upgrade |
| `ODOO_CONF` | `/etc/odoo/odoo.conf` | configuration file of the server |

The SSH user must be allowed to run `sudo systemctl` without a password
(`visudo` -> `deploy ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart odoo17`).

Trigger it manually from the **Actions** tab, or push a `v*` tag. The
`modules` input of the manual trigger upgrades the given modules
(`-u module`) before restarting the service; leave it empty for a simple
restart.

## 5. Good to know

* **Odoo refuses the `postgres` database user.** The CI therefore creates a
  dedicated `odoo` role in the PostgreSQL service container.
* **Python version**: the CI uses Python 3.12 (Odoo 17 supports 3.10 - 3.12).
  Change `PYTHON_VERSION` in the workflow if needed.
* **Native dependencies**: `libpq-dev`, `libldap2-dev` and `libsasl2-dev` are
  required to build `psycopg2` and `python-ldap` from source.
* **The first run is slow** (compilation of the native dependencies); the pip
  cache is shared between the runs thanks to `cache: pip`.
