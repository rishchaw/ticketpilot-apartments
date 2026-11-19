"""Cloud CLI errors must survive Windows consoles using a narrow encoding."""
import os
from pathlib import Path
import subprocess
import sys


def test_unicode_argument_error_is_utf8_and_never_runs_a_cloud_operation():
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONIOENCODING": "ascii", "PYTHONUTF8": "0"}
    result = subprocess.run(
        [sys.executable, str(root / "scripts/cloud.py"), "aws", "status", "--unknown-option", "\u2192"],
        cwd=root, env=env, capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert result.returncode == 2
    assert "unrecognized arguments: --unknown-option \u2192" in result.stderr
    assert "UnicodeEncodeError" not in result.stderr
