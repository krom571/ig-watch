"""
Instagram profile watcher - runs once per GitHub Actions job (every ~5 min).
Usernames and ntfy topic come from repo secrets, so they never appear in the
public code or logs (logs only say "profile 1", "profile 2").
"""

import json
import os
import random
import time

import requests

USERNAMES = [u.strip().lstrip("@") for u in os.environ["IG_USERNAMES"].split(",") if u.strip()]
TOPIC = os.environ["NTFY_TOPIC"].strip()
STATE_FILE = "state/state.json"
BLOCKED_WARN_AFTER = 6  # ~30 min of failed checks -> one warning

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "x-ig-app-id": "936619743392459",
}


def check(username):
    """Return 'active', 'off', or 'unknown' (blocked / rate-limited / network)."""
    url = f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
    except requests.RequestException:
        return "unknown", "network error"
    if r.status_code == 200:
        try:
            user = r.json().get("data", {}).get("user")
        except ValueError:
            return "unknown", "bad response"
        return ("active" if user else "off"), "200"
    if r.status_code == 404:
        return "off", "404"
    return "unknown", f"HTTP {r.status_code}"


def notify(title, message, tag, click=None, priority="high"):
    headers = {"Title": title, "Tags": tag, "Priority": priority}
    if click:
        headers["Click"] = click
    try:
        requests.post(f"https://ntfy.sh/{TOPIC}", data=message.encode("utf-8"),
                      headers=headers, timeout=15)
    except requests.RequestException:
        print("notification failed")


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {"status": {}, "unknown_streak": 0, "warned": False}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def main():
    state = load_state()
    any_success = False

    for i, u in enumerate(USERNAMES, start=1):
        status, detail = check(u)
        print(f"profile {i}: {status} ({detail})")

        if status != "unknown":
            any_success = True
            prev = state["status"].get(u)
            if status != prev:
                if status == "active":
                    notify(f"@{u} is ON", "Profile is available now",
                           "green_circle", click=f"https://instagram.com/{u}")
                elif prev is not None:
                    notify(f"@{u} is OFF", "Profile is disabled or unavailable", "red_circle")
                state["status"][u] = status

        time.sleep(random.uniform(2, 5))

    if any_success:
        if state.get("warned"):
            notify("IG watcher working again", "Checks are succeeding again", "white_check_mark",
                   priority="default")
        state["unknown_streak"] = 0
        state["warned"] = False
    else:
        state["unknown_streak"] = state.get("unknown_streak", 0) + 1
        if state["unknown_streak"] >= BLOCKED_WARN_AFTER and not state.get("warned"):
            notify("IG watcher can't check", "Instagram is blocking the checks right now",
                   "warning", priority="default")
            state["warned"] = True

    save_state(state)


if __name__ == "__main__":
    main()
