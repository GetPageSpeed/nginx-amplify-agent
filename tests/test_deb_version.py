"""Pin the DEB package version derived from packages/version."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_deb_version_carries_release_suffix(tmp_path):
    """Render the DEB changelog so a release-only bump yields a new apt version."""
    config = (ROOT / ".circleci/config.yml").read_text()
    lines = [line.strip() for line in config.splitlines()]
    start = lines.index(
        "VERSION=$(cat packages/version | cut -d- -f1)", lines.index('name: "Prepare DEB package sources"')
    )
    end = next(i for i in range(start, len(lines)) if "> debian/changelog" in lines[i])
    (tmp_path / "packages").mkdir()
    (tmp_path / "packages/version").write_text("1.2.3-4\n")
    (tmp_path / "debian").mkdir()
    subprocess.run(
        ["bash", "-euc", "\n".join(lines[start : end + 1])], cwd=tmp_path, check=True, env={"SUITE_NAME": "noble"}
    )
    changelog = (tmp_path / "debian/changelog").read_text()
    assert changelog == "nginx-amplify-agent (1.2.3-4~noble) noble; urgency=low\n"
