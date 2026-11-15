/* FE-02: the one store every tab reads. One action per API endpoint, plus the scenario state
   machine from the Project Overview: idle -> burning -> detected -> suppressing -> out | still burning.
   The model (API) decides every state; the 3D scene only illustrates it. */
import { create } from "zustand";
import { api } from "../api/client";
import type {
  ActionName, ChatOut, DetectOut, MetaOut, ResultsOut, ScenarioIn, SimulateOut, SuppressOut,
} from "../api/types";
import { DEFAULT_SCENARIO } from "../api/types";
import { alarmAfterS } from "../scene/alarmLogic";

export type Phase = "idle" | "burning" | "detected" | "suppressing" | "out" | "still_burning";

export type PhaseEvent =
  | { type: "simulated"; state: SimulateOut["state"] }
  | { type: "detected"; detected: boolean }
  | { type: "suppress_ranked" }
  | { type: "applied"; state: SimulateOut["state"] }
  | { type: "reset" };

// Pure, so the demo's state flow is predictable and unit-tested.
export function nextPhase(phase: Phase, ev: PhaseEvent): Phase {
  switch (ev.type) {
    case "reset":
      return "idle";
    case "simulated":
      return ev.state === "burning" ? "burning" : "out";
    case "detected":
      // A fire the vents never see (e.g. fans off) keeps burning undetected.
      return phase === "burning" && ev.detected ? "detected" : phase;
    case "suppress_ranked":
      return phase === "burning" || phase === "detected" || phase === "still_burning" ? "suppressing" : phase;
    case "applied":
      return ev.state === "extinguished" ? "out" : "still_burning";
  }
}

export type Step = "meta" | "simulate" | "detect" | "suppress" | "apply" | "results" | "chat";
export interface ChatTurn { question: string; reply: ChatOut }
export interface TimelineEvent {
  at: number;
  variable: string;
  action: "used" | "modified" | "removed";
  from: string | null;
  value: string | null;
  context: string;
}

const TRACKED_INPUTS = ["material", "o2_pct", "pressure_kpa", "flow_speed_cm_s", "flow_dir"] as const;
type TrackedInput = typeof TRACKED_INPUTS[number];
const INPUT_LABELS: Record<TrackedInput, string> = {
  material: "Material", o2_pct: "Oxygen", pressure_kpa: "Cabin pressure",
  flow_speed_cm_s: "Airflow speed", flow_dir: "Airflow direction",
};
const inputValue = (key: TrackedInput, value: unknown) =>
  key === "flow_dir" && Array.isArray(value) ? value.join(", ") : String(value);
const recordInputs = (inputs: ScenarioIn, action: TimelineEvent["action"], context: string, at = Date.now()) =>
  TRACKED_INPUTS.map(key => ({
    at, variable: INPUT_LABELS[key], action, from: null,
    value: inputValue(key, inputs[key]), context,
  }));

interface ScenarioData {
  inputs: ScenarioIn;
  meta: MetaOut | null;
  simulate: SimulateOut | null; // latest prediction (from /simulate or /apply)
  detect: DetectOut | null;
  suppress: SuppressOut | null;
  results: ResultsOut | null;
  history: SimulateOut[]; // every prediction in this scenario, in order
  timeline: TimelineEvent[]; // variable edits and uses across this browser session
  chat: ChatTurn[];
  phase: Phase;
  // Frontend ignition counter: +1 on every successful /simulate (not /apply). The 3D scene restarts its
  // smoke and demo clock when it changes, even if the backend reuses a scenario_id (the BE-06 mock does).
  ignitions: number;
  // FE-06: set once per ignition and shared by every 3D view, so switching to Compare and back
  // neither restarts the demo clock nor fires the alarm again.
  ignitedAt: number | null; // Date.now() when this ignition's /simulate returned
  alarmId: string | null; // the detector that tripped, once the demo clock reached time_to_detect_s
  loading: Record<Step, boolean>;
  error: string | null;
}

interface ScenarioActions {
  setInputs: (patch: Partial<ScenarioIn>) => void;
  clearError: () => void;
  loadMeta: () => Promise<void>; // GET /meta
  runSimulate: () => Promise<SimulateOut | null>; // POST /simulate
  runDetect: () => Promise<DetectOut | null>; // POST /detect
  runSuppress: () => Promise<SuppressOut | null>; // POST /suppress
  runApply: (action: ActionName) => Promise<SimulateOut | null>; // POST /apply
  loadResults: () => Promise<ResultsOut | null>; // GET /results/{id}
  ask: (message: string) => Promise<ChatOut | null>; // POST /chat
  ignite: () => Promise<void>; // FE-03: /simulate, then /detect if the fire keeps burning
  reset: () => void;
}

export type ScenarioStore = ScenarioData & ScenarioActions;

const IDLE_LOADING: Record<Step, boolean> = {
  meta: false, simulate: false, detect: false, suppress: false, apply: false, results: false, chat: false,
};

export const initialScenario: ScenarioData = {
  inputs: DEFAULT_SCENARIO,
  meta: null,
  simulate: null,
  detect: null,
  suppress: null,
  results: null,
  history: [],
  timeline: [],
  chat: [],
  phase: "idle",
  ignitions: 0,
  ignitedAt: null,
  alarmId: null,
  loading: IDLE_LOADING,
  error: null,
};

export const useScenario = create<ScenarioStore>()((set, get) => {
  // Late replies (review fix): every scenario call notes the epoch before it is sent and drops the
  // reply if the epoch has moved. Reset and each new ignition move it, so a /detect, /suppress,
  // /apply or /results reply that arrives after Reset (or after the next Ignite) never lands. resets
  // moves only on Reset: a /simulate reply is dropped if Reset came while it was in flight.
  let epoch = 0;
  let resets = 0;

  // Shared wrapper: sets the step's loading flag, records the error message, never throws.
  // A request that is no longer current (isCurrent() false) doesn't report its error either.
  async function run<T>(step: Step, call: () => Promise<T>, isCurrent: () => boolean = () => true): Promise<T | null> {
    set(s => ({ loading: { ...s.loading, [step]: true }, error: null }));
    try {
      return await call();
    } catch (err) {
      if (isCurrent()) set({ error: err instanceof Error ? err.message : String(err) });
      return null;
    } finally {
      set(s => ({ loading: { ...s.loading, [step]: false } }));
    }
  }
  // Runs a call for the current ignition; returns null (ignored) if the epoch moved meanwhile.
  async function runCurrent<T>(step: Step, call: () => Promise<T>): Promise<T | null> {
    const sent = epoch;
    const res = await run(step, call, () => epoch === sent);
    return epoch === sent ? res : null;
  }
  const scenarioId = () => get().simulate?.scenario_id ?? null;

  // FE-06 alarm: one timer per /detect result, owned by the store (not a component), so it survives
  // views mounting and unmounting. It fires at time_to_detect_s on the 10x demo clock, counted from
  // ignitedAt, and only if the same ignition is still current.
  let alarmTimer: ReturnType<typeof setTimeout> | null = null;
  const clearAlarm = () => {
    if (alarmTimer !== null) clearTimeout(alarmTimer);
    alarmTimer = null;
  };
  const scheduleAlarm = (detect: DetectOut) => {
    clearAlarm();
    const at = alarmAfterS(detect);
    const id = detect.detector_id;
    if (at == null || !id) return;
    const { ignitedAt } = get();
    const scheduledIn = epoch;
    const elapsed = ignitedAt == null ? 0 : (Date.now() - ignitedAt) / 1000;
    alarmTimer = setTimeout(() => {
      alarmTimer = null;
      if (epoch === scheduledIn) set({ alarmId: id });
    }, Math.max(0, at - elapsed) * 1000);
  };
  const needScenario = () => {
    set({ error: "Ignite a scenario first." });
    return null;
  };

  return {
    ...initialScenario,

    setInputs: patch => set(s => {
      const inputs = { ...s.inputs, ...patch };
      const at = Date.now();
      const changes = TRACKED_INPUTS.filter(key => patch[key] !== undefined && !Object.is(s.inputs[key], inputs[key]));
      const timeline = changes.map(key => ({
        at, variable: INPUT_LABELS[key], action: inputs[key] == null || inputs[key] === "" ? "removed" as const : "modified" as const,
        from: inputValue(key, s.inputs[key]), value: inputs[key] == null || inputs[key] === "" ? null : inputValue(key, inputs[key]),
        context: "Control panel",
      }));
      return { inputs, timeline: [...s.timeline, ...timeline] };
    }),
    clearError: () => set({ error: null }),

    loadMeta: async () => {
      const meta = await run("meta", api.meta);
      if (!meta) return;
      set(s => ({
        meta,
        // Pick the first material when none is chosen yet, so Ignite works straight away.
        inputs: s.inputs.material || !meta.materials.length ? s.inputs : { ...s.inputs, material: meta.materials[0].name },
      }));
    },

    runSimulate: async () => {
      const resetsAtSend = resets;
      const inputs = get().inputs;
      const previousInputs = get().simulate?.inputs ?? null;
      const usedAt = Date.now();
      const res = await run("simulate", () => api.simulate(inputs), () => resets === resetsAtSend);
      if (!res || resets !== resetsAtSend) return null; // Reset while in flight: drop the late reply
      // A new scenario: earlier detection, actions and results no longer apply.
      epoch++;
      clearAlarm();
      set(s => ({
        simulate: res, detect: null, suppress: null, results: null, history: [res], ignitions: s.ignitions + 1,
        timeline: [
          ...s.timeline,
          ...(previousInputs ? recordInputs(previousInputs, "removed", "Previous scenario replaced by Ignite", usedAt) : []),
          ...recordInputs(inputs, "used", "Ignite", usedAt),
        ],
        ignitedAt: Date.now(), alarmId: null,
        phase: nextPhase(s.phase, { type: "simulated", state: res.state }),
      }));
      return res;
    },

    runDetect: async () => {
      const id = scenarioId();
      if (!id) return needScenario();
      const res = await runCurrent("detect", () => api.detect(id));
      if (res) {
        set(s => ({ detect: res, alarmId: null, phase: nextPhase(s.phase, { type: "detected", detected: res.detected }) }));
        scheduleAlarm(res);
      }
      return res;
    },

    runSuppress: async () => {
      const id = scenarioId();
      if (!id) return needScenario();
      const sent = epoch;
      // Save the ranking inside the call, before run() clears loading.suppress. Saving it after
      // left a moment of "alarm, no ranking, not loading", and SuppressionPanel's auto-rank effect
      // then sent a second /suppress for the same alarm.
      return runCurrent("suppress", async () => {
        const res = await api.suppress(id);
        if (epoch === sent) set(s => ({ suppress: res, phase: nextPhase(s.phase, { type: "suppress_ranked" }) }));
        return res;
      });
    },

    runApply: async action => {
      const id = scenarioId();
      if (!id) return needScenario();
      const previousInputs = get().simulate?.inputs ?? null;
      const res = await runCurrent("apply", () => api.apply(id, action));
      if (res) {
        set(s => ({
          simulate: res, history: [...s.history, res],
          timeline: [
            ...s.timeline,
            ...(previousInputs ? TRACKED_INPUTS.filter(key => !Object.is(previousInputs[key], res.inputs[key])).map(key => ({
              at: Date.now(), variable: INPUT_LABELS[key], action: "modified" as const,
              from: inputValue(key, previousInputs[key]), value: inputValue(key, res.inputs[key]), context: `Apply ${action}`,
            })) : []),
            ...recordInputs(res.inputs, "used", `Apply ${action}`),
          ],
          phase: nextPhase(s.phase, { type: "applied", state: res.state }),
        }));
      }
      return res;
    },

    loadResults: async () => {
      const id = scenarioId();
      if (!id) return needScenario();
      const res = await runCurrent("results", () => api.results(id));
      if (res) set({ results: res });
      return res;
    },

    ask: async message => {
      const res = await run("chat", () => api.chat(message, scenarioId() ?? undefined));
      if (res) set(s => ({ chat: [...s.chat, { question: message, reply: res }] }));
      return res;
    },

    ignite: async () => {
      const sim = await get().runSimulate();
      if (sim?.state === "burning") await get().runDetect();
    },

    // Keeps the chosen inputs and the loaded /meta, so the user can rerun the loop at once.
    // ignitions keeps counting, so the next Ignite after a Reset is always a new ignition.
    reset: () => {
      const activeInputs = get().simulate?.inputs ?? null;
      epoch++; // in-flight scenario replies are now stale
      resets++;
      clearAlarm();
      set(s => ({
        ...initialScenario, inputs: s.inputs, meta: s.meta, chat: s.chat, ignitions: s.ignitions,
        timeline: [...s.timeline, ...(activeInputs ? recordInputs(activeInputs, "removed", "Scenario reset; removed from active run", Date.now()) : [])],
      }));
    },
  };
});
