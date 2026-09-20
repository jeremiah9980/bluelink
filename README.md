# Ioniq 5 Bluelink remote (GitHub Actions + dashboard)

Controls a US Hyundai Ioniq 5 through Bluelink. Commands run as GitHub Actions workflows in a **private**
repo that holds your Bluelink login as encrypted secrets. The dashboard is a static page that
starts those workflows through the GitHub API and reads back the results.

```
dashboard (phone/Mac) ──GitHub API──> command.yml / status.yml ──Bluelink API──> car
        ▲                                         │
        └──────── reads status branch ◄───────────┘  (status.json, history.jsonl, last_command.json)
```

## Setup (Mac, one time)
```bash
cd ioniq-bluelink
./setup.sh            # creates private repo, prompts for Bluelink email/password/PIN, publishes dashboard
```
Then create a fine-grained token (the script opens the page): access to **only** `ioniq-bluelink`,
**Actions: Read and write**, **Contents: Read-only**. Paste it into the dashboard's Settings.

## What runs when
| Workflow | Trigger | Touches the car? |
|---|---|---|
| `status` | every hour at :17, or "Update status" | No. Reads Hyundai's last saved data |
| `command` | dashboard buttons, or Actions tab → command → Run workflow | Yes |

## Without the dashboard
From a phone or computer, open github.com → your repo → **Actions** → **command** → **Run workflow**, then pick the action.
From Terminal: `gh workflow run command.yml -R OWNER/ioniq-bluelink -f action=climate_start -f temp=72`

## Notes
- Uses the community library `hyundai_kia_connect_api` (the same one Home Assistant uses). Bluelink has
  no official public API, so Hyundai can change or block it at any time.
- If Hyundai blocks logins from GitHub's cloud servers, add a self-hosted runner on your Mac
  (repo → Settings → Actions → Runners) and change `runs-on: ubuntu-latest` to `runs-on: self-hosted`.
- Scheduled checks use about 1 Actions minute each (roughly 720 of the 2,000 free minutes a month on private repos).
  GitHub pauses scheduled workflows after 60 days with no repo activity. Re-enable them in the Actions tab.
- Anyone with your dashboard token can unlock the car. Keep it scoped to this one repo and revoke it if a device is lost.
- Test mode: `gh variable set BLUELINK_MOCK -R OWNER/ioniq-bluelink --body 1` (fake data, no Hyundai login).
