// Compare video view, rendered: the 3D follows the video's time, and every shown value has a source.
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, expect, it, vi } from "vitest";
import type { MetaOut, PreviewOut, SimulateOut } from "../api/types";
import { MODEL_INPUTS } from "./compareVideo";
import { CompareView } from "./CompareView";

const meta: MetaOut = {
  materials: [{ name: "Heptane", fuel_type: "droplet", n_tests: 117 }],
  ranges: { o2_pct: { min: 12, max: 34 }, pressure_kpa: { min: 70.17, max: 309.27 }, flow_cm_s: { min: 0, max: 28 } },
  ranges_by_fuel_type: {
    droplet: { o2_pct: { min: 12, max: 34 }, pressure_kpa: { min: 70.17, max: 309.27 }, flow_cm_s: { min: 0, max: 0 } },
  },
  investigations: [],
};
const preview: PreviewOut = {
  state: "extinguished", burn_probability: 0.298, trust: "strong", extrapolated: false, is_synthetic: false, inputs: MODEL_INPUTS,
};

const view = vi.hoisted(() => ({
  store: {} as Record<string, unknown>,
  player: { status: "ready", time: 0, playing: true, duration: 95 } as Record<string, unknown>,
  model: { preview: null, curve: null, error: null } as Record<string, unknown>,
  scene: [] as { simulate: SimulateOut | null; smoke?: boolean }[], // every IssScene render's props
}));
vi.mock("../store/useScenario", () => ({
  useScenario: (select: (state: Record<string, unknown>) => unknown) => select(view.store),
}));
vi.mock("./SceneView", () => ({
  IssScene: (props: { simulate: SimulateOut | null; smoke?: boolean }) => { view.scene.push(props); return null; },
}));
vi.mock("./useVideoReference", () => ({
  useYouTubePlayer: () => ({ hostRef: { current: null }, seek: () => {}, ...view.player }),
  useVideoModel: () => view.model,
}));

const render = (time = 0) => {
  view.player.time = time;
  view.scene = [];
  return renderToStaticMarkup(<CompareView onClose={() => {}} />);
};

beforeEach(() => {
  view.store = { meta, setInputs: () => {}, ignite: async () => {} };
  view.model = { preview, curve: [[10, 0.03], [21, 0.298], [40, 0.95]], error: null };
});

it("shows no flame before ignition, burns from 0:43 and is out from 1:03, with no smoke", () => {
  render(20);
  expect(view.scene[0].simulate).toBeNull();
  expect(view.scene[0].smoke).toBe(false);
  render(50);
  expect(view.scene[0].simulate?.state).toBe("burning");
  expect(view.scene[0].simulate?.burn_probability).toBe(0.298); // flame sized by the model
  render(70);
  expect(view.scene[0].simulate?.state).toBe("extinguished");
});

it("says where the video is, in the 3D and on the timeline", () => {
  const html = render(50);
  expect(html).toContain("video 0:50 · Flame ball burning · 7 s after ignition");
  expect(html).toContain("Now at 0:50: Flame ball burning.");
});

it("lists the video's conditions with their sources", () => {
  const html = render();
  expect(html).toContain("50/50 mixture of iso-octane and heptane");
  expect(html).toContain("The video&#x27;s YouTube description (NASA Johnson)");
  expect(html).toContain("Timed by the team from the video");
});

it("shows the model's verdict for those conditions and says the fuel differs", () => {
  const html = render();
  expect(html).toContain("Heptane (117 NASA tests), 21% O₂, 101.3 kPa, 0 cm/s");
  expect(html).toContain("no iso-octane");
  expect(html).toContain("Goes out");
  expect(html).toContain("30% burn probability");
  expect(html).toContain("trust: strong");
  expect(html).toContain("video&#x27;s conditions: 21% → 30%"); // the O2 chart's point
});

it("waits honestly while the model hasn't answered", () => {
  view.model = { preview: null, curve: null, error: "API offline" };
  const html = render(50);
  expect(html).toContain("No model result: API offline");
  expect(view.scene[0].simulate).toBeNull(); // no made-up flame
  expect(html).not.toContain("o2-chart");
});
