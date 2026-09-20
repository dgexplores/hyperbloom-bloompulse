"""Phase 6: corpus growth (1910.219), instrument-backed cites, confidence."""
from backend.app.rag.citations import BACKING, citations_for, passages


def test_power_transmission_backing_resolves():
    assert BACKING["power_transmission"] in passages()
    assert BACKING["bearing_freq"] in passages()


def _verdict(**overrides):
    base = {
        "severity": "normal",
        "metrics": {"max_vib": 1.0, "max_temp_rise": 1.0, "pressure_var": 1.0},
        "physics_consistency": 0.5,
        "contributing_feature": "vibration",
    }
    base.update(overrides)
    return base


def test_bearing_cite_attaches_on_physics_fire():
    cites = citations_for(_verdict(severity="alert", physics_consistency=0.96))
    ids = [c.id for c in cites]
    assert any("ntn" in i or "bearing" in i.lower() for i in ids), ids


def test_bearing_cite_absent_without_physics():
    cites = citations_for(_verdict(severity="alert", physics_consistency=0.5))
    titles = [c.title for c in cites]
    assert "Bearing Unit Model: NTN UCFCX05" not in titles


def test_power_cite_on_vibration_driven_critical():
    cites = citations_for(_verdict(
        severity="critical", contributing_feature="vibration",
        metrics={"max_vib": 5.0, "max_temp_rise": 1.0, "pressure_var": 1.0},
    ))
    titles = [c.title for c in cites]
    assert "Sec 1910.219(d)(3) - Broken Pulleys" in titles


def test_power_cite_absent_for_heat_driven():
    cites = citations_for(_verdict(
        severity="critical", contributing_feature="temperature_rise",
        metrics={"max_vib": 1.0, "max_temp_rise": 20.0, "pressure_var": 1.0},
    ))
    titles = [c.title for c in cites]
    assert "Sec 1910.219(d)(3) - Broken Pulleys" not in titles


def test_confidence_published_is_one():
    cites = citations_for(_verdict(
        severity="critical", contributing_feature="vibration",
        metrics={"max_vib": 5.0, "max_temp_rise": 1.0, "pressure_var": 1.0},
    ))
    by_title = {c.title: c for c in cites}
    assert by_title["Sec 1910.219(d)(3) - Broken Pulleys"].confidence == 1.0
    assert by_title["Sec 1910.219(d)(3) - Broken Pulleys"].synthetic is False


def test_confidence_synthetic_is_discounted():
    cites = citations_for(_verdict(severity="alert", physics_consistency=0.96))
    by_title = {c.title: c for c in cites}
    ntn = by_title["Bearing Unit Model: NTN UCFCX05"]
    assert ntn.synthetic is True
    assert ntn.confidence == 0.6


def test_citation_cap_holds():
    cites = citations_for(_verdict(
        severity="critical", contributing_feature="vibration",
        physics_consistency=0.99,
        metrics={"max_vib": 5.0, "max_temp_rise": 20.0, "pressure_var": 15.0},
    ))
    assert len(cites) <= 5
