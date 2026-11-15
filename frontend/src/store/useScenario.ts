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

interface ScenarioData {
  inputs: ScenarioIn;
  meta: MetaOut | null;
  simulate: SimulateOut | null; // latest prediction (from /simulate or /apply)
  detect: DetectOut | null;
  suppress: SuppressOut | null;
  results: ResultsOut | null;
  history: SimulateOut[]; // every prediction in this scenario, in order
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
  chat: [],
  phase: "idle",
  ignitions: 0,
  ignitedAt: null,
  alarmId: null,
  loading: IDLE_LOADING,
  error: null,
};

export const useScenario = create<ScenarioStore>()((set, get) => {
  // Shared wrapper: sets the step's loading flag, records the error message, never throws.
  async function run<T>(step: Step, call: () => Promise<T>): Promise<T | null> {
    set(s => ({ loading: { ...s.loading, [step]: true }, error: null }));
    try {
      return await call();
    } catch (err) {
      set({ error: err instanceof Error ? err.message : String(err) });
      return null;
    } finally {
      set(s => ({ loading: { ...s.loading, [step]: false } }));
    }
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
    const { ignitions, ignitedAt } = get();
    const elapsed = ignitedAt == null ? 0 : (Date.now() - ignitedAt) / 1000;
    alarmTimer = setTimeout(() => {
      alarmTimer = null;
      if (get().ignitions === ignitions) set({ alarmId: id });
    }, Math.max(0, at - elapsed) * 1000);
  };
  const needScenario = () => {
    set({ error: "Ignite a scenario first." });
    return null;
  };

  return {
    ...initialScenario,

    setInputs: patch => set(s => ({ inputs: { ...s.inputs, ...patch } })),
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
      const res = await run("simulate", () => api.simulate(get().inputs));
      if (!res) return null;
      // A new scenario: earlier detection, actions and results no longer apply.
      clearAlarm();
      set(s => ({
        simulate: res, detect: null, suppress: null, results: null, history: [res], ignitions: s.ignitions + 1,
        ignitedAt: Date.now(), alarmId: null,
        phase: nextPhase(s.phase, { type: "simulated", state: res.state }),
      }));
      return res;
    },

    runDetect: async () => {
      const id = scenarioId();
      if (!id) return needScenario();
      const res = await run("detect", () => api.detect(id));
      if (res) {
        set(s => ({ detect: res, alarmId: null, phase: nextPhase(s.phase, { type: "detected", detected: res.detected }) }));
        scheduleAlarm(res);
      }
      return res;
    },

    runSuppress: async () => {
      const id = scenarioId();
      if (!id) return needScenario();
      const res = await run("suppress", () => api.suppress(id));
      if (res) set(s => ({ suppress: res, phase: nextPhase(s.phase, { type: "suppress_ranked" }) }));
      return res;
    },

    runApply: async action => {
      const id = scenarioId();
      if (!id) return needScenario();
      const res = await run("apply", () => api.apply(id, action));
      if (res) {
        set(s => ({
          simulate: res, history: [...s.history, res],
          phase: nextPhase(s.phase, { type: "applied", state: res.state }),
        }));
      }
      return res;
    },

    loadResults: async () => {
      const id = scenarioId();
      if (!id) return needScenario();
      const res = await run("results", () => api.results(id));
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
      clearAlarm();
      set(s => ({ ...initialScenario, inputs: s.inputs, meta: s.meta, chat: s.chat, ignitions: s.ignitions }));
    },
  };
});
