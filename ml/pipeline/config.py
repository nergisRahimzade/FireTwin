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
U0_CM_S = 0.5  # offset inside ln(u + u0) so zero flow is finite
FUEL_TYPES = ["solid", "droplet", "gas"]
BURN_THRESHOLD = 0.5  # state = burning if P(burn) >= this
MIN_ROWS_OPTION_B = 8  # per fuel_type, to fit the explicit boundary
MIN_ROWS_SPREAD = 15  # ML-02: fewer rows with a spread rate -> spread is None

# --- Nearest tests + trust (ML-04) ---
NEAREST_K = 3
TRUST_STRONG_DIST = 0.15
TRUST_STRONG_COUNT = 3
TRUST_MEDIUM_DIST = 0.30

# --- Detector (BE-03): ISS lab as a box, metres, origin at module centre, x along the axis ---
MODULE_LENGTH_M = 8.5
MODULE_DIAMETER_M = 4.2
FIRE_POSITION = (0.0, 0.0, 0.0)
DETECTORS = [
    {"id": "vent_aft", "position": (4.0, 1.5, 0.0)},
    {"id": "vent_fwd", "position": (-4.0, 1.5, 0.0)},
    {"id": "vent_mid", "position": (0.0, 2.0, 0.0)},
]
DIFFUSION_M2_S = 0.01  # plume spreading while fans mix the air (illustrative, not NASA data)
# Still air mixes far less than fan-driven air, so smoke creeps instead of spreading.
STILL_AIR_DIFFUSION_M2_S = 0.002  # illustrative, not NASA data
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
