"""Pure rules: slugs and effective-status coercion (no database)."""
import services.catalog_slugs as slugs
import services.catalog_status as S


def test_slugify_transliterates_and_collapses():
    assert slugs.slugify("Citroën ë-C4") == "citroen-e-c4"
    assert slugs.slugify("ID.4 GTX") == "id-4-gtx"
    assert slugs.slugify("  Model 3  ") == "model-3"
    assert slugs.slugify(None) == ""


def test_model_url_slug_prefixes_all_digit_names():
    assert slugs.model_url_slug("polestar", "2") == "polestar-2"
    assert slugs.model_url_slug("bmw", "i4") == "i4"
    assert slugs.is_valid_model_url_slug("model-3")
    assert not slugs.is_valid_model_url_slug("2")
    assert not slugs.is_valid_model_url_slug("model-3-vs-i4")
    assert not slugs.is_valid_model_url_slug("Model-3")


def test_generation_slug_rule():
    assert slugs.generation_slug(2024) == "2024"
    assert slugs.generation_slug(2024, {"2024"}, "Juniper") == "2024-juniper"
    assert slugs.generation_slug(2024, {"2024", "2024-refresh"}) == "2024-gen2"


def test_legacy_make_path_slug_mirrors_frontend():
    assert slugs.legacy_make_path_slug("Citroën") == "citron"
    assert slugs.legacy_make_path_slug("Rolls-Royce") == "rolls-royce"
    assert slugs.legacy_make_path_slug("Slate Auto") == "slate-auto"


def test_variant_full_slug_is_unique():
    assert slugs.variant_full_slug("tesla", "model-3", "2024", "rwd") == "tesla-model-3-2024-rwd"
    assert slugs.variant_full_slug("tesla", "model-3", "2024", "rwd", {"tesla-model-3-2024-rwd"}) == \
        "tesla-model-3-2024-rwd-2"


def test_coercion_under_defunct_brand_and_discontinued_parent():
    assert S.coerce("current", None, brand_defunct=True) == "discontinued"
    assert S.coerce("upcoming", None, brand_defunct=True) == "cancelled"
    assert S.coerce("current", "discontinued") == "discontinued"
    assert S.coerce("upcoming", "discontinued") == "cancelled"
    assert S.coerce("current", "cancelled") == "cancelled"
    assert S.coerce("discontinued", "current") == "discontinued"
    assert S.coerce("current", "upcoming") == "current"           # kept, flagged instead
    assert S.consistency_warning("current", "upcoming")
    assert S.coerce(None, "current") == "current"                 # NULL inherits


def test_status_chain_and_make_label():
    assert S.model_status("current", "acquired") == "discontinued"
    assert S.brand_status("acquired") == "defunct"
    m = S.model_status("current", "active")
    g = S.generation_status("current", m, "active")
    assert S.variant_status(None, "current", g, "active") == "current"
    assert S.variant_status("current", "discontinued", "discontinued", "active") == "discontinued"
    assert S.make_display_status("defunct", ["current"]) == "defunct"
    assert S.make_display_status("active", ["discontinued", "upcoming"]) == "upcoming"
    assert S.make_display_status("pre-production", []) == "upcoming"
    assert S.make_display_status("active", ["discontinued"]) == "discontinued"


def test_default_generation_rule():
    gens = [dict(slug="2017", start_year=2017, status="discontinued"),
            dict(slug="2024", start_year=2024, status="current"),
            dict(slug="2027", start_year=2027, status="upcoming")]
    assert S.default_generation(gens)["slug"] == "2024"
    gens[1]["status"] = "discontinued"
    assert S.default_generation(gens)["slug"] == "2027"
    gens[2]["status"] = "cancelled"
    assert S.default_generation(gens)["slug"] == "2024"
