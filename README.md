# Odoo 17 - GitHub Actions test repository

This repository is a **test bed** for the GitHub Actions pipelines described in
[`.github/CI.md`](.github/CI.md).

It contains only the custom addon `app_one`; the CI downloads the matching
Odoo core (`odoo/odoo`, branch `17.0`) and runs the addon against a real
PostgreSQL database.

| What | Where |
|---|---|
| CI workflow | `.github/workflows/ci.yml` |
| Deployment workflow | `.github/workflows/deploy.yml` (in the full fork) |
| Static addon checker | `.github/scripts/check_addons.py` |
| Lint configuration | `.github/ruff-custom-addons.toml` |
| The addon under test | `odoo/custom_addons/app_one` |

## Pipelines

| Job | What it does | Blocking |
|---|---|---|
| `Lint (ruff)` | ruff on the custom addons + on the changed files | yes (custom addons) |
| `Addons structure` | manifest / `__init__.py` / XML / CSV checks | yes |
| `Unit tests (Odoo)` | installs the modules and runs the Odoo test suite | yes |
| `Lint (pylint-odoo)` | OCA style checks | no (advisory) |

## Triggering a run

* every push and pull request on the `17.0` branch;
* manually from the **Actions** tab -> **Odoo CI** -> **Run workflow**, with
  the optional `modules` and `test_tags` inputs.

## Local equivalent

```bash
python odoo-bin \
  --addons-path="addons,odoo/addons,$PWD/odoo/custom_addons" \
  -d test_db -i app_one --test-enable --test-tags=/app_one \
  --without-demo=all --stop-after-init --log-level=test
```
