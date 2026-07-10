from backend.icp_scoring_config import (
    get_scoring_settings,
    reset_scoring_overrides,
    update_scoring_settings,
)


def test_update_and_reset_scoring_overrides(tmp_path, monkeypatch):
    icp_path = tmp_path / "icp.yaml"
    overrides_path = tmp_path / "icp_overrides.yaml"
    icp_path.write_text(
        """
thresholds:
  hot: 65
  qualified: 50
scoring_weights:
  portal_detection: 15
  industry_match: 15
negative_weights:
  no_website: 8
employee_bands:
  sweet_spot_min: 15
""".strip(),
        encoding="utf-8",
    )

    import backend.config_loader as loader
    import backend.icp_scoring_config as scoring_config

    monkeypatch.setattr(loader.settings, "icp_config_path", str(icp_path))
    monkeypatch.setattr(scoring_config, "ICP_OVERRIDES_PATH", overrides_path)
    loader.load_icp_config.cache_clear()

    updated = update_scoring_settings(
        {
            "scoring_weights": {"portal_detection": 20, "industry_match": 15},
            "thresholds": {"hot": 70, "qualified": 50},
        }
    )
    assert updated["values"]["scoring_weights"]["portal_detection"] == 20
    assert updated["overrides"]["scoring_weights"]["portal_detection"] == 20
    assert "industry_match" not in updated["overrides"]["scoring_weights"]

    merged = loader.load_icp_config()
    assert merged["scoring_weights"]["portal_detection"] == 20
    assert merged["thresholds"]["hot"] == 70

    reset = reset_scoring_overrides()
    loader.load_icp_config.cache_clear()
    merged_after = loader.load_icp_config()
    assert merged_after["scoring_weights"]["portal_detection"] == 15
    assert reset["overrides"]["scoring_weights"] == {}
