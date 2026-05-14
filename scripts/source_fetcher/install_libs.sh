#!/usr/bin/env bash
# Install vendored Solidity libraries used by the MCC pipeline and per-case
# Foundry projects. Run from repo root after a fresh clone.
#
# What this installs (~51 MB total) into lib/vendored/:
#   forge-std                            v1.9.4
#   openzeppelin-contracts-v3.4.2        v3.4.2  (Solidity 0.6/0.7 cases)
#   openzeppelin-contracts-v4.9.5        v4.9.5  (Solidity 0.8.0-0.8.20)
#   openzeppelin-contracts-v5.0.2        v5.0.2  (post-2024)
#   openzeppelin-contracts-upgradeable-v4.9.5 v4.9.5
#   solady                               v0.0.245
#   solmate                              latest
#
# Idempotent: skips libs that are already cloned.

set -euo pipefail

# Resolve repo root (script lives in scripts/source_fetcher/).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENDORED="$REPO_ROOT/lib/vendored"

mkdir -p "$VENDORED"
cd "$VENDORED"

# clone_at <dir> <ref> <repo_url>
clone_at() {
    local dir="$1" ref="$2" url="$3"
    if [ -d "$dir/.git" ] || [ -d "$dir/contracts" ] || [ -d "$dir/src" ]; then
        echo "[skip] $dir (already present)"
        return 0
    fi
    echo "[clone] $dir @ $ref"
    git clone --depth 1 --branch "$ref" "$url" "$dir"
}

clone_at forge-std                                v1.9.4   https://github.com/foundry-rs/forge-std.git
clone_at openzeppelin-contracts-v3.4.2            v3.4.2   https://github.com/OpenZeppelin/openzeppelin-contracts.git
clone_at openzeppelin-contracts-v4.9.5            v4.9.5   https://github.com/OpenZeppelin/openzeppelin-contracts.git
clone_at openzeppelin-contracts-v5.0.2            v5.0.2   https://github.com/OpenZeppelin/openzeppelin-contracts.git
clone_at openzeppelin-contracts-upgradeable-v4.9.5 v4.9.5  https://github.com/OpenZeppelin/openzeppelin-contracts-upgradeable.git
clone_at solady                                   v0.0.245 https://github.com/Vectorized/solady.git

# solmate has no semver tags; default branch is fine.
if [ ! -d "solmate/.git" ] && [ ! -d "solmate/src" ]; then
    echo "[clone] solmate @ main"
    git clone --depth 1 https://github.com/transmissions11/solmate.git
else
    echo "[skip] solmate (already present)"
fi

# Trim .git history to slim the install (we don't need git history of deps).
find "$VENDORED" -type d -name ".git" -prune -exec rm -rf {} + 2>/dev/null || true

echo
echo "Installed vendored libs:"
du -sh "$VENDORED"/*
echo
echo "Done. Total size:"
du -sh "$VENDORED"
