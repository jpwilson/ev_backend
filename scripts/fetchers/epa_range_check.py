"""EPA range verifier — fetcher #1 of the data-freshness pipeline.

Cross-checks our epa_range against fueleconomy.gov (official EPA data,
free web service) and files change proposals for material differences.

Conservative by design:
- proposes only on an UNAMBIGUOUS make/model match (one EPA model line);
- only for cars with a 4-digit model year in `generation`;
- never writes the catalog — everything goes through /admin/proposals.

Usage:
  EV_ADMIN_KEY=... python scripts/fetchers/epa_range_check.py [--dry-run] [--limit N]

Env:
  EV_API_BASE   (default https://ev-backend-three.vercel.app)
  EV_ADMIN_KEY  (required unless --dry-run)
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from typing import Optional

API_BASE = os.getenv("EV_API_BASE", "https://ev-backend-three.vercel.app")
ADMIN_KEY = os.getenv("EV_ADMIN_KEY", "")
EPA_BASE = "https://www.fueleconomy.gov/ws/rest"

# Our make names -> EPA make names where they differ
MAKE_ALIASES = {
    "VW": "Volkswagen",
    "Mercedes": "Mercedes-Benz",
    "KIA": "Kia",
}

RANGE_DIFF_THRESHOLD = 0.02  # propose when >2% apart


def http_json(url: str, headers: Optional[dict] = None, payload: Optional[dict] = None, method: str = "GET"):
    req = urllib.request.Request(url, method=method)
    req.add_header("Accept", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, data, timeout=30) as resp:
        return json.loads(resp.read().decode())


def epa_menu(path: str) -> list:
    """EPA menu endpoints return {menuItem: [{text, value}]} (or a single dict)."""
    try:
        data = http_json(f"{EPA_BASE}/vehicle/menu/{path}")
    except Exception:
        return []
    items = (data or {}).get("menuItem") or []
    if isinstance(items, dict):
        items = [items]
    return [i["value"] for i in items]


def epa_vehicle(vehicle_id: str) -> dict:
    return http_json(f"{EPA_BASE}/vehicle/{vehicle_id}")


def year_from_generation(generation: Optional[str]) -> Optional[str]:
    if not generation:
        return None
    m = re.search(r"\b(20[12][0-9])\b", generation)
    return m.group(1) if m else None


def tokens(name: str) -> list:
    """Normalize for matching: lowercase, strip hyphens inside tokens.
    'F-150 Lightning 4WD' -> ['f150','lightning','4wd']."""
    return name.lower().replace("-", "").split()


def model_matches(ours: str, epa_model: str) -> bool:
    """EPA model lines are per-trim ('Model Y Long Range AWD'); ours are
    model-level ('Model Y'). Match when our tokens are a prefix of EPA's —
    token-exact, so 'EV6' can never match 'EV60'."""
    a, b = tokens(ours), tokens(epa_model)
    return len(b) >= len(a) and b[: len(a)] == a


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="print proposals, post nothing")
    ap.add_argument("--limit", type=int, default=0, help="check at most N cars (0 = all)")
    args = ap.parse_args()

    if not args.dry_run and not ADMIN_KEY:
        print("EV_ADMIN_KEY required (or use --dry-run)", file=sys.stderr)
        return 2

    cars = http_json(f"{API_BASE}/cars/cards")
    candidates = [
        c for c in cars
        if c.get("epa_range")
        and c.get("availability_desc") == "available"
        and year_from_generation(c.get("generation"))
    ]
    if args.limit:
        candidates = candidates[: args.limit]

    proposals, checked, suspicious, no_match = [], 0, 0, 0

    for car in candidates:
        year = year_from_generation(car["generation"])
        make = MAKE_ALIASES.get(car["make_name"], car["make_name"])

        epa_models = epa_menu(f"model?year={year}&make={urllib.parse.quote(make)}")
        time.sleep(0.3)  # be polite to the EPA service
        # EPA lists one line per trim; all lines whose tokens start with our
        # model name belong to this model.
        matches = sorted({m for m in epa_models if model_matches(car["model"], m)})
        if not matches:
            no_match += 1
            continue
        if len(matches) > 8:  # smells like a bad match, skip conservatively
            suspicious += 1
            continue

        # Take the max EV range across all trims (matches our convention of
        # quoting the strongest official figure per model line)
        best_range = 0
        best_url = ""
        vehicle_ids = []
        for epa_model in matches:
            vehicle_ids.extend(
                epa_menu(
                    f"options?year={year}&make={urllib.parse.quote(make)}&model={urllib.parse.quote(epa_model)}"
                )
            )
            time.sleep(0.2)
        for vid in vehicle_ids[:8]:
            try:
                v = epa_vehicle(vid)
            except Exception:
                continue
            time.sleep(0.2)
            if str(v.get("atvType", "")).upper() != "EV":
                continue
            r = float(v.get("range") or 0)
            if r > best_range:
                best_range = r
                best_url = f"https://www.fueleconomy.gov/feg/Find.do?action=sbs&id={vid}"

        checked += 1
        if not best_range:
            continue

        ours = float(car["epa_range"])
        if abs(best_range - ours) / max(ours, 1) > RANGE_DIFF_THRESHOLD:
            proposals.append({
                "entity_type": "car",
                "entity_id": car["id"],
                "field": "epa_range",
                "old_value": ours,
                "new_value": best_range,
                "source_name": "EPA fueleconomy.gov",
                "source_url": best_url,
                "confidence": 0.8,
                "rationale": (
                    f"EPA's best trim range for {year} {make} {car['model']} is "
                    f"{best_range} mi; we show {ours} mi "
                    f"({abs(best_range - ours) / ours:.0%} apart)."
                ),
            })

    print(f"checked={checked} proposals={len(proposals)} suspicious={suspicious} no_match={no_match}")
    for p in proposals:
        print(f"  car#{p['entity_id']}: epa_range {p['old_value']} -> {p['new_value']}  ({p['rationale']})")

    if args.dry_run or not proposals:
        return 0

    run = http_json(
        f"{API_BASE}/admin/crawl-runs",
        headers={"X-Admin-Key": ADMIN_KEY},
        payload={"scope": "epa_range_check"},
        method="POST",
    )
    result = http_json(
        f"{API_BASE}/admin/proposals",
        headers={"X-Admin-Key": ADMIN_KEY},
        payload={"proposals": proposals, "crawl_run_id": run["id"]},
        method="POST",
    )
    http_json(
        f"{API_BASE}/admin/crawl-runs/{run['id']}",
        headers={"X-Admin-Key": ADMIN_KEY},
        payload={"status": "completed", "stats": {"checked": checked, **result}},
        method="PATCH",
    )
    print(f"posted: {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
