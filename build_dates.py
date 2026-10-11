#!/usr/bin/env python3
# copyright (c) 2026 bill wolf. licensed under the GNU GPL v3.0; see LICENSE.
"""
Build dates.json for zzup.

For every script in the norns community catalog, record:
  added    the date it first appeared in community.json
           (from monome/norns-community's git history)
  updated  the date of the latest commit on its repo's default branch
  commit   the hash of that latest commit

usage:
  build_dates.py --catalog-repo PATH [--previous dates.json] [--out dates.json]

--catalog-repo  a clone of https://github.com/monome/norns-community with
                full commit history (blobless is fine: --filter=blob:none)
--previous      the last dates.json. repos whose latest commit hasn't
                changed reuse its date, so only changed repos are fetched.

Needs only git and the python standard library.
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

CATALOG_FILE = "community.json"
WORKERS = 8           # repos checked in parallel
GIT_TIMEOUT = 60      # seconds per git network call

# never let git stop and ask for a password (private or deleted repos)
GIT_ENV = dict(os.environ, GIT_TERMINAL_PROMPT="0")


def git(args, cwd=None, timeout=GIT_TIMEOUT):
    """run git, returning (ok, stdout)"""
    try:
        r = subprocess.run(["git"] + args, cwd=cwd, env=GIT_ENV,
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, r.stdout
    except subprocess.TimeoutExpired:
        return False, ""


# ---------------------------------------------------------------------------
# added dates, from the catalog's history
# ---------------------------------------------------------------------------

NAME_RE = re.compile(r'"project_name"\s*:\s*"((?:[^"\\]|\\.)*)"')


def names_in(text):
    """project names in one version of community.json.
    parses the json properly; falls back to a regex for the few historical
    versions that weren't valid json."""
    try:
        return [e["project_name"] for e in json.loads(text).get("entries", [])
                if isinstance(e, dict) and "project_name" in e]
    except (ValueError, AttributeError):
        return [json.loads('"%s"' % n) for n in NAME_RE.findall(text)]


def added_dates(repo):
    """name -> date (YYYY-MM-DD) of the first commit containing it"""
    ok, out = git(["log", "--reverse", "--format=%H %cs", "--", CATALOG_FILE],
                  cwd=repo, timeout=600)
    if not ok:
        sys.exit("can't read catalog history in " + repo)
    first = {}
    for line in out.splitlines():
        h, day = line.split()
        ok, text = git(["show", "%s:%s" % (h, CATALOG_FILE)], cwd=repo, timeout=120)
        if not ok:
            continue  # the file was deleted or moved in this commit
        for name in names_in(text):
            first.setdefault(name, day)
    return first


# ---------------------------------------------------------------------------
# latest commits, from each script's repo
# ---------------------------------------------------------------------------

GITHUB_RE = re.compile(r"^https?://github\.com/([^/]+)/([^/#?]+)")


def repo_url(project_url):
    """the git url for a catalog project_url, or None if it isn't a repo.
    catalog links are sometimes to a subfolder (/tree/main), a single file
    (/blob/main/x.lua) or a release zip; all of those still belong to the
    github repo they're in."""
    m = GITHUB_RE.match(project_url or "")
    if m:
        name = re.sub(r"\.git$", "", m.group(2))
        return "https://github.com/%s/%s" % (m.group(1), name)
    if (project_url or "").endswith(".git"):
        return project_url
    return None


def latest_commit(url):
    """(hash, None) for the default branch's latest commit, or (None, reason)"""
    ok, out = git(["ls-remote", url, "HEAD"])
    if not ok or not out.strip():
        return None, "unreachable"
    return out.split()[0], None


def commit_date(url, commit, scratch):
    """the committer date of `commit`, fetching only that commit's metadata"""
    with tempfile.TemporaryDirectory(dir=scratch) as d:
        git(["init", "-q", "--bare"], cwd=d)
        ok, _ = git(["fetch", "-q", "--depth", "1", "--filter=tree:0", url, commit], cwd=d)
        if not ok:
            return None
        ok, out = git(["log", "-1", "--format=%cs", "FETCH_HEAD"], cwd=d)
        return out.strip() if ok and out.strip() else None


# ---------------------------------------------------------------------------
# putting it together
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog-repo", required=True)
    ap.add_argument("--previous")
    ap.add_argument("--out", default="dates.json")
    args = ap.parse_args()

    with open(os.path.join(args.catalog_repo, CATALOG_FILE)) as f:
        entries = [e for e in json.load(f)["entries"]
                   if isinstance(e, dict) and e.get("project_name")]

    prev = {}
    if args.previous and os.path.exists(args.previous):
        with open(args.previous) as f:
            prev = json.load(f).get("scripts", {})

    print("catalog: %d entries" % len(entries))
    added = added_dates(args.catalog_repo)

    scratch = tempfile.mkdtemp(prefix="zzup-")
    problems = []

    def check(e):
        name = e["project_name"]
        rec = {"added": added.get(name)}
        url = repo_url(e.get("project_url"))
        if url is None:
            problems.append((name, "not a git repo: " + str(e.get("project_url"))))
            return name, rec
        commit, why = latest_commit(url)
        if commit is None:
            problems.append((name, why + ": " + url))
            # keep the last known commit, so a temporary outage doesn't
            # wipe the data
            old = prev.get(name, {})
            for k in ("updated", "commit"):
                if old.get(k):
                    rec[k] = old[k]
            return name, rec
        old = prev.get(name, {})
        if old.get("commit") == commit and old.get("updated"):
            day = old["updated"]  # unchanged since last run
        else:
            day = commit_date(url, commit, scratch)
            if day is None:
                problems.append((name, "couldn't read commit date: " + url))
        rec["commit"] = commit
        if day:
            rec["updated"] = day
        return name, rec

    with ThreadPoolExecutor(WORKERS) as pool:
        results = dict(pool.map(check, entries))

    # one script per line keeps the daily git diffs small and readable
    today = datetime.date.today().isoformat()
    lines = ['{', '  "version": 1,', '  "generated": "%s",' % today, '  "scripts": {']
    names = sorted(results, key=str.lower)
    for i, name in enumerate(names):
        rec = {k: results[name][k] for k in ("added", "updated", "commit")
               if results[name].get(k)}
        lines.append("    %s: %s%s" % (json.dumps(name, ensure_ascii=False),
                                       json.dumps(rec, separators=(", ", ": ")),
                                       "," if i < len(names) - 1 else ""))
    lines += ["  }", "}"]
    text = "\n".join(lines) + "\n"
    json.loads(text)  # sanity check before writing

    tmp = args.out + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, args.out)

    dated = sum(1 for r in results.values() if r.get("updated"))
    print("wrote %s: %d scripts, %d with commit dates" % (args.out, len(results), dated))
    for name, msg in sorted(problems):
        print("  problem: %s: %s" % (name, msg))


if __name__ == "__main__":
    main()
