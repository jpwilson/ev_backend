# Catalog seed data

One JSON file per make: `{make_slug}.json`. These files are the source of truth for the catalog
(`makes → models → generations → variants → offerings`); a loader upserts them into the catalog tables.
Files whose names start with `_` (for example `_example.json`) are format examples and are never loaded.

## Format

Plain JSON (the comments below are explanation only; real files must not contain them).
Any field you cannot source is `null`; arrays may be empty; do not add fields that are not listed.

```jsonc
{
  "make": {
    "slug": "tesla",                    // lowercase ascii, official brand: mercedes-benz, volkswagen, kia, citroen
    "name": "Tesla",                    // official display name
    "legacy_id": 1,                     // existing makes.id from legacy/{make}.json, or null for a new make
    "country": "US",                    // ISO 3166-1 alpha-2 of HQ
    "headquarters": "Austin, Texas, USA",
    "founded": 2003,
    "parent_group": null,               // e.g. "Volkswagen Group"
    "website_url": "https://www.tesla.com",
    "status": "active",                 // active | pre-production | defunct | acquired
    "status_date": null,                // "YYYY-MM-DD" (or "YYYY-MM", "YYYY") when defunct/acquired
    "status_details": null,             // one plain sentence: "Filed for Chapter 11 bankruptcy on 17 June 2024; assets sold..."
    "description": "2-3 plain sentences.",
    "sources": [{"fields": ["status"], "url": "https://...", "name": "Reuters"}]
  },
  "models": [
    {
      "slug": "tesla-model-3",          // if the model exists in legacy data: its make_model_slug, unchanged. New: "{make_slug}-{url_slug}"
      "url_slug": "model-3",            // slugified name; if all digits prefix the make ("polestar-2"); never contains "-vs-"
      "name": "Model 3",
      "aliases": [],                    // former / other-market names
      "body_style": "sedan",            // sedan|hatchback|wagon|coupe|convertible|suv|pickup|van|minivan|microcar
      "is_commercial": false,           // cargo vans, semis, fleet-only
      "status": "current",              // upcoming|current|discontinued|cancelled (global)
      "official_url": "https://www.tesla.com/model3",
      "description": "2-3 plain sentences about the model across its life.",
      "markets": {                      // only markets you can source. Keys: US, CA, EU, UK, CN, JP, KR, IN, AU
        "US": {"status": "current", "launch": "2017-07", "end": null, "local_name": null}
      },
      "relations": [{"relation": "twin", "model": "subaru-solterra"}],   // twin | successor (this model succeeds "model")
      "sources": [{"fields": ["status"], "url": "https://...", "name": "..."}],
      "generations": [
        {
          "slug": "2017",               // first model year (US) or first delivery year; unique per model. Two in one year: "2024-refresh"
          "name": "Original",           // "Highland", "Second generation", "Facelift"
          "kind": "generation",         // generation | refresh
          "ordinal": 1,                 // a refresh keeps its generation's number
          "code_name": null,
          "platform": null,
          "start_year": 2017,
          "end_year": 2023,             // null while on sale
          "status": "discontinued",
          "description": "1-2 sentences: what changed in this version.",
          "images": [
            {"source": "commons",       // commons | press | legacy
             "file_url": "https://upload.wikimedia.org/...jpg",   // direct file URL (commons/press) or legacy path "/pub_assets/car_images/x.png"
             "page_url": "https://commons.wikimedia.org/wiki/File:...",
             "credit": "Author name", "license": "CC BY-SA 4.0",
             "view": "front_3q",        // front_3q|rear_3q|side|front|rear|interior|dashboard|detail
             "verified_by_viewing": true}   // you opened the image and it shows THIS generation
          ],
          "sources": [],
          "variants": [
            {
              "slug": "long-range-awd",       // unique within the generation
              "name": "Long Range AWD",
              "legacy_ids": [24],             // existing cars.id rows this variant IS (usually 0 or 1). Every legacy row of your makes must be claimed exactly once across your file.
              "status": "discontinued",       // or null to inherit the generation's
              "year_from": 2017, "year_to": 2023,
              "drivetrain": "AWD",            // FWD|RWD|AWD
              "body_type": null,              // only if it differs from the model's
              "seats": 5,
              "battery_kwh": 82.0, "battery_basis": "gross",   // usable|gross|null when unknown
              "power_hp": 425, "torque_lbft": 364,
              "accel_0_60_s": 4.2, "accel_0_100_s": null,      // two separate facts; never derive one from the other
              "top_speed_mph": 145,
              "dc_kw": 250,
              "offerings": [                  // one per market (and model year where the market has them)
                {"market": "US", "model_year": 2023,
                 "range": 358, "range_unit": "mi", "range_cycle": "EPA",      // EPA|WLTP|CLTC|WLTC|KR|MIDC
                 "price": 47240, "launch_price": null, "currency": "USD",
                 "price_basis": "msrp_excl_destination",                       // msrp_excl_destination|msrp_incl_destination|list_incl_vat
                 "connector": "NACS",                                          // NACS|CCS1|CCS2|GBT|CHADEMO
                 "is_estimate": false}
              ],
              "sources": [{"fields": ["specs", "price", "range"], "url": "https://...", "name": "Tesla"}]
            }
          ]
        }
      ]
    }
  ],
  "legacy_notes": [                     // anything about legacy rows the director should know
    {"legacy_id": 204, "note": "Legacy row mixes Highland price with 2021 range."}
  ],
  "gaps": ["Could not source WLTP range for X"]
}
```

What the validator enforces beyond the comments above: EPA range is in `mi`, every other cycle in `km`;
a discontinued/cancelled model and a defunct/acquired make need a source whose `fields` include `"status"`;
every variant needs a source with a URL; commons/press images need `page_url` and `credit` (commons also
`license`); legacy images must sit under `/pub_assets/car_images/` and have `verified_by_viewing: true`.
Implausible numbers (EPA range outside 30-800 mi, 0-60 outside 1.5-20 s, battery outside 5-250 kWh,
DC charging outside 3-1000 kW, power outside 10-2500 hp) are warnings, not errors.

## Validate

```sh
# one file, a whole directory (skips _*.json), or several
python3 ev_backend/scripts/catalog/validate_seed.py ev_backend/catalog/data/tesla.json
python3 ev_backend/scripts/catalog/validate_seed.py ev_backend/catalog/data

# also require every legacy car id to be claimed exactly once
python3 ev_backend/scripts/catalog/validate_seed.py ev_backend/catalog/data/tesla.json \
  --legacy _catalog_work/legacy/tesla.json

# machine-readable summary (counts, errors, warnings)
python3 ev_backend/scripts/catalog/validate_seed.py ev_backend/catalog/data --json
```

Errors print as `ERROR <file> <json path>: <message>` and exit 1; warnings print as `WARN` and do not
change the exit code. A file must exit 0 before it is handed in.
