"""
Builds data/clusters.json for the public cluster page.

Reads the Plume data table in Airtable (read-only), finds landfills where
Carbon Mapper detected 2+ plumes in the same satellite pass (same Scene ID +
same Landfill Link), and writes ONLY public fields. No subscriber data is read.

Runs in GitHub Actions. Needs the secret AIRTABLE_TOKEN (read-only token,
scoped to this base, data.records:read).
"""
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

import requests

BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "appk5Pi5OJRT6VtTv")
TABLE = os.environ.get("PLUME_TABLE", "Plume data")
TOKEN = os.environ.get("AIRTABLE_TOKEN")
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "clusters.json")

# Field names in Plume data. Scripts find fields by name, so keep these in
# sync if a field is ever renamed.
REQUIRED = {
    "name": "Name",
    "scene": "Scene ID",
    "landfill_link": "Landfill Link",
    "landfill_name": "Landfill Name (from Landfill Link)",
    "rate": "Emissions Auto",
    "uncertainty": "emission_uncertainty_auto",
    "datetime": "datetime",
    "published": "published_at",
}
OPTIONAL = {
    "state": "State Name String",
    "state_lookup": "state name",
    "platform": "platform",
    "plume_png": "plume_png",
    "plume_map": "Plume Map URL",
    "cluster_map": "Cluster Map URL",
    "wit_url": "WIT URL",
    "owner": "Landfill Owner Organization(s) (from Landfill Link)",
}

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


def first(v):
    """Lookup fields come back as lists; return the first value as text."""
    if isinstance(v, list):
        v = v[0] if v else ""
    if isinstance(v, dict):  # some lookups return {"name": ...}
        v = v.get("name") or v.get("url") or ""
    return "" if v is None else str(v).strip()


def num(v):
    v = first(v).replace(",", "")
    try:
        return float(v)
    except ValueError:
        return 0.0


def day(v):
    """'2026-10-19 17:45:37' or ISO -> '2026-10-19'."""
    m = re.match(r"(\d{4}-\d{2}-\d{2})", first(v))
    return m.group(1) if m else ""


def fetch_all():
    if not TOKEN:
        sys.exit("AIRTABLE_TOKEN is not set. Add it under Settings > Secrets and variables > Actions.")
    fields = dict(REQUIRED, **OPTIONAL)
    url = f"https://api.airtable.com/v0/{BASE_ID}/{requests.utils.quote(TABLE)}"
    headers = {"Authorization": f"Bearer {TOKEN}"}
    while True:  # retry loop that drops optional fields Airtable doesn't know
        params = [("pageSize", "100"),
                  ("filterByFormula", "AND({Scene ID}!='', {Landfill Link}!='')")]
        params += [("fields[]", f) for f in fields.values()]
        records, offset, missing = [], None, None
        while True:
            p = params + ([("offset", offset)] if offset else [])
            r = requests.get(url, headers=headers, params=p, timeout=60)
            if r.status_code == 429:
                time.sleep(30)
                continue
            if r.status_code == 422 and "UNKNOWN_FIELD_NAME" in r.text:
                m = re.search(r'Unknown field name: \\?"(.+?)\\?"', r.text)
                missing = m.group(1) if m else None
                break
            if r.status_code != 200:
                sys.exit(f"Airtable error {r.status_code}: {r.text[:300]}")
            data = r.json()
            records += data.get("records", [])
            offset = data.get("offset")
            if not offset:
                return records, fields
            time.sleep(0.25)
        key = next((k for k, v in fields.items() if v == missing), None)
        if key in OPTIONAL:
            print(f"Note: optional field '{missing}' not found in Airtable; continuing without it.")
            fields.pop(key)
            continue
        sys.exit(f"Required field '{missing}' not found in {TABLE}. Check the field name in REQUIRED.")


def build(records, fields):
    get = lambda rec, key: rec["fields"].get(fields[key]) if key in fields else None
    seen, groups = set(), defaultdict(list)
    for rec in records:
        name = first(get(rec, "name"))
        links = get(rec, "landfill_link") or []
        landfill_id = links[0] if links and isinstance(links[0], str) else first(links)
        if not name or name in seen or not landfill_id:
            continue
        seen.add(name)
        groups[(first(get(rec, "scene")), landfill_id)].append(rec)

    months = defaultdict(list)
    for (scene, _), recs in groups.items():
        if len(recs) < 2:
            continue
        recs.sort(key=lambda r: first(get(r, "name")))
        plumes = []
        for r in recs:
            rate = num(get(r, "rate"))
            plumes.append({
                "id": first(get(r, "name")),
                "rate": round(rate, 1) if rate > 0 else None,
                "uncertainty": round(num(get(r, "uncertainty")), 1) if rate > 0 else None,
                "published": day(get(r, "published")),
                "portal": f"https://data.carbonmapper.org/?plume_id={first(get(r, 'name'))}",
            })
        # A group becomes a cluster when its second plume is published.
        pub_dates = sorted(p["published"] for p in plumes if p["published"])
        if len(pub_dates) < 2:
            continue
        became_cluster = pub_dates[1]
        lead = max(recs, key=lambda r: num(get(r, "rate")))
        state = first(get(lead, "state")) or first(get(lead, "state_lookup"))
        image = ""
        for key in ("cluster_map", "plume_map", "plume_png"):
            image = next((first(get(r, key)) for r in [lead] + recs if first(get(r, key))), "")
            if image:
                break
        months[became_cluster[:7]].append({
            "scene": scene,
            "landfill": first(get(lead, "landfill_name")),
            "state": state,
            "owner": first(get(lead, "owner")),
            "wit_url": first(get(lead, "wit_url")),
            "observed": day(get(lead, "datetime")),
            "platform": first(get(lead, "platform")),
            "image": image,
            "image_is_cluster_map": bool(first(get(lead, "cluster_map"))),
            "plume_count": len(plumes),
            "largest_rate": max([p["rate"] or 0 for p in plumes]),
            "plumes": plumes,
        })

    out = []
    for month in sorted(months, reverse=True):
        clusters = sorted(months[month], key=lambda c: (-c["plume_count"], -c["largest_rate"], c["landfill"]))
        y, m = month.split("-")
        out.append({
            "month": month,
            "label": f"{MONTHS[int(m) - 1]} {y}",
            "summary": {
                "clusters": len(clusters),
                "plumes": sum(c["plume_count"] for c in clusters),
                "states": len({c["state"] for c in clusters if c["state"]}),
            },
            "clusters": clusters,
        })
    return out


def main():
    records, fields = fetch_all()
    months = build(records, fields)
    print(f"Read {len(records)} plume records; found "
          f"{sum(m['summary']['clusters'] for m in months)} clusters across {len(months)} months.")
    try:
        with open(OUT, encoding="utf-8") as f:
            old = json.load(f)
        if old.get("months") == months:
            print("No changes since last run; leaving the file as it is.")
            return
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "months": months},
                  f, ensure_ascii=False, indent=1)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
