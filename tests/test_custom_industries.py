from backend.config_loader import add_custom_industry, slugify_industry_id


def test_slugify_industry_id():
    assert slugify_industry_id("Veterinary Clinics") == "veterinary_clinics"
    assert slugify_industry_id("Oil & Gas / Energy") == "oil_gas_energy"


def test_add_custom_industry(tmp_path, monkeypatch):
    custom_path = tmp_path / "custom_industries.yaml"
    icp_path = tmp_path / "icp.yaml"
    icp_path.write_text("industries:\n  manufacturing:\n    label: Manufacturing\n    search_queries: []\n    keywords: []\n", encoding="utf-8")
    custom_path.write_text("industries: {}\n", encoding="utf-8")

    import backend.config_loader as loader

    monkeypatch.setattr(loader, "CUSTOM_INDUSTRIES_PATH", custom_path)
    monkeypatch.setattr(loader.settings, "icp_config_path", str(icp_path))
    loader.load_icp_config.cache_clear()

    result = add_custom_industry("Dental Offices")
    assert result["id"] == "dental_offices"
    assert result["label"] == "Dental Offices"
    assert result["custom"] is True

    merged = loader.load_icp_config()
    assert "dental_offices" in merged["industries"]
    assert merged["industries"]["dental_offices"]["search_queries"]
