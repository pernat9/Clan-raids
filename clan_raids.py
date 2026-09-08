#!/usr/bin/env python3
"""
Destiny 2 clan raid counter.

Counts raid completions where at least MIN_CLAN_MEMBERS members of your clan
were in the fireteam together.

How it works: a raid instance has one instance ID shared by everyone in the
fireteam. Pull every clan member's raid history, then count how many members'
histories each instance ID appears in. No fireteam lookups needed.

Usage:
    export BUNGIE_API_KEY=your_key_here
    python clan_raids.py

Outputs index.html in this directory.
"""

import json
import os
import sys
import time
from collections import defaultdict
from itertools import combinations
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import requests

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------

BUNGIE_NAME = "Peppy#4787"   # used only to find which clan to pull

# How many clan members must be in the fireteam for it to count as a clan raid.
# 2 = you plus one clanmate. Bump to 3 if you want a stricter definition.
MIN_CLAN_MEMBERS = 3

# Only count runs that were actually completed (vs. wipes and bailouts).
COMPLETED_ONLY = True

# Pantheon is a boss-rush event, not a raid, but Bungie files it under the same
# activity mode. Set False to count it.
EXCLUDE_PANTHEON = True
EXCLUDED_HASHES = set()

API_KEY = os.environ.get("BUNGIE_API_KEY")
BASE = "https://www.bungie.net/Platform"
CACHE = Path(__file__).parent / "cache"
OUT = Path(__file__).parent / "index.html"
PAGE_URL = os.environ.get("PAGE_URL", "")

RAID_MODE = 4          # DestinyActivityModeType.Raid (dungeons are 82)
PAGE_SIZE = 250
MAX_PAGES = 40        # Bungie stops serving history past a certain depth
MAX_WORKERS = 5        # be polite; Bungie throttles aggressively above this

session = requests.Session()


# ----------------------------------------------------------------------------
# API plumbing
# ----------------------------------------------------------------------------

class BungieError(Exception):
    pass


def api(path, params=None, retries=4):
    """GET a Bungie endpoint, unwrap the Response envelope, retry on throttle."""
    url = f"{BASE}{path}"
    headers = {"X-API-Key": API_KEY}
    for attempt in range(retries):
        try:
            r = session.get(url, headers=headers, params=params, timeout=30)
        except requests.RequestException as e:
            if attempt == retries - 1:
                raise BungieError(f"network error on {path}: {e}")
            time.sleep(2 ** attempt)
            continue

        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(2 ** attempt + 1)
            continue

        try:
            body = r.json()
        except ValueError:
            raise BungieError(f"non-JSON response from {path} ({r.status_code})")

        code = body.get("ErrorCode")
        if code == 1:
            return body.get("Response")
        if code in (1665, 1618, 1672):
            # PrivacyRestriction / account not found / profile hidden
            raise BungieError(f"private:{body.get('ErrorStatus')}")
        if code == 51:  # PerEndpointRequestThrottleExceeded
            time.sleep(2 ** attempt + 1)
            continue
        raise BungieError(f"{body.get('ErrorStatus')} on {path}")

    raise BungieError(f"gave up on {path}")


def cached(name, fn):
    """Disk-cache a JSON blob so re-runs don't re-download everything."""
    CACHE.mkdir(exist_ok=True)
    f = CACHE / f"{name}.json"
    if f.exists():
        return json.loads(f.read_text())
    data = fn()
    f.write_text(json.dumps(data))
    return data


# ----------------------------------------------------------------------------
# Steps
# ----------------------------------------------------------------------------

def find_player(bungie_name):
    name, code = bungie_name.rsplit("#", 1)
    r = session.post(
        f"{BASE}/Destiny2/SearchDestinyPlayerByBungieName/-1/",
        headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
        json={"displayName": name, "displayNameCode": int(code)},
        timeout=30,
    )
    results = r.json().get("Response") or []
    if not results:
        sys.exit(f"Couldn't find {bungie_name}. Check the name and code.")
    # Prefer the cross-save primary if flagged, else first result
    for m in results:
        if m.get("crossSaveOverride") in (0, m.get("membershipType")):
            return m
    return results[0]


def find_clan(membership_type, membership_id):
    groups = api(f"/GroupV2/User/{membership_type}/{membership_id}/0/1/")
    results = groups.get("results") or []
    if not results:
        sys.exit("That account isn't in a clan.")
    g = results[0]["group"]
    return g["groupId"], g["name"]


def get_roster(group_id):
    members, page = [], 1
    while True:
        resp = api(f"/GroupV2/{group_id}/Members/", {"currentpage": page})
        batch = resp.get("results") or []
        members.extend(batch)
        if not resp.get("hasMore"):
            break
        page += 1
    out = []
    for m in members:
        d = m["destinyUserInfo"]
        name = d.get("bungieGlobalDisplayName") or d.get("displayName") or "?"
        code = d.get("bungieGlobalDisplayNameCode")
        out.append({
            "membershipId": d["membershipId"],
            "membershipType": d["membershipType"],
            "name": f"{name}#{code:04d}" if code else name,
        })
    return out


def get_characters(member):
    resp = api(
        f"/Destiny2/{member['membershipType']}/Profile/{member['membershipId']}/",
        {"components": "200"},
    )
    return list((resp.get("characters", {}).get("data") or {}).keys())


def get_raid_history(member):
    """Every raid instance this member has a record of, across all characters."""
    activities, truncated = [], []
    for char_id in get_characters(member):
        page = 0
        while True:
            try:
                resp = api(
                    f"/Destiny2/{member['membershipType']}/Account/"
                    f"{member['membershipId']}/Character/{char_id}/Stats/Activities/",
                    {"mode": RAID_MODE, "count": PAGE_SIZE, "page": page},
                )
            except BungieError as e:
                if str(e).startswith("private:"):
                    raise
                break
            batch = (resp or {}).get("activities") or []
            if not batch:
                break
            activities.extend(batch)
            if len(batch) < PAGE_SIZE:
                break
            page += 1
            if page > MAX_PAGES:
                truncated.append(char_id)
                break
    return activities


def fetch_member(member):
    try:
        raw = cached(f"hist_{member['membershipId']}",
                     lambda: get_raid_history(member))
        status = "ok"
    except BungieError as e:
        raw, status = [], ("private" if str(e).startswith("private:") else "error")

    runs = {}
    for a in raw:
        vals = a.get("values", {})
        completed = vals.get("completed", {}).get("basic", {}).get("value", 0)
        reason = vals.get("completionReason", {}).get("basic", {}).get("value", 0)
        # completionReason 0 = objective completed. Anything else (wipe-out,
        # timeout, joined-too-late) can still carry completed==1.
        if COMPLETED_ONLY and (completed != 1 or reason != 0):
            continue
        details = a.get("activityDetails", {})
        if details.get("directorActivityHash") in EXCLUDED_HASHES:
            continue
        runs[details.get("instanceId")] = {
            "hash": details.get("directorActivityHash"),
            "date": a.get("period"),
        }
    return member, runs, status


def get_activity_names():
    """Map activity hashes to readable raid names via the manifest."""
    try:
        manifest = api("/Destiny2/Manifest/")
        path = manifest["jsonWorldComponentContentPaths"]["en"]["DestinyActivityDefinition"]
        defs = cached("activity_defs", lambda: session.get(
            f"https://www.bungie.net{path}", timeout=120).json())
        names = {}
        for h, d in defs.items():
            n = (d.get("displayProperties", {}) or {}).get("name")
            if n:
                names[int(h)] = n
        return names
    except Exception:
        return {}


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main():
    if not API_KEY:
        sys.exit("Set BUNGIE_API_KEY first:  export BUNGIE_API_KEY=your_key")

    print(f"Looking up {BUNGIE_NAME}...")
    player = find_player(BUNGIE_NAME)
    group_id, clan_name = find_clan(player["membershipType"], player["membershipId"])
    print(f"Clan: {clan_name} ({group_id})")

    roster = get_roster(group_id)

    global EXCLUDED_HASHES
    names = get_activity_names()
    if EXCLUDE_PANTHEON:
        EXCLUDED_HASHES = {h for h, n in names.items() if "pantheon" in n.lower()}
        print(f"Excluding {len(EXCLUDED_HASHES)} Pantheon activities (not raids).")

    print(f"{len(roster)} members. Pulling raid history (cached after first run)...")

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for i, out in enumerate(pool.map(fetch_member, roster), 1):
            results.append(out)
            member, runs, status = out
            flag = "" if status == "ok" else f"  [{status}]"
            print(f"  {i}/{len(roster)}  {member['name']}: {len(runs)} raids{flag}")

    # instance id -> members present
    instances = defaultdict(list)
    meta = {}
    for member, runs, status in results:
        for iid, info in runs.items():
            instances[iid].append(member["membershipId"])
            meta[iid] = info

    clan_instances = {i: m for i, m in instances.items()
                      if len(m) >= MIN_CLAN_MEMBERS}

    sizes = defaultdict(int)
    for m in instances.values():
        sizes[len(m)] += 1
    print("\nFireteam breakdown (clanmates present per raid instance):")
    for n in sorted(sizes):
        label = "solo / no clanmates" if n == 1 else f"{n} clan members"
        print(f"  {label:<22} {sizes[n]:>6} instances")
    print(f"\n{len(clan_instances)} clan raids "
          f"({MIN_CLAN_MEMBERS}+ clanmates in the fireteam).")

    big = [r for r in results if len(r[1]) >= 990]
    if big:
        print("\nWarning: history looks truncated by Bungie for: "
              + ", ".join(r[0]["name"] for r in big))

    # Every pair who cleared a raid together, and how many times. This is the
    # graph the map is drawn from.
    pair_counts = defaultdict(int)
    for present in clan_instances.values():
        for a, b in combinations(sorted(set(present)), 2):
            pair_counts[(a, b)] += 1

    by_member = defaultdict(lambda: {"count": 0, "raids": defaultdict(int),
                                     "partners": defaultdict(int), "last": None})
    for iid, present in clan_instances.items():
        raid_name = names.get(meta[iid]["hash"], "Unknown raid")
        date = meta[iid]["date"]
        for mid in present:
            e = by_member[mid]
            e["count"] += 1
            e["raids"][raid_name] += 1
            if not e["last"] or date > e["last"]:
                e["last"] = date
            for other in present:
                if other != mid:
                    e["partners"][other] += 1

    lookup = {m["membershipId"]: m["name"] for m in roster}
    rows = []
    for member, runs, status in results:
        mid = member["membershipId"]
        e = by_member.get(mid)
        if not e:
            rows.append({"name": member["name"], "count": 0, "total": len(runs),
                         "top_raid": "—", "partner": "—", "last": "—",
                         "status": status})
            continue
        top_raid = max(e["raids"].items(), key=lambda x: x[1])[0]
        partner = max(e["partners"].items(), key=lambda x: x[1])
        partner_name = lookup.get(partner[0], "?")
        rows.append({
            "name": member["name"],
            "count": e["count"],
            "total": len(runs),
            "top_raid": top_raid,
            "partner": f"{partner_name} ({partner[1]})",
            "partner_name": partner_name,
            "partner_count": partner[1],
            "last": (e["last"] or "")[:10],
            "status": status,
        })
    rows.sort(key=lambda r: -r["count"])

    who = {m["membershipId"]: m["name"] for m in roster}
    pairs = [(who[a], who[b], w) for (a, b), w in pair_counts.items()
             if a in who and b in who]
    write_html(rows, clan_name, len(clan_instances), pairs)
    print(f"Wrote {OUT}")


def write_html(rows, clan_name, total, pairs=()):
    from render import render
    OUT.write_text(
        render(rows, clan_name, total, MIN_CLAN_MEMBERS, PAGE_URL, pairs),
        encoding="utf-8")


if __name__ == "__main__":
    main()
