# nginx-amplify-agent Guidelines

## Overview
Python monitoring agent for GetPageSpeed Amplify. Collects system and NGINX metrics, sends to the Amplify server.

- Source: `https://github.com/GetPageSpeed/nginx-amplify-agent`
- Server repo: `~/Projects/amplify` (Go server that receives agent data)
- Agent config: `/etc/amplify-agent/agent.conf`

## Package Build Infrastructure

### Build Server
- Host: `builder@web.getpagespeed.com`
- CI: CircleCI (`.circleci/config.yml`)
- Integration tests: GitHub Actions (`.github/workflows/integration-test.yml`)

### RPM Packages (RHEL/CentOS/Amazon/Fedora/SLES)
- Spec file: `packages/nginx-amplify-agent/rpm/nginx-amplify-agent.spec`
- Docker images: `getpagespeed/rpmbuilder:<dist>` (e.g., `el7`, `el8`, `el9`, `el10`, `amzn2`, `amzn2023`, `fc42`, `fc43`, `sles15`, `sles16`)
- Deploy: `builder@web.getpagespeed.com:~/incoming/<project>/<dist>/<arch>/<branch>/`
- Deploy hook: `~/scripts/incoming.sh` (processes RPMs into yum repos)
- Requirements files: `requirements-amzn2.txt` (Python 3.6/3.7), `requirements-rhel9.txt` (Python 3.9+)

### DEB Packages (Debian/Ubuntu)
- Control files: `packages/nginx-amplify-agent/deb/debian/control.<codename>` (one per distro)
- Docker images: `getpagespeed/debbuilder:<suite>` (e.g., `ubuntu-focal`, `ubuntu-jammy`, `ubuntu-noble`, `debian-bookworm`, `debian-trixie`)
- Build rules: `packages/nginx-amplify-agent/deb/debian/rules`
- Deploy: `builder@web.getpagespeed.com:~/incoming-deb/<project>/<distro>/<codename>/<arch>/<branch>/`
- Deploy hook: `~/scripts/incoming-deb.sh` (processes DEBs via reprepro)
- All modern suites use `requirements-rhel9.txt`

### Package Repos (reprepro)
Repos are managed with `reprepro` on `builder@web.getpagespeed.com`. GPG signing uses `GNUPGHOME=/home/builder/.gnupg-deb`.

**Amplify-specific repo** (free, used by install script):
- Debian: `/srv/www/packages.amplify.getpagespeed.com/httpdocs/debian/`
- Ubuntu: `/srv/www/packages.amplify.getpagespeed.com/httpdocs/ubuntu/`
- Config: `conf/distributions` in each repo base
- URL: `https://packages.amplify.getpagespeed.com/{debian,ubuntu}/`

**Extras repo** (paid GetPageSpeed subscription):
- Debian: `/srv/www/extras.getpagespeed.com/httpdocs/debian/`
- Ubuntu: `/srv/www/extras.getpagespeed.com/httpdocs/ubuntu/`
- URL: `https://packages.getpagespeed.com/{debian,ubuntu}/` (via extras subdomain)

### Adding a New Distro

1. **Check Docker image exists**: `docker manifest inspect getpagespeed/debbuilder:<suite>` (or `rpmbuilder:<dist>`)
   - If missing, build it in `~/Projects/debbuilder/` (or rpmbuilder equivalent)
2. **Create control/spec file**: Copy from closest existing distro, adjust deps as needed
   - DEB: `packages/nginx-amplify-agent/deb/debian/control.<codename>`
   - RPM: Conditionals in `nginx-amplify-agent.spec`
3. **Add CI workflow**: Add build + deploy workflow to `.circleci/config.yml`
4. **Add reprepro distribution**: SSH to `builder@web.getpagespeed.com`, add distribution block to `conf/distributions` in BOTH repo bases (amplify + extras)
   ```
   Origin: GetPageSpeed
   Label: GetPageSpeed Amplify
   Suite: <codename>
   Codename: <codename>
   Architectures: amd64
   Components: amplify-agent
   Description: GetPageSpeed Amplify Agent for <distro> <codename>
   SignWith: yes
   ```
5. **Update install script**: Add codename to `packages/install.sh` supported list
6. **Add integration test**: Add to `.github/workflows/integration-test.yml` matrix
   - Debian: `dokken/debian-<ver>` (multi-arch, systemd preinstalled). Avoid `jrei/systemd-debian:*` — repushed arm64-only on 2026-05-03; agent .deb is amd64, so amd64-capable image required.
   - Ubuntu: `jrei/systemd-ubuntu:<codename>` (still publishes amd64)
   - RPM: `almalinux/<ver>-init`
7. **Bump version**: Increment release in `packages/version` to trigger rebuild
8. **Push and verify**: Push to master, wait for CI, run integration tests

### Supported Distros (as of March 2026)

**RPM**: el7, el8, el9, el10, amzn2, amzn2023, fc42, fc43, sles15, sles16
**DEB**: ubuntu-focal (20.04), ubuntu-jammy (22.04), ubuntu-noble (24.04), debian-bookworm (12), debian-trixie (13)

### Version Bumping
- Version file: `packages/version` (format: `MAJOR.MINOR.PATCH-RELEASE`, e.g., `1.8.4-8`)
- Bump the RELEASE number to trigger a rebuild without code changes
- CI auto-builds and deploys on push to master

## Install Script
- Location: `packages/install.sh`
- Served via: `https://amplify.getpagespeed.com/install.sh` (proxied from GitHub raw by the amplify server)
- Usage: `API_KEY='<key>' bash -c "$(curl -sSL https://amplify.getpagespeed.com/install.sh)"`
- Supported codenames are listed in a case statement around line 477
- DEB repo URL: `https://packages.amplify.getpagespeed.com/{ubuntu,debian}/`
- RPM repo URL: `https://packages.amplify.getpagespeed.com/py3/{os}/{release}/$basearch`

## Development Rules
- NEVER commit with `--no-verify`
- Bump `packages/version` release number when making packaging-only changes
- Test with integration tests via GitHub Actions: `gh workflow run integration-test.yml`
- Don't delete a remote branch (`git push origin --delete <branch>`) while CircleCI has queued pipelines for it — workers can race the deletion, fail `git checkout <sha>` with `reference is not a tree`, and email a failure notice. Wait for the pipeline to start (or cancel pending workflows manually) before deleting. Prefer `gh pr merge --squash --delete-branch` over branch-then-cherry-pick.

## Key Directories
```
packages/
  install.sh                              # Install script served to users
  version                                 # Package version (MAJOR.MINOR.PATCH-RELEASE)
  nginx-amplify-agent/
    rpm/
      nginx-amplify-agent.spec            # RPM spec (conditional requires per distro)
      nginx-amplify-agent.service         # Systemd unit
    deb/
      debian/
        control.<codename>                # Per-distro control files
        rules                             # Build rules
        postinst, preinst, prerm, postrm  # Lifecycle scripts
    requirements.txt                      # Base Python requirements
    requirements-amzn2.txt                # Python 3.6/3.7 (older gevent)
    requirements-rhel9.txt                # Python 3.9+ (modern gevent)
    setup.py                              # Standard setup
    setup-rpm.py                          # RPM-specific setup
    setup-deb.py                          # DEB-specific setup
```
