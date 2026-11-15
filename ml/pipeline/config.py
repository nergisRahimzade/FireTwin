"""All tunable numbers for the ML pipeline in one place (model, trust, detector, suppression)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTS_PARQUET = ROOT / "data" / "processed" / "tests.parquet"
DOCS_DIR = ROOT / "data" / "docs"
ARTIFACTS_DIR = ROOT / "ml" / "artifacts"
MODEL_PATH = ARTIFACTS_DIR / "model.joblib"
RANGES_PATH = ARTIFACTS_DIR / "feature_ranges.json"
METRICS_PATH = ARTIFACTS_DIR / "metrics.json"
PHYSICS_PARAMS_PATH = ARTIFACTS_DIR / "physics_params.json"

# --- Physics-shaped model (A1) ---
# Solid-fuel tables (BASS-II in the MSG, Saffire in Cygnus) record no pressure. Those tests
# ran in cabin air, so the model ASSUMES one standard atmosphere for them. The table itself
# keeps the value empty, and metrics.json counts how many rows rely on this assumption.
NOMINAL_PRESSURE_KPA = 101.3
U0_CM_S = 0.5  # offset inside ln(u + u0) so zero flow is finite
FUEL_TYPES = ["solid", "droplet", "gas"]
MIN_ROWS_PER_FUEL = 10  # a fuel type needs this many labelled rows for its own model
MIN_MATERIAL_ROWS = 8  # a material gets its own term in the fuel model above this many rows
# A fuel model shows skill only if, out of fold, it beats always predicting the base rate
# (log loss) and ranks burned above extinguished (AUC). Without skill, trust is capped at weak.
SKILL_MIN_AUC = 0.65
SKILL_MIN_LOGLOSS_GAIN = 0.02  # log loss must be at least 2 % below the base-rate log loss
BURN_THRESHOLD = 0.5  # state = burning if P(burn) >= this
MIN_ROWS_OPTION_B = 8  # per fuel_type, to fit the explicit boundary
MIN_ROWS_SPREAD = 15  # ML-02: fewer rows with a spread rate -> spread is None

# --- Nearest tests + trust (ML-04) ---
NEAREST_K = 3
TRUST_STRONG_DIST = 0.15
TRUST_STRONG_COUNT = 3
TRUST_MEDIUM_DIST = 0.30
# ml/calibrate_trust.py measures how far a neighbour can be before it stops predicting the
# outcome, and writes the thresholds here. The values above are the fallback defaults.
TRUST_CALIBRATION_PATH = ARTIFACTS_DIR / "trust_calibration.json"
KNOWN_OUTCOMES = ("burned", "extinguished")  # only these tests can support a verdict

# --- Detector (BE-03): ISS lab as a box, metres, origin at module centre, x along the axis ---
MODULE_LENGTH_M = 8.5
MODULE_DIAMETER_M = 4.2
FIRE_POSITION = (0.0, 0.0, 0.0)
DETECTORS = [
    # Positions from the coordinate table in docs/contract.md (+x = fore). Changing one is
    # a contract change: update that table and the frontend's src/lab/config.js together.
    {"id": "vent_fwd", "position": (4.0, 1.37, 0.0)},
    {"id": "vent_aft", "position": (-4.0, 1.37, 0.0)},
    {"id": "vent_mid", "position": (0.0, 1.37, 0.0)},
]
DIFFUSION_M2_S = 0.01  # plume spreading while fans mix the air (illustrative, not NASA data)
# Still air mixes far less than fan-driven air, so smoke creeps instead of spreading.
STILL_AIR_DIFFUSION_M2_S = 0.001  # illustrative, not NASA data
PLUME_RADIUS_M = 0.3  # smoke plume radius at the source
# A vent is "downstream" when it lies within this angle of the airflow direction: cabin air
# leaves through the vents, so the flow carries smoke into a vent it points towards.
DOWNSTREAM_CONE_DEG = 30.0
DETECT_TIMEOUT_S = 300.0
NOTE_FANS_OFF = "fans off: smoke cannot reach vents"

# --- Suppression planning (BE-04, A2) ---
CO2_O2_DROP_PCT = 6.0
ACTION_LABELS = {
    "cut_power": "Cut power",
    "fans_off": "Fans off",
    "co2": "CO2 extinguisher",
    "water_mist": "Water mist",
}
# Crew risk per action, 0-1. Placeholders chosen by the team, NOT from NASA data.
CREW_RISK = {"cut_power": 0.05, "fans_off": 0.10, "co2": 0.40, "water_mist": 0.20}
NO_DATA_ACTIONS = {"water_mist"}  # no PSI data: data_support="none"
MAX_PLAN_STEPS = 3
CREW_RISK_WEIGHT = 0.5
DETECTION_DELAY_WEIGHT = 0.1
CREW_RISK_MAX = 0.6  # critic rejects plans above this

# --- Evidence (A2) ---
RETRIEVE_TOP_K = 3

# --- RAG store (ML-08) ---
INVESTIGATIONS_PATH = ROOT / "data" / "processed" / "investigations.json"
CHROMA_DIR = ROOT / "chroma_db"  # git-ignored; rebuild with `python ml/ingest_rag.py`
RAG_COLLECTION = "firetwin_docs"
RAG_CHUNK_WORDS = 500  # the plan says ~500 tokens; words are a close, simple stand-in
RAG_CHUNK_OVERLAP = 50
# Cosine distance above which a chunk is treated as not about the question.
RAG_MAX_DISTANCE = 0.75

# --- Physics-shaped fire simulation (ml/pipeline/fire_sim.py). Illustrative engineering values,
# not NASA measurements, except the spread rate, which is read from the Saffire-II table. ---
SIM_DURATION_S = 300.0
SIM_DT_S = 0.5
SIM_IGNITION_RADIUS_MM = 5.0  # flame size at ignition; smaller than this counts as out
SIM_MAX_FLAME_RADIUS_MM = 150.0  # the burning item's size: a flame cannot outgrow its fuel
SIM_DEFAULT_SPREAD_MM_S = 2.35  # used only if no test states a spread rate
SIM_SPREAD_REF_O2_PCT = 21.5  # O2 of the Saffire-II micro-g spread tests
SIM_FLAME_DECAY_S = 2.0  # how fast a flame that cannot survive shrinks
SIM_FAN_SPINDOWN_S = 5.0  # airflow time constant after fans off
SIM_CO2_MIXING_S = 10.0  # oxygen time constant after a CO2 discharge
SIM_STILL_AIR_CM_S = 0.5  # below this the air counts as still (slow diffusion)
SIM_SMOKE_PER_M2_S = 1.0  # smoke released per m^2 of flame per second (arbitrary units)
SIM_ALARM_CONCENTRATION = 0.002  # detector trips at this smoke concentration (same units)
