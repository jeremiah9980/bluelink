#!/usr/bin/env bash
# Publishes ./data to the orphan "status" branch as a single commit (no history bloat on main).
set -euo pipefail
cd data
rm -rf .git
git init -q -b status
git config user.name "bluelink-bot"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add -A
git commit -qm "status $(date -u +%Y-%m-%dT%H:%M:%SZ)"
git push -qf "https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" status
echo "Published to status branch"
