/* Flame in Freefall: 3D ISS lab configuration (plain numbers, no three.js).
   Units are meters. Origin [0, 0, 0] is the module center.
   +x = fore (along the module), +y = overhead, +z = port, -z = starboard.

   The vent positions are the detector positions. If the backend ever runs the detection math
   (the guide's BE-03 detector config), it must use these same numbers, or smoke will visibly
   reach one vent while a different one trips the alarm. */
export const MODULE = { length: 8.5, diameter: 4.2, aisle: 1.38 }; // aisle = rack face distance from the axis
export const VENTS = [
  { id: "vent_1", pos: [3.55, 1.37, 0.0], normal: [0, -1, 0], where: "overhead, fore" },
  { id: "vent_2", pos: [-3.55, -1.37, 0.0], normal: [0, 1, 0], where: "deck, aft" },
  { id: "vent_3", pos: [0.55, 0.0, -1.37], normal: [0, 0, 1], where: "starboard wall" },
];
export const FIRE_POS = [-0.6, -0.3, 0.25];
export const AIRFLOW = [
  { id: "fore", label: "Fore (+x)", dir: [1, 0, 0], fans: true },
  { id: "aft", label: "Aft (−x)", dir: [-1, 0, 0], fans: true },
  { id: "starboard", label: "Starboard (−z)", dir: [0, 0, -1], fans: true },
  { id: "off", label: "Fans off", dir: [0, 0, 0], fans: false },
];
export const DETECT_RADIUS = 0.45; // smoke closer than this to a vent trips its detector
export const TIME_SCALE = 2.5; // the demo clock runs 2.5x real time
