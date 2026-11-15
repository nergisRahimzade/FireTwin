/* FireTwin 3D configuration (plain numbers, no three.js). Matches the "3D coordinate system"
   section of docs/contract.md, the one frame shared with the backend detector (BE-03):
   metres, origin [0, 0, 0] at the module centre, +x = fore (the forward airflow direction),
   +y = overhead, +z = port. The fire is always at the module centre.

   The live scene draws detectors where POST /detect puts them (FE-04). VENTS below are the
   contract's positions, used by lab/core.js buildVents() and its smoke-model tests. */
export const MODULE = { length: 8.5, diameter: 4.2, aisle: 1.38 }; // aisle = rack face distance from the axis
export const VENTS = [
  { id: "vent_fwd", pos: [4.0, 1.37, 0.0], normal: [0, -1, 0], where: "overhead, fore end" },
  { id: "vent_aft", pos: [-4.0, 1.37, 0.0], normal: [0, -1, 0], where: "overhead, aft end" },
  { id: "vent_mid", pos: [0.0, 1.37, 0.0], normal: [0, -1, 0], where: "overhead, above the fire" },
];
export const FIRE_POS = [0, 0, 0];
export const AIRFLOW = [
  { id: "fore", label: "Fore (+x)", dir: [1, 0, 0], fans: true },
  { id: "aft", label: "Aft (−x)", dir: [-1, 0, 0], fans: true },
  { id: "off", label: "Fans off", dir: [0, 0, 0], fans: false },
];
export const DETECT_RADIUS = 0.45; // smoke closer than this to a vent trips its detector
export const TIME_SCALE = 2.5; // the demo clock runs 2.5x real time
