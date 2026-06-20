from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from structural_compounding_lab.common.project_paths import (
    PROJECT_ROOT_ENV_VAR,
    output_root,
    package_root,
    project_root,
    resolve_project_path,
)


class ProjectPathTests(unittest.TestCase):
    def test_detects_clone_root_from_nested_start(self):
        expected = Path(__file__).resolve().parents[2]
        self.assertEqual(expected, project_root(Path(__file__).resolve().parent))
        self.assertEqual(expected / "structural_compounding_lab", package_root())
        self.assertEqual(expected / "structural_compounding_lab" / "output", output_root())

    def test_resolves_relative_path_under_clone_root(self):
        expected = Path(__file__).resolve().parents[2]
        relative = Path("structural_compounding_lab") / "data_storage" / "BTCUSDT" / "1m" / "tape.csv"
        self.assertEqual(expected / relative, resolve_project_path(relative))

    def test_environment_override_must_contain_package(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "structural_compounding_lab").mkdir()
            with patch.dict(os.environ, {PROJECT_ROOT_ENV_VAR: str(root)}):
                self.assertEqual(root.resolve(), project_root())

    def test_invalid_environment_override_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {PROJECT_ROOT_ENV_VAR: tmpdir}):
                with self.assertRaises(RuntimeError):
                    project_root()
