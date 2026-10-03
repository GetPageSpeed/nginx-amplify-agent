#!/usr/bin/env python3
"""Check agent release versions in source and the deployed health endpoint."""

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from urllib.request import urlopen


RELEASE_RE = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)-([1-9][0-9]*)\Z")
DEFAULT_ROOT = Path(__file__).resolve().parents[1]


def read_release(source_root):
    """Read and validate the release version from a source tree.

    Args:
        source_root: Path to the source root.

    Returns:
        Full release version and bare semantic version.

    Raises:
        ValueError: The release version has an invalid format.
    """
    release = (Path(source_root) / "packages/version").read_text()
    if release.endswith("\n"):
        release = release[:-1]
    match = RELEASE_RE.fullmatch(release)
    if match is None:
        raise ValueError(f"packages/version must be X.Y.Z-N with a positive build: {release!r}")
    return release, ".".join(match.group(i) for i in (1, 2, 3))


def runtime_release(runtime_root):
    """Read the literal Context version components without importing the agent.

    Args:
        runtime_root: Path to the source or extracted Python package root.

    Returns:
        Full runtime release version.

    Raises:
        ValueError: Context has missing or invalid literal version components.
    """
    path = Path(runtime_root) / "amplify/agent/common/context.py"
    module = ast.parse(path.read_text(), filename=str(path))
    values = {}
    for node in module.body:
        if not isinstance(node, ast.ClassDef) or node.name != "Context":
            continue
        for method in node.body:
            if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) or method.name != "__init__":
                continue
            for statement in method.body:
                if not isinstance(statement, ast.Assign):
                    continue
                for target in statement.targets:
                    if (
                        isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "self"
                    ):
                        if target.attr in ("version_semver", "version_build"):
                            if target.attr in values:
                                raise ValueError(f"duplicate Context.{target.attr} assignment")
                            try:
                                values[target.attr] = ast.literal_eval(statement.value)
                            except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
                                raise ValueError(f"Context.{target.attr} must be a literal")
    semver = values.get("version_semver")
    build = values.get("version_build")
    if (
        not isinstance(semver, tuple)
        or len(semver) != 3
        or any(not isinstance(n, int) or isinstance(n, bool) or n < 0 for n in semver)
    ):
        raise ValueError("Context.version_semver must be a literal tuple of three nonnegative integers")
    if not isinstance(build, int) or isinstance(build, bool) or build < 1:
        raise ValueError("Context.version_build must be a positive integer literal")
    return "{}.{}.{}-{}".format(*semver, build)


def check_local(source_root=DEFAULT_ROOT, runtime_root=None):
    """Verify package and runtime versions in a source tree.

    Args:
        source_root: Path to the source root containing packages/version.
        runtime_root: Optional extracted Python package root; defaults to source_root.

    Returns:
        Bare semantic release version.

    Raises:
        ValueError: The package and runtime versions differ.
    """
    release, bare = read_release(source_root)
    runtime = runtime_release(source_root if runtime_root is None else runtime_root)
    if runtime != release:
        raise ValueError(f"runtime version {runtime} differs from packages/version {release}")
    return bare


def fetch_health(url, timeout=5):
    """Fetch and decode a health JSON response.

    Args:
        url: Health endpoint URL.
        timeout: Maximum HTTP request time in seconds.

    Returns:
        Decoded JSON value.
    """
    with urlopen(url, timeout=timeout) as response:
        return json.load(response)


def check_health(url, expected_version, fetcher=None):
    """Verify production health and its advertised agent version.

    Args:
        url: Health endpoint URL.
        expected_version: Bare semantic release version.
        fetcher: Owned health-fetch function, injectable by tests.

    Raises:
        ValueError: Health data is missing, malformed, or mismatched.
    """
    data = (fetcher or fetch_health)(url)
    if not isinstance(data, dict):
        raise ValueError("health response must be a JSON object")
    expected = {"status": "healthy", "database": "connected", "latest_agent_version": expected_version}
    for key, value in expected.items():
        if data.get(key) != value:
            raise ValueError(f"health {key} expected {value!r}, got {data.get(key)!r}")


def main(argv=None):
    """Run local checks and optional production parity verification.

    Args:
        argv: Optional command-line arguments.

    Returns:
        Process exit status.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument(
        "--runtime-root", type=Path, help="Extracted Python package root containing amplify/agent/common/context.py"
    )
    parser.add_argument("--health-url")
    args = parser.parse_args(argv)
    try:
        bare = check_local(args.source_root, args.runtime_root)
        if args.health_url:
            check_health(args.health_url, bare)
    except (ValueError, OSError, SyntaxError) as error:
        print(f"Release version check failed: {error}", file=sys.stderr)
        return 1
    print("Release version check passed: {}{}".format(bare, " (health parity)" if args.health_url else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
