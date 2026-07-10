from backend.config_loader import get_discovery_queries


def test_discovery_queries_use_configured_industry():
    queries = get_discovery_queries("manufacturing")
    assert queries[0] == "manufacturing company"
    assert "food manufacturing" in queries


def test_discovery_queries_fall_back_to_label_hint():
    queries = get_discovery_queries("stevedoring_services", "Stevedoring Services")
    assert queries == ["Stevedoring Services company", "Stevedoring Services"]


def test_discovery_queries_ignore_empty_configured_list():
    queries = get_discovery_queries(
        "port_agency",
        "Port Agency",
    )
    assert "Port Agency" in queries[0]
