"""DAT-05: the clean_<inv>.py scripts. Each test feeds a few rows in PSI's own format."""

import csv

import clean_bass2
import clean_flex
import clean_saffire2
import pytest
from psi_sources import COLUMNS, write_clean

FLEX_HEADER = ",".join(
    ["FLEX Test #", "FLEX Identifier", "Test Date", "Test GMT", "Fuel", "Ambient pressure; mmHg"]
    + [f"{gas} initial ambient composition; mole fraction" for gas in ("O", "N", "CO", "He")]
    + ["Droplet initial diameter; mm", "Visible flame extinction diameter; mm"]
    + ["Burning rate; mm", "Burn time; s", "Test end"]
)
FLEX_RAW = (
    FLEX_HEADER
    + """
1,20CAL08,3/5/2009,17:22:03,Methanol,757.7,0.21,0.79,0,0,1.69,0.89,0.52,4.3,Disruption
2,20CAL10,3/5/2009,19:20:06,Heptane,760,0.3,0.7,0,0,1.86,0.94,0.6,5,Completion
3,X,3/5/2009,19:20:06,Heptane,0,0.15,0.85,0,0,1.86,0.94,0.6,5,Extinction
,,,,,,,,,,,,,,
"""
)

SAFFIRE_HEADER = ",".join(
    ["Sample Number", "Material", "Samle Thickness ", "Sample Length ", "Sample Width (cm)"]
    + ["Air Flow (cm/s)", "Percent O2 (Note 1)", "Ignition Power (W)"]
)
SAFFIRE_RAW = (
    SAFFIRE_HEADER
    + """
2-5,Cotton-Fiberglass (SIBAL),0.25 mm,29 cm,5 cm,20 cm/s,~ 22.1,80 W
2-9,,0.25 mm,29 cm,5 cm,20 cm/s,22.0 to 21.9,80 W
F1C1/F1C2,Pre-test flow visulation data for sample 2-1,,,,,,
Note 1 Derived from measured CO2 production,,,,,,,
"""
)

BASS_HEADER = ",".join(
    ["PI", "Test #", "Date", "GMT", "Sample #", "Fuel Sample Material", "Flow restrictor"]
    + [
        "Fan display",
        "Air display",
        "Calibrated  initial O2 % by vol ",
        "Calibrated final O2 % by vol",
    ]
)
BASS_RAW = (
    BASS_HEADER
    + """
X,B1,2/19/2014,50,147,100 micron PMMA film   2 cm wide,2,62,5,22.2,22.2
X,B2,2/19/2014,50,155,1/4" clear rod,2,62,5  3  2  ext,21.0,20.1
X,B3,2/19/2014,50,155,SIBAL 1 cm,2,blowoff,10 20 (1.15 .5),18.5,18.4
X,B4,2/19/2014,50,155,Nomex,2,,down to ext from 8,17.0,16.9
X,B5,2/19/2014,50,155,0.2 mm PMMA slab,2,no ign,5,16.0,16.0
"""
)


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_flex_converts_units_and_reads_the_test_end(tmp_path):
    rows = clean_flex.clean(write(tmp_path, "flex.csv", FLEX_RAW))
    assert [r["test_id"] for r in rows] == ["FLEX-1", "FLEX-2", "FLEX-3"]  # empty row dropped
    assert rows[1]["o2_pct"] == 30.0  # mole fraction 0.3 x 100
    assert rows[1]["pressure_kpa"] == 101.32  # 760 mmHg
    assert rows[2]["pressure_kpa"] is None  # 0 mmHg = not recorded
    assert [r["outcome"] for r in rows] == ["unknown", "burned", "extinguished"]
    assert {r["flow_cm_s"] for r in rows} == {0.0}
    assert {r["fuel_type"] for r in rows} == {"droplet"}


def test_saffire2_keeps_only_samples(tmp_path):
    rows = clean_saffire2.clean(write(tmp_path, "saffire.csv", SAFFIRE_RAW))
    assert [r["test_id"] for r in rows] == ["Saffire-II-2-5", "Saffire-II-2-9"]
    assert rows[0]["o2_pct"] == 22.1 and rows[1]["o2_pct"] == 22.0  # starting value kept
    assert rows[0]["flow_cm_s"] == 20.0
    assert rows[1]["material"] == "unspecified"  # blank in the PSI table
    assert {r["outcome"] for r in rows} == {"unknown"}


def test_bass2_reads_airflow_notes(tmp_path):
    rows = {r["test_id"]: r for r in clean_bass2.clean(write(tmp_path, "bass.csv", BASS_RAW))}
    b1, b2, b3, b4, b5 = (rows[f"BASS-II-B{i}"] for i in range(1, 6))
    assert (b1["outcome"], b1["flow_cm_s"], b1["material"]) == ("unknown", 5.0, "PMMA film")
    assert (b2["outcome"], b2["flow_cm_s"], b2["material"]) == ("extinguished", 2.0, "PMMA rod")
    assert (b3["outcome"], b3["flow_cm_s"]) == ("extinguished", 20.0)  # blowoff at the top speed
    assert b3["material"] == "Cotton-Fiberglass (SIBAL)"
    assert (b4["outcome"], b4["flow_cm_s"]) == ("extinguished", None)  # lowest speed not written
    assert (b5["outcome"], b5["flow_cm_s"]) == ("unknown", 5.0)  # no ignition is not a verdict
    assert b2["o2_pct"] == 21.0 and b2["pressure_kpa"] is None


def test_bass2_rejects_an_unknown_sample():
    with pytest.raises(ValueError, match="unknown BASS-II sample"):
        clean_bass2.material("aluminium foil")


@pytest.mark.parametrize(
    "module, raw",
    [(clean_flex, FLEX_RAW), (clean_saffire2, SAFFIRE_RAW), (clean_bass2, BASS_RAW)],
)
def test_clean_csvs_have_the_unified_columns(tmp_path, module, raw):
    rows = module.clean(write(tmp_path, "raw.csv", raw))
    out = write_clean(rows, tmp_path / "clean.csv")
    with out.open() as f:
        written = list(csv.DictReader(f))
    assert list(written[0]) == COLUMNS
    for r in written:
        assert r["source_url"].startswith("https://psi.nasa.gov/")
        assert r["is_synthetic"] == "False"
        assert r["outcome"] in {"burned", "extinguished", "unknown"}
        assert r["o2_pct"] == "" or 0 <= float(r["o2_pct"]) <= 100
        assert r["flow_cm_s"] == "" or float(r["flow_cm_s"]) >= 0
