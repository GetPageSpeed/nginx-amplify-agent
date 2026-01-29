"""
Test that all modules can be imported without errors.

This catches issues like:
- Missing dependencies
- Removed stdlib modules (e.g., asyncore in Python 3.12)
- Syntax errors
"""

import importlib
import sys

import pytest


# Core modules that must be importable
CORE_MODULES = [
    "amplify",
    "amplify.agent",
    # Note: amplify.agent.main parses sys.argv at import time, tested separately
    "amplify.agent.supervisor",
    "amplify.agent.common.context",
    "amplify.agent.common.errors",
]

# Modules with external dependencies
AGENT_MODULES = [
    "amplify.agent.managers.abstract",
    "amplify.agent.managers.nginx",
    "amplify.agent.managers.system",
    "amplify.agent.objects.abstract",
    "amplify.agent.objects.nginx.object",
    "amplify.agent.pipelines.abstract",
    "amplify.agent.pipelines.syslog",
    "amplify.agent.collectors.abstract",
    "amplify.agent.common.util.configreader",
    "amplify.agent.common.util.host",
    "amplify.agent.common.util.ps",
]


@pytest.mark.parametrize("module_name", CORE_MODULES)
def test_core_module_imports(module_name):
    """Test that core modules can be imported."""
    module = importlib.import_module(module_name)
    assert module is not None


@pytest.mark.parametrize("module_name", AGENT_MODULES)
def test_agent_module_imports(module_name):
    """Test that agent modules can be imported."""
    module = importlib.import_module(module_name)
    assert module is not None


def test_python_version_compatibility():
    """Verify we're running on a supported Python version."""
    assert sys.version_info >= (3, 8), "Python 3.8+ required"


def test_no_deprecated_stdlib_in_codebase():
    """Check that we don't import removed stdlib modules in our code."""
    import os
    import re

    deprecated_imports = [
        r"^\s*import\s+asyncore",
        r"^\s*from\s+asyncore\s+import",
        r"^\s*import\s+asynchat",
        r"^\s*from\s+asynchat\s+import",
    ]
    pattern = re.compile("|".join(deprecated_imports))

    amplify_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    amplify_pkg = os.path.join(amplify_dir, "amplify")

    violations = []
    for root, dirs, files in os.walk(amplify_pkg):
        for filename in files:
            if filename.endswith(".py"):
                filepath = os.path.join(root, filename)
                with open(filepath) as f:
                    for lineno, line in enumerate(f, 1):
                        if pattern.match(line):
                            violations.append(f"{filepath}:{lineno}: {line.strip()}")

    assert not violations, "Found deprecated stdlib imports:\n" + "\n".join(violations)
