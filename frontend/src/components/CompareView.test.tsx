import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, expect, it, vi } from "vitest";
import { DEFAULT_SCENARIO, type SimulateOut } from "../api/types";
import type { ScenarioStore } from "../store/useScenario";
import { CompareView } from "./CompareView";

const view = vi.hoisted(() => ({
  state: {} as Pick<ScenarioStore, "inputs" | "simulate" | "detect" | "ignitions" | "ignitedAt" | "alarmId">,
}));
vi.mock("../store/useScenario", () => ({
  useScenario: (select: (state: typeof view.state) => unknown) => select(view.state),
}));
vi.mock("./SceneView", () => ({ IssScene: () => null }));
vi.mock("./ValidationReference", () => ({ ValidationReference: () => null }));

const recorded: SimulateOut = {
  scenario_id: "synthetic-review", state: "burning", burn_probability: 0.9,
  spread_rate_mm_s: null, trust: "strong", extrapolated: false, nearest_tests: [], explanation: "",
  inputs: { ...DEFAULT_SCENARIO, material: "Synthetic review material" },
};
const render = () => renderToStaticMarkup(<CompareView onClose={() => {}} />);

beforeEach(() => {
  view.state = {
    simulate: recorded, inputs: { ...recorded.inputs, o2_pct: 40 },
    detect: null, ignitions: 1, ignitedAt: 0, alarmId: "synthetic-vent",
  };
});

it("labels edited controls as an unrecorded preview and identifies the alarm's source", () => {
  const html = render();
  expect(html).toContain("Preview of new settings");
  expect(html).toContain("Ignite again to record");
  expect(html).toContain("The alarm belongs to the recorded scenario.");
});

it("clears the preview notice when Apply or Ignite makes the controls match the record", () => {
  expect(render()).toContain("Preview of new settings");
  view.state.inputs = recorded.inputs;
  expect(render()).not.toContain("Preview of new settings");
});

it("clears the preview notice after Reset removes the scenario", () => {
  expect(render()).toContain("Preview of new settings");
  view.state.simulate = null;
  expect(render()).not.toContain("Preview of new settings");
});
