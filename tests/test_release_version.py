"""Regression checks for agent release versions and CircleCI parity gates."""

import ast
import importlib.util
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check-release-version.py"
spec = importlib.util.spec_from_file_location("check_release_version", SCRIPT)
release_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_check)


@pytest.fixture
def source_root(tmp_path):
    """Create a source tree containing only the version check inputs."""
    for name in ("packages/version", "amplify/agent/common/context.py"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text((ROOT / name).read_text())
    return tmp_path


def test_current_release_matches_actual_context():
    """Assert the running Context reports the package release."""
    from amplify.agent.common.context import Context

    expected = (ROOT / "packages/version").read_text().strip()
    assert Context().version == expected
    assert release_check.check_local(ROOT) == expected.split("-")[0]


@pytest.mark.parametrize(
    "release",
    ["1.8.18", "1.8.18-0", "1.8.18-01", "v1.8.18-1", "1.8.18-1-extra", "1.8.18-1 ", "1.8.18-1\n", "1.8.x-1", ""],
)
def test_rejects_invalid_package_versions(source_root, release):
    """Reject malformed release strings and nonpositive builds."""
    (source_root / "packages/version").write_text(release + "\n")
    with pytest.raises(ValueError, match="packages/version"):
        release_check.check_local(source_root)


def test_rejects_runtime_version_drift(source_root):
    """Detect a runtime version that differs from the release file."""
    path = source_root / "amplify/agent/common/context.py"
    path.write_text(path.read_text().replace("self.version_semver = (1, 8, 18)", "self.version_semver = (1, 8, 17)"))
    with pytest.raises(ValueError, match="differs"):
        release_check.check_local(source_root)


def test_extracted_runtime_matches_source_release(source_root, tmp_path):
    """Compare a release file with an extracted artifact lacking that file."""
    runtime_root = tmp_path / "site-packages"
    context = runtime_root / "amplify/agent/common/context.py"
    context.parent.mkdir(parents=True)
    context.write_text((source_root / "amplify/agent/common/context.py").read_text())
    assert not (runtime_root / "packages/version").exists()
    assert release_check.check_local(source_root, runtime_root) == "1.8.18"
    assert release_check.main(["--source-root", str(source_root), "--runtime-root", str(runtime_root)]) == 0


def test_extracted_runtime_drift_fails(source_root, tmp_path, capsys):
    """Reject an extracted runtime whose version differs from the source."""
    runtime_root = tmp_path / "site-packages"
    context = runtime_root / "amplify/agent/common/context.py"
    context.parent.mkdir(parents=True)
    context.write_text(
        (source_root / "amplify/agent/common/context.py")
        .read_text()
        .replace("self.version_semver = (1, 8, 18)", "self.version_semver = (1, 8, 17)")
    )
    assert not (runtime_root / "packages/version").exists()
    with pytest.raises(ValueError, match="differs"):
        release_check.check_local(source_root, runtime_root)
    assert release_check.main(["--source-root", str(source_root), "--runtime-root", str(runtime_root)]) == 1
    assert "differs" in capsys.readouterr().err


@pytest.mark.parametrize("semver", ["(True, 8, 18)", "(1, False, 18)", "(1, 8, True)"])
def test_rejects_boolean_runtime_semver(source_root, semver):
    """Reject booleans in the runtime semantic version tuple."""
    path = source_root / "amplify/agent/common/context.py"
    path.write_text(path.read_text().replace("self.version_semver = (1, 8, 18)", f"self.version_semver = {semver}"))
    with pytest.raises(ValueError, match="version_semver"):
        release_check.check_local(source_root)


@pytest.mark.parametrize(
    "replacement",
    ["self.version_build = 0", "self.version_build = True", "self.version_build = unknown", "self.version_build = '1'"],
)
def test_rejects_invalid_runtime_literal(source_root, replacement):
    """Reject missing, dynamic, and invalid runtime build values."""
    path = source_root / "amplify/agent/common/context.py"
    path.write_text(path.read_text().replace("self.version_build = 1", replacement))
    with pytest.raises(ValueError, match="version_build"):
        release_check.check_local(source_root)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"status": "degraded", "database": "connected", "latest_agent_version": "1.8.18"},
        {"status": "healthy", "database": "disconnected", "latest_agent_version": "1.8.18"},
        {"status": "healthy", "database": "connected", "latest_agent_version": "1.8.17"},
        {"status": "healthy", "database": "connected", "latest_agent_version": "1.8.18-1"},
        {"status": "healthy", "database": "connected"},
    ],
)
def test_health_parity_failures_are_visible(payload):
    """Reject malformed, incomplete, unhealthy, and mismatched health data."""
    with pytest.raises(ValueError):
        release_check.check_health("https://example.test/health", "1.8.18", fetcher=lambda url: payload)


def test_healthy_production_version_passes():
    """Accept a healthy response advertising the bare release version."""
    payload = {"status": "healthy", "database": "connected", "latest_agent_version": "1.8.18"}
    release_check.check_health("https://example.test/health", "1.8.18", fetcher=lambda url: payload)


@pytest.mark.parametrize(
    "error", [OSError("network unavailable"), ValueError("invalid JSON"), TimeoutError("timed out")]
)
def test_cli_reports_fetch_failures(source_root, monkeypatch, capsys, error):
    """Exit nonzero when the owned fetch seam reports a transport or JSON error."""

    def fail_fetch(url, timeout=5):
        raise error

    monkeypatch.setattr(release_check, "fetch_health", fail_fetch)
    assert release_check.main(["--source-root", str(source_root), "--health-url", "https://example.test/health"]) == 1
    assert str(error) in capsys.readouterr().err


def test_cli_default_checks_local_source(capsys):
    """Run the local check without contacting a health endpoint."""
    assert release_check.main([]) == 0
    assert "1.8.18" in capsys.readouterr().out


def test_package_metadata_matches_bare_release():
    """Keep RPM, DEB, and pyproject package metadata at the bare release."""
    bare = release_check.check_local(ROOT)
    for name in ("setup-rpm.py", "setup-deb.py"):
        path = ROOT / "packages/nginx-amplify-agent" / name
        module = ast.parse(path.read_text())
        calls = [
            node
            for node in ast.walk(module)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "setup"
        ]
        assert len(calls) == 1
        versions = [ast.literal_eval(kw.value) for kw in calls[0].keywords if kw.arg == "version"]
        assert versions == [bare], name
    pyproject = (ROOT / "pyproject.toml").read_text()
    project = pyproject.split("[project]", 1)[1].split("\n[", 1)[0]
    assert re.search(rf'^version = "{re.escape(bare)}"$', project, re.MULTILINE)


def test_each_distro_workflow_verifies_after_deploy():
    """Require a uniquely named parity job after every distro deploy."""
    config = (ROOT / ".circleci/config.yml").read_text()
    workflows = config.split("\nworkflows:\n", 1)[1]
    blocks = re.findall(r"^  (build-[a-z0-9]+):\n(.*?)(?=^  build-|\Z)", workflows, re.MULTILINE | re.DOTALL)
    assert len(blocks) == 13
    names = []
    for workflow, block in blocks:
        deploy = re.search(r"^          name: (deploy-[a-z0-9_-]+)$", block, re.MULTILINE)
        verify = re.search(
            r"^      - verify-release-parity:\n          name: (verify-release-parity-[a-z0-9_-]+)\n          requires: \[([^]]+)\]",
            block,
            re.MULTILINE,
        )
        assert deploy and verify, workflow
        assert verify.group(2) == deploy.group(1), workflow
        names.append(verify.group(1))
    assert len(names) == len(set(names))
    assert "python3 scripts/check-release-version.py --health-url https://amplify.getpagespeed.com/health" in config


def test_myci_routes_to_package_workflows():
    """Select the package CI config ahead of auxiliary GitHub workflows."""
    assert (ROOT / ".myci/settings.yml").read_text() == "config: .circleci/config.yml\n"
    assert (ROOT / ".circleci/config.yml").is_file()


def test_each_distro_workflow_separates_build_and_deploy_contexts():
    """Keep publishing credentials off build and parity jobs in every distro."""
    config = (ROOT / ".circleci/config.yml").read_text()
    assert "org-global" not in config
    workflows = config.split("\nworkflows:\n", 1)[1]
    blocks = re.findall(r"^  (build-[a-z0-9]+):\n(.*?)(?=^  build-|\Z)", workflows, re.MULTILINE | re.DOTALL)
    assert len(blocks) == 13
    for workflow, block in blocks:
        build = block.split("      - build-", 1)[1].split("      - deploy-", 1)[0]
        deploy = block.split("      - deploy-", 1)[1].split("      - verify-release-parity:", 1)[0]
        parity = block.split("      - verify-release-parity:", 1)[1]
        assert re.findall(r"^          context: (.+)$", build, re.MULTILINE) == ["build-deps"], workflow
        assert re.findall(r"^          context: (.+)$", deploy, re.MULTILINE) == ["deploy"], workflow
        assert not re.search(r"^          context:", parity, re.MULTILINE), workflow


def test_rpm_workflows_preflight_source_version_without_builder_python():
    """Gate every RPM build on a secret-free Python job outside rpmbuilder."""
    config = (ROOT / ".circleci/config.yml").read_text()
    jobs = config.split("\njobs:\n", 1)[1].split("\nworkflows:\n", 1)[0]
    preflight = jobs.split("  verify-source-version:\n", 1)[1].split("\n  verify-release-parity:\n", 1)[0]
    assert "image: cimg/python:3.12" in preflight
    assert "- checkout" in preflight
    assert "command: python3 scripts/check-release-version.py" in preflight
    assert "context:" not in preflight
    rpm = jobs.split("  build-rpm:\n", 1)[1].split("\n  deploy-rpm:\n", 1)[0]
    assert "python3" not in rpm
    assert re.search(r'steps:\n      - checkout\n      - run:\n          name: "Prepare spec file and sources"', rpm)

    workflows = config.split("\nworkflows:\n", 1)[1]
    blocks = re.findall(r"^  (build-[a-z0-9]+):\n(.*?)(?=^  build-|\Z)", workflows, re.MULTILINE | re.DOTALL)
    rpm_blocks = [(workflow, block) for workflow, block in blocks if "      - build-rpm:" in block]
    assert len(rpm_blocks) == 8
    names = []
    for workflow, block in rpm_blocks:
        preflight_job = re.search(
            r"^      - verify-source-version:\n          name: (verify-source-version-[a-z0-9_-]+)$",
            block,
            re.MULTILINE,
        )
        build = re.search(r"^      - build-rpm:\n(.*?)(?=^      - deploy-rpm:)", block, re.MULTILINE | re.DOTALL)
        assert preflight_job and build, workflow
        assert "          context:" not in block.split("      - build-rpm:", 1)[0], workflow
        assert f"          requires: [{preflight_job.group(1)}]" in build.group(1), workflow
        names.append(preflight_job.group(1))
    assert len(names) == len(set(names))


def test_deb_build_checks_version_before_side_effects():
    """Keep local validation immediately after checkout in the DEB builder."""
    config = (ROOT / ".circleci/config.yml").read_text()
    jobs = config.split("\njobs:\n", 1)[1].split("\nworkflows:\n", 1)[0]
    deb = jobs.split("  build-deb:\n", 1)[1].split("\n  deploy-deb:\n", 1)[0]
    assert re.search(
        r'steps:\n      - checkout\n      - run:\n          name: "Verify local release version"\n          command: python3 scripts/check-release-version.py\n      - run:',
        deb,
    )


def test_integration_jobs_assert_installed_runtime_version():
    """Check every published-package integration job against the release file."""
    workflow = (ROOT / ".github/workflows/integration-test.yml").read_text()
    jobs = re.findall(
        r"^  (test-(?:deb|deb-reinstall-recovery|rpm)):\n(.*?)(?=^  test-|\Z)", workflow, re.MULTILINE | re.DOTALL
    )
    assert {name for name, _ in jobs} == {"test-deb", "test-deb-reinstall-recovery", "test-rpm"}
    for name, block in jobs:
        assert "    steps:\n      - uses: actions/checkout@v4\n" in block, name
        install = "Reinstall via install.sh must succeed" if name == "test-deb-reinstall-recovery" else "Run install.sh"
        assert block.index(f"      - name: {install}") < block.index(
            "      - name: Verify installed agent version"
        ), name
        assert 'expected="$(cat packages/version)"' in block, name
        if name == "test-rpm":
            assert (
                "docker exec agent-test python3 -c 'import sys, amplify; sys.path.insert(0, amplify.__path__[0]); "
                "from amplify.agent.common.context import Context; print(Context().version)'" in block
            ), name
        else:
            assert (
                "docker exec agent-test python3 -c 'from amplify.agent.common.context import Context; print(Context().version)'"
                in block
            ), name
            assert "sys.path.insert" not in block, name
        assert 'test "$actual" = "$expected"' in block, name
