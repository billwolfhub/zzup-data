# zzup-data

Dates for the norns community catalog, used by [zzup](https://github.com/billwolfhub/zzup).

`dates.json` records, for every script in the [norns community catalog](https://github.com/monome/norns-community):

- **added**: the date it first appeared in the catalog, from the catalog's git history
- **updated**: the date of the latest commit on its repo's default branch
- **commit**: the hash of that latest commit, which lets zzup tell whether an installed script has an update available

A GitHub Action rebuilds it daily and commits only when something changed.

## format

```json
{
  "version": 1,
  "generated": "2026-10-11",
  "scripts": {
    "awake": {"added": "2019-10-21", "updated": "2026-04-30", "commit": "19c68fef…"}
  }
}
```

- Scripts are keyed by their catalog `project_name`.
- `generated` is the date the data last changed.
- `updated` and `commit` are missing when a script's repo can't be reached. If a repo becomes unreachable later, its last known values are kept.

## notes on the data

- **The 2019 bulk import:** 57 scripts were added to the catalog on 2019-10-21, when the original scripts moved into it. For those, "added" means 2019 or earlier.
- **"Added" means added to the catalog:** this is usually close to when a script was first published, but not always.
- **Renames:** a renamed catalog entry is dated from its rename.
- **Commits, not releases:** "updated" counts any commit, including README edits.

## running it yourself

`build_dates.py` needs only git and Python 3:

```
git clone --filter=blob:none https://github.com/monome/norns-community catalog
python3 build_dates.py --catalog-repo catalog --previous dates.json --out dates.json
```

A full build takes about a minute; with `--previous`, only repos with new commits are fetched.

To host your own copy, fork this repo, enable Actions on the fork, and point zzup's data URL setting at your fork's `dates.json`.

## license

GPL-3.0, the same license as norns itself. See [LICENSE](LICENSE). The dates are derived from the public [norns community catalog](https://github.com/monome/norns-community) and the public repos it lists.
