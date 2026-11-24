# F1 lineup watch

Checks every F1 race weekend and posts to Slack whether each team's drivers
are the same as the previous race or someone was replaced.

## Setup (about 5 minutes)
1. Create a new GitHub repo and add these files (keep the `.github/workflows` folder).
2. In Slack, create an Incoming Webhook for the channel you want alerts in.
3. In the repo: Settings → Secrets and variables → Actions → New secret
   `SLACK_WEBHOOK_URL` = your webhook URL.
4. Actions tab → "F1 lineup watch" → Run workflow. You should get a
   "watcher is running" message in Slack.

## What you'll get
One Slack message per Grand Prix, after the race: "same lineup as [last GP]"
or the list of replacements per team. Practice, qualifying and sprints are skipped.

## Notes
- Runs every 2 hours on Saturdays, Sundays and Mondays (UTC); the alert lands
  roughly 1–3 hours after the race ends.
- GitHub pauses scheduled workflows after 60 days without repo activity, so
  re-enable it in the Actions tab before the new season if it went quiet over
  the winter break.
- Local test: `python f1_lineup_watch.py` (prints instead of posting when
  `SLACK_WEBHOOK_URL` isn't set).
