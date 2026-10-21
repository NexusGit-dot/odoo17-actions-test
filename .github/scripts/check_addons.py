#!/usr/bin/env python3
"""Static sanity checks for the custom Odoo addons of this repository.

The script does not need a database nor the Odoo runtime, so it is fast enough
to run as the very first CI step: it catches most of the packaging mistakes
(broken manifest, missing ``__init__.py``, malformed XML, inconsistent CSV)
before PostgreSQL and the Odoo server are even started.

Usage::

    python .github/scripts/check_addons.py                 # run all the checks
    python .github/scripts/check_addons.py --list-modules  # "mod_a,mod_b"

Exit code is 0 when everything is fine, 1 otherwise.
"""

from __future__ import annotations

import argparse
import ast
import csv
import os
import sys
import xml.etree.ElementTree as ET

DEFAULT_ADDONS_DIR = "odoo/custom_addons"
DEFAULT_SERIES = "17.0"
REQUIRED_MANIFEST_KEYS = ("name", "version")
RECOMMENDED_MANIFEST_KEYS = ("depends", "license", "author")


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, where: str, message: str) -> None:
        self.errors.append(f"{where}: {message}")

    def warn(self, where: str, message: str) -> None:
        self.warnings.append(f"{where}: {message}")


def iter_modules(addons_dir: str):
    """Yield ``(module_name, module_path)`` for every module of ``addons_dir``."""
    if not os.path.isdir(addons_dir):
        return
    for entry in sorted(os.listdir(addons_dir)):
        path = os.path.join(addons_dir, entry)
        if os.path.isdir(path) and os.path.isfile(os.path.join(path, "__manifest__.py")):
            yield entry, path


def load_manifest(module_path: str, report: Report):
    """Load a manifest the same way Odoo does (ast.literal_eval)."""
    manifest_file = os.path.join(module_path, "__manifest__.py")
    try:
        with open(manifest_file, encoding="utf-8") as f:
            content = f.read()
    except OSError as exc:
        report.error(manifest_file, f"cannot be read ({exc})")
        return None
    try:
        manifest = ast.literal_eval(content)
    except (SyntaxError, ValueError) as exc:
        report.error(manifest_file, f"is not a valid python literal ({exc})")
        return None
    if not isinstance(manifest, dict):
        report.error(manifest_file, "must evaluate to a dict")
        return None
    return manifest


def check_manifest(name: str, module_path: str, manifest: dict, series: str, report: Report) -> None:
    where = f"{name}/__manifest__.py"
    for key in REQUIRED_MANIFEST_KEYS:
        if not manifest.get(key):
            report.error(where, f"missing required key '{key}'")
    for key in RECOMMENDED_MANIFEST_KEYS:
        if key not in manifest:
            report.warn(where, f"recommended key '{key}' is missing")

    version = str(manifest.get("version") or "")
    if version and series and not version.startswith(series):
        report.error(where, f"version '{version}' does not start with the series '{series}'")

    depends = manifest.get("depends")
    if depends is not None and not isinstance(depends, (list, tuple)):
        report.error(where, "'depends' must be a list")

    # every file referenced in 'data' must exist
    for data_file in manifest.get("data") or []:
        if not os.path.exists(os.path.join(module_path, data_file)):
            report.error(where, f"data file '{data_file}' does not exist")


def check_python_packages(name: str, module_path: str, report: Report) -> None:
    """Every directory containing .py files must be an importable package."""
    for root, dirs, files in os.walk(module_path):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")]
        if any(f.endswith(".py") for f in files) and "__init__.py" not in files:
            rel = os.path.relpath(root, module_path)
            report.error(f"{name}/{rel}", "missing __init__.py (not an importable package)")


def check_xml_files(name: str, module_path: str, report: Report) -> None:
    for root, dirs, files in os.walk(module_path):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")]
        for f in files:
            if not f.endswith(".xml"):
                continue
            path = os.path.join(root, f)
            rel = os.path.relpath(path, module_path)
            try:
                ET.parse(path)
            except ET.ParseError as exc:
                report.error(f"{name}/{rel}", f"invalid XML ({exc})")


def check_csv_files(name: str, module_path: str, report: Report) -> None:
    """CSV files (access rights, data) must have a constant number of columns."""
    for root, dirs, files in os.walk(module_path):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")]
        for f in files:
            if not f.endswith(".csv"):
                continue
            path = os.path.join(root, f)
            rel = os.path.relpath(path, module_path)
            try:
                with open(path, newline="", encoding="utf-8") as fh:
                    rows = list(csv.reader(fh))
            except (OSError, csv.Error) as exc:
                report.error(f"{name}/{rel}", f"cannot be read ({exc})")
                continue
            if not rows:
                continue
            width = len(rows[0])
            for i, row in enumerate(rows[1:], start=2):
                if len(row) != width:
                    report.error(
                        f"{name}/{rel}",
                        f"line {i} has {len(row)} columns, expected {width}",
                    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--addons-dir", default=DEFAULT_ADDONS_DIR)
    parser.add_argument("--series", default=DEFAULT_SERIES)
    parser.add_argument("--list-modules", action="store_true",
                        help="print the comma separated list of modules and exit")
    args = parser.parse_args()

    modules = list(iter_modules(args.addons_dir))
    if args.list_modules:
        print(",".join(name for name, _ in modules))
        return 0

    if not modules:
        print(f"No module found in '{args.addons_dir}' - nothing to check.")
        return 0

    report = Report()
    for name, module_path in modules:
        manifest = load_manifest(module_path, report)
        if manifest is not None:
            check_manifest(name, module_path, manifest, args.series, report)
        check_python_packages(name, module_path, report)
        check_xml_files(name, module_path, report)
        check_csv_files(name, module_path, report)

    for warning in report.warnings:
        print(f"WARNING  {warning}")
    for error in report.errors:
        print(f"ERROR    {error}")

    print(f"\n{len(modules)} module(s) checked, {len(report.errors)} error(s), {len(report.warnings)} warning(s).")
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
