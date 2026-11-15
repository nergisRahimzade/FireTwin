/* Compare mode: a NASA FLEX-2 droplet-flame video (right) and the 3D module set to that test's
   conditions (left), playing in step: the video's time decides whether the 3D flame is unlit, burning
   or out, so play, pause and skipping in the video all move the 3D with it. Below: the test's
   conditions with their sources, the model's verdict for them, the video timeline and the O2 chart.
   The 3D's timing follows the video; its flame size comes from the model (compareVideo.ts). */
import { Suspense, useEffect, useMemo } from "react";
import { useScenario } from "../store/useScenario";
import {
  IGNITION_S, MODEL_FUEL_NOTE, MODEL_INPUTS, PHASES, SOURCES, VIDEO, VIDEO_CONDITIONS, flameAt, formatTime,
  phaseAt, sceneVerdict,
} from "./compareVideo";
import { chartTested } from "./dashboard.logic";
import { O2Chart } from "./O2Chart";
import { IssScene } from "./SceneView";
import { useVideoModel, useYouTubePlayer } from "./useVideoReference";
import { ValidationReference } from "./ValidationReference";
import { VideoTimeline } from "./VideoTimeline";

const pct = (p: number) => `${Math.round(p * 100)}%`;

export function CompareView({ onClose }: { onClose: () => void }) {
  const meta = useScenario(s => s.meta);
  const setInputs = useScenario(s => s.setInputs);
  const ignite = useScenario(s => s.ignite);
  const player = useYouTubePlayer(VIDEO.id);
  const model = useVideoModel(meta);
  const flame = flameAt(player.time);
  // A new object only when the flame state changes (not on every time tick), so the 3D flame
  // grows or fades smoothly instead of restarting.
  const scene = useMemo(() => sceneVerdict(model.preview, flame), [model.preview, flame]);
  const { range: tested, scope } = chartTested(meta, MODEL_INPUTS);
  const fuel = meta?.materials.find(m => m.name === MODEL_INPUTS.material);
  const sinceIgnition = player.time - IGNITION_S;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Same values in the real simulator: the controls take them and Ignite records a session, with
  // the full verdict (explanation, nearest NASA tests) on the main page.
  const runAsSession = () => {
    setInputs(MODEL_INPUTS);
    void ignite();
    onClose();
  };

  return (
    <section className="compare-view" role="dialog" aria-modal="true" aria-label="Compare">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-2xl font-bold">Compare</h2>
        <button type="button" className="btn-ghost" onClick={onClose}>Back to simulation</button>
      </header>
      <div className="compare-panes">
        <div className="glass lab3d">
          <div className="lab3d-view">
            <div className="lab3d-canvas">
              <Suspense fallback={<div className="lab3d-msg">Loading the ISS module…</div>}>
                {/* No smoke: the video shows a droplet in a sealed chamber, and smoke can't be rewound. */}
                <IssScene detect={null} simulate={scene} smoke={false} />
              </Suspense>
            </div>
            <div className="lab3d-hud">
              <span className="clock mono" role="status">
                video {formatTime(player.time)} · {PHASES[phaseAt(player.time)].label}
                {sinceIgnition >= 0 ? ` · ${Math.floor(sinceIgnition)} s after ignition` : ""}
              </span>
            </div>
          </div>
        </div>
        <ValidationReference hostRef={player.hostRef} status={player.status} time={player.time} playing={player.playing} />
      </div>

      <VideoTimeline time={player.time} duration={player.duration} onSeek={player.status === "ready" ? player.seek : undefined} />

      <div className="compare-results">
        <div className="table-wrap">
          <table aria-label="The video's test">
            <thead><tr><th>The video's test</th><th>Value</th><th>Source</th></tr></thead>
            <tbody>
              {VIDEO_CONDITIONS.map(c => (
                <tr key={c.name}><td>{c.name}</td><td>{c.value}</td><td className="muted">{c.source}</td></tr>
              ))}
              <tr><td>What the video shows</td><td>Flame lit at 0:43, out at 1:03 (whether the droplet had burned up isn't stated)</td><td className="muted">{SOURCES.team}</td></tr>
            </tbody>
          </table>
        </div>

        <div className="glass panel compare-model">
          <h3 className="panel-title m-0">The model at these conditions</h3>
          <p className="note m-0">
            {MODEL_INPUTS.material}{fuel ? ` (${fuel.n_tests} NASA tests)` : ""}, {MODEL_INPUTS.o2_pct}% O₂,{" "}
            {MODEL_INPUTS.pressure_kpa} kPa, {MODEL_INPUTS.flow_speed_cm_s} cm/s. {MODEL_FUEL_NOTE}
          </p>
          {model.preview ? (
            <p className="m-0">
              <b className={model.preview.state === "burning" ? "state-burning" : "state-out"}>
                {model.preview.state === "burning" ? "Keeps burning" : "Goes out"}
              </b>{" "}
              <span className="mono">{pct(model.preview.burn_probability)} burn probability</span>{" "}
              <span className={`badge trust-${model.preview.trust}`}>trust: {model.preview.trust}</span>
              {model.preview.extrapolated && <span className="badge">outside tested range</span>}
              {model.preview.is_synthetic && <span className="badge badge-synth">synthetic</span>}
            </p>
          ) : (
            <p className="note m-0">{model.error ? `No model result: ${model.error}` : meta ? "Asking the model…" : "Waiting for the API…"}</p>
          )}
          <p className="note m-0">
            The model says whether a flame keeps burning or goes out, not when: the 3D's timing follows the video, and
            its flame size comes from this result.
          </p>
          <button type="button" className="btn-primary justify-self-start" disabled={!meta} onClick={runAsSession}>
            Run these settings as a session
          </button>
        </div>
      </div>

      {model.preview && model.curve && (
        <O2Chart
          inputs={MODEL_INPUTS} recorded={model.preview.burn_probability} sweep={model.curve}
          tested={tested} scope={scope} subject="video's conditions"
        />
      )}
    </section>
  );
}
