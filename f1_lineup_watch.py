#!/usr/bin/env python3
"""
F1 lineup watcher.

Race day only. After every Grand Prix it compares each team's drivers against
the previous Grand Prix and sends one notification: "lineup is the same" or
the list of replacements. Practice, qualifying and sprint sessions are ignored.

Data: OpenF1 (https://openf1.org), free, no API key for historical data.
Notifications: Slack incoming webhook (SLACK_WEBHOOK_URL); otherwise printed.
State: state.json (processed sessions + last race lineup).
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = "https://api.openf1.org/v1"
STATE_FILE = Path(os.environ.get("STATE_FILE", "state.json"))
SLACK_WEBHOOK = os.environ.get("SLACK_WEBHOOK_URL", "")
# Wait this long after a session ends before reading it (data needs to settle,
# and OpenF1 limits unauthenticated access while a session is live).
SETTLE = timedelta(minutes=int(os.environ.get("SETTLE_MINUTES", "45")))
WATCHED = {"Race"}  # Grand Prix only (sprints are named "Sprint")


# ---------------------------------------------------------------- API helpers
def get(path, **params):
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                data = json.load(r)
                return data if isinstance(data, list) else []
        except urllib.error.HTTPError as e:
            if e.code == 404:  # OpenF1 returns 404 for "no results"
                return []
            if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(5 * (attempt + 1))
                continue
            raise
    return []


def lineup(session_key):
    """{team_name: {driver_name: driver_number}} for one session."""
    teams = {}
    for d in get("drivers", session_key=session_key):
        team = d.get("team_name") or "Unknown team"
        name = (d.get("full_name") or d.get("broadcast_name")
                or str(d.get("driver_number"))).title()
        teams.setdefault(team, {})[name] = d.get("driver_number")
    return teams


def diff(base, cur):
    """List of human-readable changes per team (compared by driver name)."""
    changes = []
    for team in sorted(set(base) | set(cur)):
        b, c = set(base.get(team, {})), set(cur.get(team, {}))
        if team not in base:
            changes.append(f"• *{team}* (new team): {', '.join(sorted(c))}")
        elif team not in cur:
            changes.append(f"• *{team}*: not on the entry list")
        elif b != c:
            out = ", ".join(sorted(b - c)) or "—"
            inn = ", ".join(sorted(c - b)) or "—"
            changes.append(f"• *{team}*: {out} → {inn}")
    return changes


def ended(s, now):
    return datetime.fromisoformat(s["date_end"]) + SETTLE < now


# ---------------------------------------------------------------- notify/state
def notify(text):
    print(text, "\n")
    if not SLACK_WEBHOOK:
        return
    req = urllib.request.Request(
        SLACK_WEBHOOK,
        data=json.dumps({"text": text}).encode(),
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=30)


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"processed": [], "baseline": None, "baseline_from": None}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True))


# ---------------------------------------------------------------- main
def seed_baseline(state, year, now):
    """First run: use the latest finished race as the reference lineup."""
    for y in (year, year - 1):
        races = [s for s in get("sessions", year=y, session_name="Race")
                 if ended(s, now)]
        races.sort(key=lambda s: s["date_start"])
        for race in reversed(races):
            lu = lineup(race["session_key"])
            if lu:
                meetings = {m["meeting_key"]: m.get("meeting_name")
                            for m in get("meetings", year=y)}
                state["baseline"] = lu
                state["baseline_from"] = (
                    meetings.get(race["meeting_key"]) or race.get("location"))
                return True
    return False


def main():
    now = datetime.now(timezone.utc)
    year = int(os.environ.get("SEASON", now.year))
    state = load_state()

    sessions = [s for s in get("sessions", year=year, session_name="Race")
                if s.get("session_name") in WATCHED]
    sessions.sort(key=lambda s: s["date_start"])
    done = [s for s in sessions if ended(s, now)]
    meetings = {m["meeting_key"]: m.get("meeting_name") or m.get("location")
                for m in get("meetings", year=year)}

    if state["baseline"] is None:
        if not seed_baseline(state, year, now):
            print("No finished race found yet; will try again next run.")
            return
        # Don't replay history: mark everything already finished as handled.
        state["processed"] = [s["session_key"] for s in done]
        save_state(state)
        notify(f"🏁 F1 lineup watcher is running. Reference lineup: "
               f"*{state['baseline_from']}*.")
        return

    processed = set(state["processed"])
    for s in done:
        key = s["session_key"]
        if key in processed:
            continue
        cur = lineup(key)
        if not cur:
            print(f"No driver data yet for session {key}; retrying next run.")
            continue

        gp = meetings.get(s["meeting_key"]) or s.get("location", "Grand Prix")
        ref = state["baseline_from"]
        changes = diff(state["baseline"], cur)
        if changes:
            notify(f"🔁 *{gp}* — driver change(s) vs {ref}:\n"
                   + "\n".join(changes))
        else:
            notify(f"✅ *{gp}* — same lineup as {ref}.")
        state["baseline"], state["baseline_from"] = cur, gp

        processed.add(key)
        state["processed"] = sorted(processed)
        save_state(state)


if __name__ == "__main__":
    main()
