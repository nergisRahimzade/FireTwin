/* FE-03: control panel. Material from /meta, sliders for O2, flow speed and (collapsed) pressure,
   flow direction, and Ignite (/simulate, then /detect). The tested range from /meta is shaded on
   each slider, and values outside it are flagged before anyone ignites. */
import { useEffect, useId, useState } from "react";
import { useScenario, type Phase } from "../store/useScenario";
import {
  FLOW_DIRS, LIMITS, TYPED_STEP, bandPercent, igniteBlocker, isOutside, outsideKeys, parseTyped, sameDir, testedRange,
  type SliderKey,
} from "./controlPanel.logic";

const PHASE_LABEL: Record<Phase, string> = {
  idle: "Ready", burning: "Burning", detected: "Alarm tripped", suppressing: "Choosing an action",
  out: "Fire out", still_burning: "Still burning",
};

function Slider({ field, label }: { field: SliderKey; label: string }) {
  const id = useId();
  const value = useScenario(s => s.inputs[field]);
  const meta = useScenario(s => s.meta);
  const setInputs = useScenario(s => s.setInputs);
  const { min, max, step, unit } = LIMITS[field];
  const tested = testedRange(meta, field);
  const band = tested && bandPercent(tested, field);
  const outside = isOutside(value, tested);
  const fill = ((value - min) / (max - min)) * 100;
  // Number box next to the slider (whiteboard: "sliders & number inputs"). Local text, so typing
  // "3" on the way to "34" isn't snapped to the minimum; a valid number updates the store at once.
  const [text, setText] = useState(String(value));
  useEffect(() => setText(String(value)), [value]);
  return (
    <div className="field">
      <div className="flex items-center justify-between gap-3">
        <label className="label" htmlFor={id}>{label}</label>
        <span className={`num-input${outside ? " outside" : ""}`}>
          <input
            type="number" inputMode="decimal" min={min} max={max} step={TYPED_STEP} value={text}
            aria-label={`${label} (${unit})`}
            onChange={e => {
              setText(e.target.value);
              const typed = parseTyped(field, e.target.value);
              if (typed !== null && typed === Number(e.target.value)) setInputs({ [field]: typed });
            }}
            onBlur={() => {
              const typed = parseTyped(field, text);
              if (typed === null) setText(String(value));
              else { setInputs({ [field]: typed }); setText(String(typed)); }
            }}
          />
          <span className="mono">{unit}</span>
        </span>
      </div>
      <div className="range single">
        <div className="track">
          {band && <span className="band" style={{ left: `${band.left}%`, right: `${band.right}%` }} />}
          <i style={{ left: 0, right: `${100 - fill}%` }} />
        </div>
        <input
          id={id} type="range" min={min} max={max} step={step} value={value}
          aria-valuetext={`${value} ${unit}${outside ? ", outside the tested range" : ""}`}
          onChange={e => setInputs({ [field]: Number(e.target.value) })}
        />
      </div>
      <span className="note">
        {tested
          ? outside
            ? `Outside tested range (${tested.min}–${tested.max} ${unit}): no direct NASA data.`
            : `Tested range ${tested.min}–${tested.max} ${unit} (shaded).`
          : "Tested range appears once the API is connected."}
      </span>
    </div>
  );
}

export function ControlPanel() {
  const inputs = useScenario(s => s.inputs);
  const meta = useScenario(s => s.meta);
  const phase = useScenario(s => s.phase);
  const error = useScenario(s => s.error);
  const busy = useScenario(s => s.loading.simulate || s.loading.detect);
  const loadingMeta = useScenario(s => s.loading.meta);
  const { setInputs, loadMeta, ignite, reset } = useScenario.getState();

  useEffect(() => { if (!useScenario.getState().meta) loadMeta(); }, [loadMeta]);

  const blocker = igniteBlocker(inputs, meta, busy);
  const outside = outsideKeys(inputs, meta);
  const materialId = useId();

  return (
    <form className="glass control-panel" onSubmit={e => { e.preventDefault(); if (!blocker) ignite(); }}>
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">Set up the fire</h2>
        <span className={`phase phase-${phase}`}>{PHASE_LABEL[phase]}</span>
      </div>

      <div className="field">
        <label className="label" htmlFor={materialId}>Material</label>
        <select
          id={materialId} className="sel" value={inputs.material} disabled={!meta?.materials.length}
          onChange={e => setInputs({ material: e.target.value })}
        >
          {!meta && <option value="">{loadingMeta ? "Loading materials…" : "No materials (API offline)"}</option>}
          {meta && !inputs.material && <option value="">Choose a material</option>}
          {meta?.materials.map(m => (
            <option key={m.name} value={m.name}>{m.name} · {m.fuel_type} · {m.n_tests} NASA tests</option>
          ))}
        </select>
        {!meta && !loadingMeta && (
          <button type="button" className="textbtn justify-self-start" onClick={() => loadMeta()}>Try again</button>
        )}
      </div>

      <Slider field="o2_pct" label="Oxygen" />
      <Slider field="flow_speed_cm_s" label="Airflow speed" />

      <fieldset className="field">
        <legend className="label">Airflow direction</legend>
        <div className="dir-grid" role="group">
          {FLOW_DIRS.map(d => (
            <button
              key={d.label} type="button" aria-pressed={sameDir(inputs.flow_dir, d.dir)}
              onClick={() => setInputs({ flow_dir: d.dir })}
            >
              <b>{d.label}</b> <span>{d.hint}</span>
            </button>
          ))}
        </div>
        {inputs.flow_speed_cm_s === 0 && <span className="note">Fans off: in microgravity, nothing carries the smoke.</span>}
      </fieldset>

      <details className="field">
        <summary className="label">Pressure (optional)</summary>
        <Slider field="pressure_kpa" label="Cabin pressure" />
      </details>

      {outside.length > 0 && (
        <p className="warn" role="status">
          Outside the tested range for {outside.map(k => ({ o2_pct: "oxygen", flow_speed_cm_s: "airflow", pressure_kpa: "pressure" })[k]).join(" and ")}.
          The model will extrapolate, so treat the verdict as having no direct NASA data.
        </p>
      )}
      {error && <p className="error" role="alert">{error}</p>}

      <div className="flex flex-wrap items-center gap-3">
        <button type="submit" className="btn-primary" disabled={!!blocker}>
          {busy ? "Igniting…" : phase === "idle" ? "Ignite" : "Ignite again"}
        </button>
        {phase !== "idle" && <button type="button" className="btn-ghost" onClick={reset}>Reset</button>}
        {blocker && !busy && <span className="note">{blocker}</span>}
      </div>
    </form>
  );
}
