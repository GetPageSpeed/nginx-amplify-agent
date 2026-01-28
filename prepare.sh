#!/bin/bash
# Prepare sources for RPM build
# This script copies the spec file to root, substitutes version placeholders,
# and creates the source tarball

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Read version from packages/version
PKG_VERSION=$(cut -d- -f1 < packages/version)
PKG_RELEASE=$(cut -d- -f2 < packages/version)

echo "Version: $PKG_VERSION"
echo "Release: $PKG_RELEASE"

# Copy spec file to root
cp packages/nginx-amplify-agent/rpm/nginx-amplify-agent.spec .
cp packages/nginx-amplify-agent/rpm/nginx-amplify-agent.service .

# Substitute version placeholders
sed -i.bak "s/%%AMPLIFY_AGENT_VERSION%%/$PKG_VERSION/g" nginx-amplify-agent.spec
sed -i.bak "s/%%AMPLIFY_AGENT_RELEASE%%/$PKG_RELEASE/g" nginx-amplify-agent.spec

# Select requirements file based on distro
# If argument passed, use it; otherwise detect from /etc/os-release
if [ -n "${1:-}" ]; then
    DIST="$1"
elif [ -f /etc/os-release ]; then
    # Detect distro from os-release (use subshell to avoid polluting our variables)
    DIST=$(
        source /etc/os-release
        case "$ID" in
            amzn)
                if [ "$VERSION_ID" = "2" ]; then
                    echo "amzn2"
                else
                    echo "amzn2023"
                fi
                ;;
            rhel|rocky|almalinux|centos)
                echo "el${VERSION_ID%%.*}"
                ;;
            fedora)
                echo "fc${VERSION_ID}"
                ;;
            opensuse*|sles)
                echo "sles${VERSION_ID%%.*}"
                ;;
            *)
                echo "el9"  # fallback
                ;;
        esac
    )
else
    DIST="el9"  # fallback
fi

echo "Detected distro: $DIST"

REQUIREMENTS_FILE="packages/nginx-amplify-agent/requirements.txt"

# Python 3.6 distros (el7, el8, sles15, amzn2) need older gevent (<24.0)
# Python 3.9+ distros (el9, el10, fc*, sles16, amzn2023) can use modern gevent
case "$DIST" in
    el7|el8|sles15|amzn2)
        # Python 3.6/3.7 - need older gevent
        if [ -f "packages/nginx-amplify-agent/requirements-amzn2.txt" ]; then
            REQUIREMENTS_FILE="packages/nginx-amplify-agent/requirements-amzn2.txt"
        fi
        ;;
    el9|el10|fc*|sles16|amzn2023)
        # Python 3.9+ - can use modern gevent
        if [ -f "packages/nginx-amplify-agent/requirements-rhel9.txt" ]; then
            REQUIREMENTS_FILE="packages/nginx-amplify-agent/requirements-rhel9.txt"
        fi
        ;;
esac

# Substitute requirements file placeholder
sed -i.bak "s|%%REQUIREMENTS%%|$REQUIREMENTS_FILE|g" nginx-amplify-agent.spec

# Clean up backup files
rm -f nginx-amplify-agent.spec.bak

echo "Using requirements file: $REQUIREMENTS_FILE"

# Create source tarball
# The spec expects nginx-amplify-agent-{version}.tar.gz with content in nginx-amplify-agent-{version}/ subdirectory
TARBALL_NAME="nginx-amplify-agent-${PKG_VERSION}"
TARBALL_FILE="${TARBALL_NAME}.tar.gz"

echo "Creating source tarball: $TARBALL_FILE"

# Create a temporary directory for tarball contents
TMPDIR=$(mktemp -d)
mkdir -p "${TMPDIR}/${TARBALL_NAME}"

# Copy source files using cp and find (works without rsync)
# Exclude .git, build artifacts, etc.
find . -mindepth 1 -maxdepth 1 \
    ! -name '.git' \
    ! -name '*.tar.gz' \
    ! -name '*.rpm' \
    ! -name '*.spec' \
    ! -name '.circleci' \
    ! -name '.github' \
    ! -name '.ruff_cache' \
    ! -name '.cursor' \
    ! -name 'nginx-amplify-agent.service' \
    -exec cp -R {} "${TMPDIR}/${TARBALL_NAME}/" \;

# Copy the RPM-specific setup.py to root of tarball (avoids circular import issues)
cp packages/nginx-amplify-agent/setup-rpm.py "${TMPDIR}/${TARBALL_NAME}/setup.py"

# Create the tarball
tar -czf "$TARBALL_FILE" -C "$TMPDIR" "$TARBALL_NAME"

# Cleanup
rm -rf "$TMPDIR"

echo "Spec file and tarball prepared successfully."
