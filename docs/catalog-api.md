# Catalog read API (`/catalog/*`)

The catalog is the new data model: **make → model → generation → variant → offering (market × model year)**.
It is read-only, public (no key), and served by `routers/catalog.py`. Data comes from the seed files in
`catalog/data/*.json`, loaded by `scripts/catalog/load_seed.py`. The legacy endpoints (`/cars/*`, `/makes`,
`/sitemap.xml`) are unchanged.

Examples below are real responses from the local database (2026-11-10, 18 seed files loaded), trimmed:
long arrays are cut to one or two items. Nothing else is changed.

## Conventions

| Topic | Rule |
|---|---|
| Base URL | local `http://localhost:8011`; production `https://ev-backend-three.vercel.app` once deployed and migrated |
| Keys | `slug`/`key`/`path` fields are always present. **Every other field may be `null`**; code must not assume a value exists. |
| Paths | `path` is the canonical frontend URL: `/make/{make}`, `/make/{make}/{model}`, `/make/{make}/{model}/{generation}`, `/make/{make}/{model}/{generation}/{variant}`. Build links only from `path`. `key` is the same path without `/make/` (`tesla/model-3/2024/premium-awd`). |
| `slug` of a model | API key = the legacy `make_model_slug` for existing models (`tesla-model-3`, `polestar-2`), `{make}-{url_slug}` for new ones. Used by compare URLs. `url_slug` is the URL segment (`model-3`). |
| Status | `status` is the **effective** status (`upcoming`, `current`, `discontinued`, `cancelled`), computed once in `services/catalog_status.py`. `own_status` is the stored value. Under a defunct/acquired brand or a discontinued parent, `current` becomes `discontinued` and `upcoming` becomes `cancelled`; under a cancelled parent everything is `cancelled`. A variant with no own status inherits its generation's. |
| Brand | `make.status` is the stored company fact (`active`, `pre-production`, `defunct`, `acquired`). `brand_status` is `defunct` for defunct or acquired brands, otherwise the stored value. Show a "defunct brand" badge with `status_date` (partial dates allowed: `2024`, `2024-06`, `2024-06-17`) and `status_details`. |
| Make label | `display_status`: `defunct`; else `current` if any model is current, else `upcoming`, else `discontinued`. Only on list endpoints (`null` inside model/variant responses). |
| Range | Always `range` + `range_unit` (`mi` for EPA, `km` for WLTP/CLTC/WLTC/KR/MIDC) + `range_cycle`. Never convert. |
| Price | `price` (current) and `launch_price` with `currency` (ISO 4217, native), `price_basis` (`msrp_excl_destination`, `msrp_incl_destination`, `list_incl_vat`), `market`, `model_year`. Never convert. `is_estimate` = manufacturer target for an unreleased car. |
| Acceleration | `accel_0_60_s` and `accel_0_100_s` are separate facts; one is never derived from the other. |
| Battery | `battery_kwh` with `battery_basis` (`usable`, `gross`, or `null` = not stated). |
| `model_year` | `null` on offerings in markets without model years (EU, CN, ...): "currently offered". |
| Markets | `US, CA, EU, UK, CN, JP, KR, IN, AU`. `EU` = EEA + Switzerland. |
| Images | Only images a researcher opened and confirmed (`verified_by_viewing`) are returned. A generation with no verified photo returns `images: []`: show a "no photo of this generation yet" placeholder, never another generation's photo. Show `credit` + `license` linked to `page_url` when present (Wikimedia Commons needs attribution). `source: legacy` = a file from `eeveecars/public/pub_assets/car_images/` (relative URL). |
| Sources | `sources: [{"fields": [...], "url": "...", "name": "..."}]` at make, model, generation and variant level. A variant's sources cover its offerings. |
| Default generation | Newest `current` generation; else newest not `cancelled`; else newest. The model page shows it first; `is_default: true`. Generations are returned newest first. |
| Caching | Lists: `public, s-maxage=300, stale-while-revalidate=3600`; details and resolve: `s-maxage=600`; `/catalog/makes` and the sitemap: `s-maxage=3600, stale-while-revalidate=86400` (same policies as the legacy GETs). |
| Not migrated yet | Every `/catalog/*` route returns **503** `{"detail": "Catalog tables are not available yet (migration catalog_02_hierarchy has not been applied)."}` with `Cache-Control: no-store`, `Retry-After: 300`. Treat 503 as "fall back to the legacy page", never as 404. |
| Errors | 404 `{"detail": "..."}` for unknown make/model/variant/best key/resolve key; 400 for a bad `kind`. |

## Endpoints

| Method + path | Purpose |
|---|---|
| `GET /catalog/meta` | Counts and `dataAsOf` (for "N models", "updated on" claims) |
| `GET /catalog/makes?status=` | All makes with display status and model counts |
| `GET /catalog/makes/{slug}?market=` | Make page: make + model cards grouped by effective status |
| `GET /catalog/models?market=&status=&make=&body_style=&q=&commercial=&limit=&offset=` | Model cards for browse/home pages |
| `GET /catalog/models/{make}/{model}` | Model page: full tree |
| `GET /catalog/variants/{make}/{model}/{generation}/{variant}` | Variant page |
| `GET /catalog/resolve?kind=model\|make\|variant&key=` | Legacy URL → new path |
| `GET /catalog/best/{key}?limit=` | Best-of lists |
| `GET /catalog/sitemap.xml` | Sitemap of canonical catalog URLs |

### `GET /catalog/meta`

`dataAsOf` is the date of the newest catalog row change (seed load), `YYYY-MM-DD`.

```json
{
  "counts": {
    "makes": 18,
    "models": 129,
    "generations": 167,
    "variants": 503,
    "offerings": 979,
    "images": 118
  },
  "models_by_status": {
    "discontinued": 30,
    "current": 89,
    "upcoming": 10
  },
  "makes_by_display_status": {
    "current": 17,
    "upcoming": 1
  },
  "markets": [
    "AU",
    "CA",
    "CN",
    "EU",
    "IN",
    "JP",
    "KR",
    "UK",
    "US"
  ],
  "dataAsOf": "2026-11-10",
  "data_updated_at": "2026-11-10T17:25:36.033360-06:00"
}
```

### `GET /catalog/makes`

Sorted by name. `status` filter = comma-separated `display_status` values. `logo_url` is the legacy logo
(relative or absolute URL). `model_counts` counts models by effective status.

```json
{
  "count": 18,
  "makes": [
    {
      "slug": "buick",
      "name": "Buick",
      "path": "/make/buick",
      "status": "active",
      "brand_status": "active",
      "display_status": "current",
      "status_date": null,
      "status_details": null,
      "country": "US",
      "founded": 1903,
      "logo_url": null,
      "model_counts": {
        "upcoming": 0,
        "current": 3,
        "discontinued": 2,
        "cancelled": 0
      }
    },
    {
      "slug": "cadillac",
      "name": "Cadillac",
      "path": "/make/cadillac",
      "status": "active",
      "brand_status": "active",
      "display_status": "current",
      "status_date": null,
      "status_details": null,
      "country": "US",
      "founded": 1902,
      "logo_url": "/pub_assets/makes/cadillac_logo.png",
      "model_counts": {
        "upcoming": 0,
        "current": 5,
        "discontinued": 0,
        "cancelled": 0
      }
    }
  ]
}
```

### `GET /catalog/makes/{slug}`

`slug` is the make slug (`mercedes-benz`, `citroen`, `kia`). For legacy slugs (`mercedes`, `citron`, `vw`) call
`/catalog/resolve?kind=make` first. `models` always has the four keys `upcoming`, `current`, `discontinued`,
`cancelled`; cards inside are newest first. `market` sets the headline market of the cards (see below).
`legacy_id` is the old `makes.id` (null for makes added by the catalog).

```json
{
  "make": {
    "slug": "polestar",
    "name": "Polestar",
    "path": "/make/polestar",
    "status": "active",
    "brand_status": "active",
    "display_status": "current",
    "status_date": null,
    "status_details": null,
    "country": "SE",
    "founded": 1996,
    "logo_url": "/pub_assets/makes/polestar_logo.png",
    "model_counts": {
      "upcoming": 1,
      "current": 4,
      "discontinued": 0,
      "cancelled": 0
    },
    "headquarters": "Gothenburg (Torslanda), Sweden",
    "parent_group": "Geely (Li Shufu)",
    "website_url": "https://www.polestar.com",
    "description": "Swedish electric-car brand that grew out of a racing team founded in 1996, bought by Volvo in 2015 and relaunched as a standalone EV maker in 2017; it is majority-owned by Geely founder Li Shufu's companies and Geely Holding. In June 2026 it said it would stop selling new cars in the US after being denied authorisation under the Connected Vehicle Rule, and it is concentrating on Europe.",
    "sources": [
      {
        "url": "https://en.wikipedia.org/wiki/Polestar",
        "name": "Wikipedia",
        "fields": [
          "founded",
          "parent_group",
          "status"
        ]
      }
    ],
    "legacy_id": 27
  },
  "models": {
    "upcoming": [
      {
        "slug": "polestar-7",
        "key": "polestar/polestar-7",
        "url_slug": "polestar-7",
        "path": "/make/polestar/polestar-7",
        "name": "Polestar 7",
        "make": {
          "slug": "polestar",
          "name": "Polestar",
          "path": "/make/polestar",
          "status": "active",
          "brand_status": "active",
          "status_date": null
        },
        "status": "upcoming",
        "own_status": "upcoming",
        "brand_status": "active",
        "body_style": "suv",
        "is_commercial": false,
        "aliases": [],
        "years": {
          "start": 2028,
          "end": null
        },
        "markets": [],
        "default_generation": {
          "slug": "2028",
          "name": "First generation",
          "path": "/make/polestar/polestar-7/2028"
        },
        "image": null,
        "headline_market": null,
        "from_price": null,
        "max_range": null,
        "quickest_0_60": null,
        "quickest_0_100": null,
        "variant_count": 0
      }
    ],
    "current": [
      {
        "slug": "polestar-5",
        "key": "polestar/polestar-5",
        "url_slug": "polestar-5",
        "path": "/make/polestar/polestar-5",
        "name": "Polestar 5",
        "make": {
          "slug": "polestar",
          "name": "Polestar",
          "path": "/make/polestar",
          "status": "active",
          "brand_status": "active",
          "status_date": null
        },
        "status": "current",
        "own_status": "current",
        "brand_status": "active",
        "body_style": "sedan",
        "is_commercial": false,
        "aliases": [],
        "years": {
          "start": 2026,
          "end": null
        },
        "markets": [
          "EU",
          "UK"
        ],
        "default_generation": {
          "slug": "2026",
          "name": "First generation",
          "path": "/make/polestar/polestar-5/2026"
        },
        "image": {
          "url": "https://upload.wikimedia.org/wikipedia/commons/d/dc/Polestar_5_Auto_Zuerich_2025_DSC_3198.jpg",
          "source": "commons",
          "page_url": "https://commons.wikimedia.org/wiki/File:Polestar_5_Auto_Zuerich_2025_DSC_3198.jpg",
          "credit": "Alexander Migl",
          "license": "CC BY-SA 4.0",
          "view": "front_3q",
          "alt": "Polestar Polestar 5 (First generation, 2026), front three-quarter view",
          "is_primary": true,
          "width": null,
          "height": null
        },
        "headline_market": "EU",
        "from_price": {
          "value": 119900,
          "currency": "EUR",
          "basis": "list_incl_vat",
          "market": "EU",
          "model_year": null,
          "is_estimate": false,
          "variant": {
            "id": 488,
            "slug": "dual-motor",
            "name": "Dual Motor",
            "path": "/make/polestar/polestar-5/2026/dual-motor"
          }
        },
        "max_range": {
          "value": 670,
          "unit": "km",
          "cycle": "WLTP",
          "market": "EU",
          "model_year": null,
          "is_estimate": false,
          "variant": {
            "id": 488,
            "slug": "dual-motor",
            "name": "Dual Motor",
            "path": "/make/polestar/polestar-5/2026/dual-motor"
          }
        },
        "quickest_0_60": {
          "value": 3.1,
          "unit": "s",
          "variant": {
            "id": 489,
            "slug": "performance",
            "name": "Performance",
            "path": "/make/polestar/polestar-5/2026/performance"
          }
        },
        "quickest_0_100": null,
        "variant_count": 2
      }
    ],
    "discontinued": [],
    "cancelled": []
  }
}
```

### `GET /catalog/models`

Model cards (one per model), sorted by make name then model name. Filters (all optional, comma lists allowed):

| Param | Meaning |
|---|---|
| `market` | Only models with a row for that market; `status` then filters the **market** status, and each card gets `market_status`. Also fixes the headline market. |
| `status` | Effective status (model status, or market status when `market` is given). Home page: `market=US&status=current`; "coming soon": `status=upcoming`. |
| `make` | Make slug(s) |
| `body_style` | `sedan, hatchback, wagon, coupe, convertible, suv, pickup, van, minivan, microcar` |
| `q` | Case-insensitive; every word must appear in make name/slug, model name/slug or aliases |
| `commercial` | `false` hides cargo vans, semis and fleet-only models (do this for consumer lists) |
| `limit`, `offset` | Paging; `count` is the total before paging |

Card headline figures are computed over the **default generation's** non-cancelled variants, in the headline
market (`market` param, else the first of US, EU, UK, CN, CA, JP, KR, AU, IN that has offerings):
`from_price` = lowest current price (newest model year per variant, majority currency), `max_range` = longest
range in that market's main cycle (EPA for US/CA, WLTP for EU/UK/AU, CLTC for CN, ...), `quickest_0_60` /
`quickest_0_100` = lowest time. Each names the `variant` it came from. `image` is the default generation's
primary verified image or `null`. `years.end` is `null` while any generation is open-ended.

```json
{
  "count": 6,
  "offset": 0,
  "market": null,
  "models": [
    {
      "slug": "tesla-cybercab",
      "key": "tesla/cybercab",
      "url_slug": "cybercab",
      "path": "/make/tesla/cybercab",
      "name": "Cybercab",
      "make": {
        "slug": "tesla",
        "name": "Tesla",
        "path": "/make/tesla",
        "status": "active",
        "brand_status": "active",
        "status_date": null
      },
      "status": "current",
      "own_status": "current",
      "brand_status": "active",
      "body_style": "coupe",
      "is_commercial": true,
      "aliases": [
        "Robotaxi"
      ],
      "years": {
        "start": 2026,
        "end": null
      },
      "markets": [
        "US"
      ],
      "default_generation": {
        "slug": "2026",
        "name": "First generation",
        "path": "/make/tesla/cybercab/2026"
      },
      "image": {
        "url": "https://upload.wikimedia.org/wikipedia/commons/3/3d/Tesla_Cybercab_-_San_Francisco_-_June_2026.jpg",
        "source": "commons",
        "page_url": "https://commons.wikimedia.org/wiki/File:Tesla_Cybercab_-_San_Francisco_-_June_2026.jpg",
        "credit": "9yz",
        "license": "CC BY 4.0",
        "view": "side",
        "alt": "Tesla Cybercab (First generation, 2026), side view",
        "is_primary": true,
        "width": null,
        "height": null
      },
      "headline_market": null,
      "from_price": null,
      "max_range": null,
      "quickest_0_60": null,
      "quickest_0_100": null,
      "variant_count": 1
    }
  ]
}
```

### `GET /catalog/models/{make}/{model}`

`make` = make slug, `model` = `url_slug`. Returns the make, the model, `headline` (same computation as the
card), `default_generation` (slug), all generations newest first (each with images, sources and variants with
their offerings), and `relations`. `relations[].relation` is `twin`, `successor` (the related model replaced
this one) or `predecessor` (this model replaced the related one), e.g.
`{"relation": "predecessor", "model": {"slug": "fisker-ocean", "name": "Ocean", "path": "/make/fisker/ocean", "make": {...}, "status": "discontinued"}}`.
`model.markets[]` gives per-market `status` (effective), `own_status`, `local_name`, `launch`, `end` (partial dates).
Variants are in the order the researchers listed them (base to top). `updated_at` = newest change in the tree.

```json
{
  "make": {
    "slug": "tesla",
    "name": "Tesla",
    "path": "/make/tesla",
    "status": "active",
    "brand_status": "active",
    "display_status": null,
    "status_date": null,
    "status_details": null,
    "country": "US",
    "founded": 2003,
    "logo_url": "https://1000logos.net/wp-content/uploads/2021/04/Tesla-logo.png",
    "model_counts": null,
    "headquarters": "Austin, Texas, USA",
    "parent_group": null,
    "website_url": "https://www.tesla.com",
    "description": "American electric-car maker founded in 2003, known for the Roadster, Model S, X, 3 and Y and the Cybertruck. The Model Y and Model 3 are its volume sellers; the Model S and X ended production in May 2026 and the Cybercab robotaxi and Semi truck entered production in 2026.",
    "sources": [
      {
        "url": "https://en.wikipedia.org/wiki/Tesla,_Inc.",
        "name": "Wikipedia: Tesla, Inc.",
        "fields": [
          "headquarters",
          "founded"
        ]
      }
    ],
    "legacy_id": 1
  },
  "model": {
    "slug": "tesla-model-3",
    "key": "tesla/model-3",
    "url_slug": "model-3",
    "path": "/make/tesla/model-3",
    "name": "Model 3",
    "aliases": [],
    "body_style": "sedan",
    "is_commercial": false,
    "status": "current",
    "own_status": "current",
    "brand_status": "active",
    "years": {
      "start": 2017,
      "end": null
    },
    "description": "Tesla's mid-size electric sedan, delivered from July 2017 and one of the best-selling EVs of all time. The heavily refreshed 'Highland' version arrived in late 2023 (US 2024 model year), with a new Performance model in 2024 and a cheaper Standard trim in October 2025.",
    "official_url": "https://www.tesla.com/model3",
    "markets": [
      {
        "market": "US",
        "status": "current",
        "own_status": "current",
        "local_name": null,
        "launch": "2017-07",
        "end": null
      }
    ],
    "sources": [
      {
        "url": "https://en.wikipedia.org/wiki/Tesla_Model_3",
        "name": "Wikipedia: Tesla Model 3",
        "fields": [
          "years"
        ]
      }
    ]
  },
  "headline": {
    "market": "US",
    "from_price": {
      "value": 38380,
      "currency": "USD",
      "basis": "msrp_incl_destination",
      "market": "US",
      "model_year": 2027,
      "is_estimate": false,
      "variant": {
        "id": 557,
        "slug": "standard-rwd",
        "name": "Standard RWD",
        "path": "/make/tesla/model-3/2024/standard-rwd"
      }
    },
    "max_range": {
      "value": 363,
      "unit": "mi",
      "cycle": "EPA",
      "market": "US",
      "model_year": 2027,
      "is_estimate": false,
      "variant": {
        "id": 558,
        "slug": "premium-rwd",
        "name": "Premium RWD (Long Range RWD)",
        "path": "/make/tesla/model-3/2024/premium-rwd"
      }
    },
    "quickest_0_60": {
      "value": 2.9,
      "unit": "s",
      "variant": {
        "id": 560,
        "slug": "performance",
        "name": "Performance",
        "path": "/make/tesla/model-3/2024/performance"
      }
    },
    "quickest_0_100": null
  },
  "default_generation": "2024",
  "generations": [
    {
      "id": 142,
      "slug": "2024",
      "key": "tesla/model-3/2024",
      "path": "/make/tesla/model-3/2024",
      "name": "Highland",
      "kind": "refresh",
      "ordinal": 1,
      "code_name": "Highland",
      "platform": null,
      "start_year": 2024,
      "end_year": null,
      "status": "current",
      "own_status": "current",
      "description": "Major refresh with new front and rear styling, a new interior with rear screen, better range and refinement; deliveries began October 2023 outside North America and January 2024 in the US.",
      "is_default": true,
      "images": [
        {
          "url": "/pub_assets/car_images/tes_m3_std_range.png",
          "source": "legacy",
          "page_url": null,
          "credit": null,
          "license": null,
          "view": "front_3q",
          "alt": "Tesla Model 3 (Highland, 2024), front three-quarter view",
          "is_primary": true,
          "width": null,
          "height": null
        }
      ],
      "sources": [
        {
          "url": "https://en.wikipedia.org/wiki/Tesla_Model_3",
          "name": "Wikipedia",
          "fields": [
            "years"
          ]
        }
      ],
      "updated_at": "2026-11-10T17:25:36.033360-06:00",
      "variants": [
        {
          "id": 557,
          "slug": "standard-rwd",
          "key": "tesla/model-3/2024/standard-rwd",
          "path": "/make/tesla/model-3/2024/standard-rwd",
          "name": "Standard RWD",
          "status": "current",
          "own_status": "current",
          "year_from": 2026,
          "year_to": null,
          "drivetrain": "RWD",
          "body_type": "sedan",
          "seats": 5,
          "battery_kwh": null,
          "battery_basis": null,
          "power_hp": null,
          "torque_lbft": null,
          "accel_0_60_s": 5.8,
          "accel_0_100_s": null,
          "top_speed_mph": null,
          "dc_kw": null,
          "offerings": [
            {
              "market": "US",
              "model_year": 2027,
              "price": 38380,
              "launch_price": null,
              "currency": "USD",
              "price_basis": "msrp_incl_destination",
              "range": 321,
              "range_unit": "mi",
              "range_cycle": "EPA",
              "connector": "NACS",
              "is_estimate": false
            },
            {
              "market": "US",
              "model_year": 2026,
              "price": 36990,
              "launch_price": null,
              "currency": "USD",
              "price_basis": "msrp_excl_destination",
              "range": 321,
              "range_unit": "mi",
              "range_cycle": "EPA",
              "connector": "NACS",
              "is_estimate": false
            }
          ],
          "sources": [
            {
              "url": "https://tslna.com/en/model-3-usa-guide/",
              "name": "TSLNA: 2026 Tesla Model 3 USA guide",
              "fields": [
                "price",
                "specs"
              ]
            }
          ],
          "updated_at": "2026-11-10T17:25:36.033360-06:00"
        }
      ]
    },
    {
      "id": 141,
      "slug": "2017",
      "key": "tesla/model-3/2017",
      "path": "/make/tesla/model-3/2017",
      "name": "Original",
      "kind": "generation",
      "ordinal": 1,
      "code_name": null,
      "platform": null,
      "start_year": 2017,
      "end_year": 2023,
      "status": "discontinued",
      "own_status": "discontinued",
      "description": "The original design, built 2017 to early 2024 in Fremont and Shanghai; Long Range and Performance packs grew to 82 kWh for 2021.",
      "is_default": false,
      "images": [
        {
          "url": "/pub_assets/car_images/tes_m3_perf.png",
          "source": "legacy",
          "page_url": null,
          "credit": null,
          "license": null,
          "view": "front_3q",
          "alt": "Tesla Model 3 (Original, 2017), front three-quarter view",
          "is_primary": true,
          "width": null,
          "height": null
        }
      ],
      "sources": [
        {
          "url": "https://en.wikipedia.org/wiki/Tesla_Model_3",
          "name": "Wikipedia",
          "fields": [
            "years"
          ]
        }
      ],
      "updated_at": "2026-11-10T17:25:36.033360-06:00",
      "variants": [
        {
          "id": 553,
          "slug": "standard-range",
          "key": "tesla/model-3/2017/standard-range",
          "path": "/make/tesla/model-3/2017/standard-range",
          "name": "Standard Range RWD",
          "status": "discontinued",
          "own_status": "discontinued",
          "year_from": 2019,
          "year_to": 2020,
          "drivetrain": "RWD",
          "body_type": "sedan",
          "seats": 5,
          "battery_kwh": null,
          "battery_basis": null,
          "power_hp": null,
          "torque_lbft": null,
          "accel_0_60_s": null,
          "accel_0_100_s": null,
          "top_speed_mph": 130.0,
          "dc_kw": null,
          "offerings": [
            {
              "market": "US",
              "model_year": 2020,
              "price": null,
              "launch_price": null,
              "currency": null,
              "price_basis": null,
              "range": 220,
              "range_unit": "mi",
              "range_cycle": "EPA",
              "connector": "NACS",
              "is_estimate": false
            },
            {
              "market": "US",
              "model_year": 2019,
              "price": null,
              "launch_price": 35000,
              "currency": "USD",
              "price_basis": "msrp_excl_destination",
              "range": 220,
              "range_unit": "mi",
              "range_cycle": "EPA",
              "connector": "NACS",
              "is_estimate": false
            }
          ],
          "sources": [
            {
              "url": "https://en.wikipedia.org/wiki/Tesla_Model_3",
              "name": "Wikipedia",
              "fields": [
                "years",
                "price"
              ]
            }
          ],
          "updated_at": "2026-11-10T17:25:36.033360-06:00"
        }
      ]
    }
  ],
  "relations": [],
  "updated_at": "2026-11-10T17:25:36.033360-06:00"
}
```

### `GET /catalog/variants/{make}/{model}/{generation}/{variant}`

The variant with all offerings, its generation (without other variants), the model summary, `siblings`
(other variants of the same generation) and `generations` (for a generation switcher). `variant.id` is the
`cars.id`, so legacy favourites/notes keyed by car id still match.

```json
{
  "make": {
    "slug": "tesla",
    "name": "Tesla",
    "path": "/make/tesla",
    "status": "active",
    "brand_status": "active",
    "display_status": null,
    "status_date": null,
    "status_details": null,
    "country": "US",
    "founded": 2003,
    "logo_url": "https://1000logos.net/wp-content/uploads/2021/04/Tesla-logo.png",
    "model_counts": null,
    "headquarters": "Austin, Texas, USA",
    "parent_group": null,
    "website_url": "https://www.tesla.com",
    "description": "American electric-car maker founded in 2003, known for the Roadster, Model S, X, 3 and Y and the Cybertruck. The Model Y and Model 3 are its volume sellers; the Model S and X ended production in May 2026 and the Cybercab robotaxi and Semi truck entered production in 2026.",
    "sources": [
      {
        "url": "https://en.wikipedia.org/wiki/Tesla,_Inc.",
        "name": "Wikipedia: Tesla, Inc.",
        "fields": [
          "headquarters",
          "founded"
        ]
      }
    ],
    "legacy_id": 1
  },
  "model": {
    "slug": "tesla-model-3",
    "name": "Model 3",
    "path": "/make/tesla/model-3",
    "status": "current",
    "own_status": "current",
    "body_style": "sedan",
    "is_commercial": false,
    "official_url": "https://www.tesla.com/model3",
    "years": {
      "start": 2017,
      "end": null
    }
  },
  "generation": {
    "id": 142,
    "slug": "2024",
    "key": "tesla/model-3/2024",
    "path": "/make/tesla/model-3/2024",
    "name": "Highland",
    "kind": "refresh",
    "ordinal": 1,
    "code_name": "Highland",
    "platform": null,
    "start_year": 2024,
    "end_year": null,
    "status": "current",
    "own_status": "current",
    "description": "Major refresh with new front and rear styling, a new interior with rear screen, better range and refinement; deliveries began October 2023 outside North America and January 2024 in the US.",
    "is_default": true,
    "images": [
      {
        "url": "/pub_assets/car_images/tes_m3_std_range.png",
        "source": "legacy",
        "page_url": null,
        "credit": null,
        "license": null,
        "view": "front_3q",
        "alt": "Tesla Model 3 (Highland, 2024), front three-quarter view",
        "is_primary": true,
        "width": null,
        "height": null
      }
    ],
    "sources": [
      {
        "url": "https://en.wikipedia.org/wiki/Tesla_Model_3",
        "name": "Wikipedia",
        "fields": [
          "years"
        ]
      }
    ],
    "updated_at": "2026-11-10T17:25:36.033360-06:00"
  },
  "variant": {
    "id": 559,
    "slug": "premium-awd",
    "key": "tesla/model-3/2024/premium-awd",
    "path": "/make/tesla/model-3/2024/premium-awd",
    "name": "Premium AWD (Long Range AWD)",
    "status": "current",
    "own_status": "current",
    "year_from": 2024,
    "year_to": null,
    "drivetrain": "AWD",
    "body_type": "sedan",
    "seats": 5,
    "battery_kwh": 78.1,
    "battery_basis": null,
    "power_hp": null,
    "torque_lbft": null,
    "accel_0_60_s": 3.8,
    "accel_0_100_s": null,
    "top_speed_mph": 125.0,
    "dc_kw": 250.0,
    "offerings": [
      {
        "market": "US",
        "model_year": 2027,
        "price": 48880,
        "launch_price": null,
        "currency": "USD",
        "price_basis": "msrp_incl_destination",
        "range": 346,
        "range_unit": "mi",
        "range_cycle": "EPA",
        "connector": "NACS",
        "is_estimate": false
      },
      {
        "market": "US",
        "model_year": 2026,
        "price": 47490,
        "launch_price": null,
        "currency": "USD",
        "price_basis": "msrp_excl_destination",
        "range": 346,
        "range_unit": "mi",
        "range_cycle": "EPA",
        "connector": "NACS",
        "is_estimate": false
      }
    ],
    "sources": [
      {
        "url": "https://www.carsdirect.com/automotive-news/2026-tesla-model-3-mid-year-changes-explained",
        "name": "CarsDirect: 2026 Model 3 mid-year changes",
        "fields": [
          "price",
          "specs"
        ]
      },
      {
        "url": "https://tslna.com/en/model-3-usa-guide/",
        "name": "TSLNA",
        "fields": [
          "price"
        ]
      }
    ],
    "updated_at": "2026-11-10T17:25:36.033360-06:00"
  },
  "siblings": [
    {
      "id": 557,
      "slug": "standard-rwd",
      "name": "Standard RWD",
      "path": "/make/tesla/model-3/2024/standard-rwd",
      "status": "current"
    },
    {
      "id": 204,
      "slug": "rwd",
      "name": "RWD",
      "path": "/make/tesla/model-3/2024/rwd",
      "status": "current"
    }
  ],
  "generations": [
    {
      "slug": "2024",
      "name": "Highland",
      "path": "/make/tesla/model-3/2024",
      "status": "current",
      "start_year": 2024,
      "end_year": null
    },
    {
      "slug": "2017",
      "name": "Original",
      "path": "/make/tesla/model-3/2017",
      "status": "discontinued",
      "start_year": 2017,
      "end_year": 2023
    }
  ]
}
```

### `GET /catalog/resolve?kind=&key=`

Maps a legacy URL key to its new path, in one hop. `kind=model` takes the old `/model_detail/{slug}` slug,
`kind=make` the old `/manufacturer/{slug}` slug (`citron`, `mercedes`, `vw`, also the new slug), `kind=variant`
the old `/car_detail/{id}` id. Keys are case-insensitive. `reason`: `legacy` (same entity), `merge` (a
duplicate legacy row/slug folded into this entity, e.g. `polestar-two` → `/make/polestar/polestar-2`), `alias`,
or `current` (not a legacy key, but a current model slug / make slug / variant id). 404 when there is no catalog
page (for example a make whose seed file is not loaded yet): show the legacy page or a 404 with `noindex`.
Recommended edge cache for the redirect itself: `s-maxage=86400, stale-while-revalidate=604800`.

```json
{
  "kind": "model",
  "key": "polestar-two",
  "path": "/make/polestar/polestar-2",
  "entity_type": "model",
  "entity_id": 56,
  "reason": "merge"
}
```

### `GET /catalog/best/{key}`

Keys: `evs-under-40k`, `longest-range-evs`, `fastest-evs`, `cheapest-evs`, `3-row-evs`, `electric-trucks`,
`300-mile-range-evs` (same slugs as `src/data/seoPages.ts`). US only: a model qualifies when its effective
status and its US market status are `current` (`electric-trucks` also takes `upcoming`, current first), it is
not commercial and the brand is not defunct. Figures are the card's US headline figures (USD, EPA), so each
item names its `variant`. The catalog has no review scores, so lists the old site ranked by rating are ranked
by price (`evs-under-40k`) or EPA range (`3-row-evs`). `unit` is the currency for price lists, `mi` for range,
`s` for acceleration. Default `limit` 12 (15 for `300-mile-range-evs`), max 100.

```json
{
  "key": "fastest-evs",
  "title": "Fastest Electric Cars (0-60 mph)",
  "market": "US",
  "metric": "accel",
  "items": [
    {
      "model": {
        "slug": "lucid-air",
        "key": "lucid/air",
        "url_slug": "air",
        "path": "/make/lucid/air",
        "name": "Air",
        "make": {
          "slug": "lucid",
          "name": "Lucid",
          "path": "/make/lucid",
          "status": "active",
          "brand_status": "active",
          "status_date": null
        },
        "status": "current",
        "own_status": "current",
        "brand_status": "active",
        "body_style": "sedan",
        "is_commercial": false,
        "aliases": [],
        "years": {
          "start": 2022,
          "end": null
        },
        "markets": [
          "EU",
          "US"
        ],
        "default_generation": {
          "slug": "2022",
          "name": "First generation",
          "path": "/make/lucid/air/2022"
        },
        "image": {
          "url": "/pub_assets/car_images/lucid_air.png",
          "source": "legacy",
          "page_url": null,
          "credit": null,
          "license": null,
          "view": "front_3q",
          "alt": "Lucid Air (First generation, 2022), front three-quarter view",
          "is_primary": true,
          "width": null,
          "height": null
        },
        "headline_market": "US",
        "from_price": {
          "value": 70900,
          "currency": "USD",
          "basis": "msrp_excl_destination",
          "market": "US",
          "model_year": 2027,
          "is_estimate": false,
          "variant": {
            "id": 370,
            "slug": "pure-rwd",
            "name": "Pure RWD",
            "path": "/make/lucid/air/2022/pure-rwd"
          }
        },
        "max_range": {
          "value": 520,
          "unit": "mi",
          "cycle": "EPA",
          "market": "US",
          "model_year": 2022,
          "is_estimate": false,
          "variant": {
            "id": 368,
            "slug": "dream-edition-range",
            "name": "Dream Edition Range",
            "path": "/make/lucid/air/2022/dream-edition-range"
          }
        },
        "quickest_0_60": {
          "value": 1.89,
          "unit": "s",
          "variant": {
            "id": 8,
            "slug": "sapphire",
            "name": "Sapphire",
            "path": "/make/lucid/air/2022/sapphire"
          }
        },
        "quickest_0_100": null,
        "variant_count": 8,
        "market_status": "current"
      },
      "value": 1.89,
      "unit": "s",
      "variant": {
        "id": 8,
        "slug": "sapphire",
        "name": "Sapphire",
        "path": "/make/lucid/air/2022/sapphire"
      },
      "rank": 1
    }
  ],
  "count": 1
}
```

### `GET /catalog/sitemap.xml`

Canonical URLs only: static pages (no `/marketplace`), the 7 best lists, curated compare pairs whose models
exist (alphabetical, canonical form), `/make`, every make (defunct included), every model, every
non-default generation and every variant. `lastmod` = newest change of the entity and its children; static
pages have none. Switch the frontend's `/sitemap.xml` rewrite to this endpoint in the same deploy as the new routes.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://www.evlineup.org/</loc>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>https://www.evlineup.org/about</loc>
    <priority>0.6</priority>
  </url>
  <url>
    <loc>https://www.evlineup.org/people</loc>
    <priority>0.6</priority>
  </url>
  <url>
    <loc>https://www.evlineup.org/advertise</loc>
    <priority>0.6</priority>
  </url>
  <url>
    <loc>https://www.evlineup.org/privacy</loc>
  ...
</urlset>
```

## Running it locally

See `_catalog_work/handover/backend.md` (start Postgres on 54329, `scripts/catalog/reset_local.sh`, then
`uvicorn main:app --port 8011` with `DATABASE_URL`, `SUPABASE_DATABASE_URL` and `USE_LOCAL_DB=false` set).
