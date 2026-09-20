#!/usr/bin/env bash
# One-time setup: creates a PRIVATE GitHub repo with the Bluelink workflows,
# stores your Bluelink login as encrypted Actions secrets, and (optionally)
# publishes the dashboard page on GitHub Pages.
set -euo pipefail
cd "$(dirname "$0")"

REPO_NAME="${1:-ioniq-bluelink}"
PAGES_REPO="${REPO_NAME}-dashboard"

command -v gh >/dev/null || { echo "GitHub CLI missing. Run: brew install gh"; exit 1; }
gh auth status >/dev/null 2>&1 || gh auth login
OWNER="$(gh api user -q .login)"
FULL="$OWNER/$REPO_NAME"
echo "→ GitHub user: $OWNER"

# 1) Private repo with the code + workflows
[ -d .git ] || git init -q -b main
git add -A
git -c user.name="$OWNER" -c user.email="$OWNER@users.noreply.github.com" commit -qm "Ioniq 5 Bluelink remote" || true
if gh repo view "$FULL" >/dev/null 2>&1; then
  git remote get-url origin >/dev/null 2>&1 || git remote add origin "https://github.com/$FULL.git"
  git push -qu origin main
else
  gh repo create "$FULL" --private --source . --remote origin --push
fi
echo "✓ Private repo: https://github.com/$FULL"

# 2) Secrets (typed at a hidden prompt; never saved on disk or in shell history)
echo
echo "Now enter your MyHyundai / Bluelink login. Each prompt hides what you type."
gh secret set BLUELINK_USERNAME -R "$FULL"
gh secret set BLUELINK_PASSWORD -R "$FULL"
gh secret set BLUELINK_PIN -R "$FULL"
read -r -p "Test with FAKE car data first (no Hyundai login)? [y/N] " mock
if [[ "${mock:-n}" =~ ^[Yy] ]]; then
  gh variable set BLUELINK_MOCK -R "$FULL" --body 1
  echo "  Mock mode ON. Turn it off later with: gh variable delete BLUELINK_MOCK -R $FULL"
else
  gh variable delete BLUELINK_MOCK -R "$FULL" >/dev/null 2>&1 || true
fi

# 3) First status run
sleep 4
gh workflow run status.yml -R "$FULL" && echo "✓ Started first status check (takes ~1 min)"

# 4) Dashboard hosting
DASH_URL=""
read -r -p "Publish the dashboard page on GitHub Pages? It goes in a separate PUBLIC repo that holds only the page, with no car data or secrets. [Y/n] " pages
if [[ ! "${pages:-y}" =~ ^[Nn] ]]; then
  tmp="$(mktemp -d)"; cp dashboard/index.html "$tmp/"; touch "$tmp/.nojekyll"
  ( cd "$tmp" && git init -q -b main && git add -A &&
    git -c user.name="$OWNER" -c user.email="$OWNER@users.noreply.github.com" commit -qm "dashboard" )
  if gh repo view "$OWNER/$PAGES_REPO" >/dev/null 2>&1; then
    ( cd "$tmp" && git push -qf "https://github.com/$OWNER/$PAGES_REPO.git" main )
  else
    ( cd "$tmp" && gh repo create "$OWNER/$PAGES_REPO" --public --source . --remote origin --push )
    gh api -X POST "repos/$OWNER/$PAGES_REPO/pages" -f "source[branch]=main" -f "source[path]=/" >/dev/null
  fi
  DASH_URL="https://$OWNER.github.io/$PAGES_REPO/#$FULL"
  echo "✓ Dashboard: $DASH_URL  (first deploy takes 1–2 min)"
fi

cat <<EOF

Last step: create the token the dashboard uses.
  1. Opening https://github.com/settings/personal-access-tokens/new
  2. Name: ioniq-dashboard   Expiration: your choice
  3. Repository access → Only select repositories → $REPO_NAME
  4. Permissions → Actions: Read and write,  Contents: Read-only
  5. Generate, copy it, and paste it into the dashboard's Settings.

Open the dashboard: ${DASH_URL:-open dashboard/index.html in your browser}
Phone: open the same link in Safari → Share → Add to Home Screen.
EOF
open "https://github.com/settings/personal-access-tokens/new" 2>/dev/null || true
