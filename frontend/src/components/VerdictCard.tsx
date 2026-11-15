/* FE-07: the model's verdict for the latest /simulate or /apply: state, burn probability, trust,
   extrapolation warning, explanation and the 3 nearest NASA tests. */
import { useScenario } from "../store/useScenario";
import { Sources } from "./Sources";

export function VerdictCard() {
  const sim = useScenario(s => s.simulate);
  if (!sim) return null;
  const burning = sim.state === "burning";
  return (
    <section className="glass panel verdict mt-3" aria-label="Verdict">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className={`panel-title m-0 ${burning ? "state-burning" : "state-out"}`}>
          {burning ? "Keeps burning" : "Extinguished"}
        </h2>
        <span className="mono">{Math.round(sim.burn_probability * 100)}% burn probability</span>
        <span className={`badge trust-${sim.trust}`}>trust: {sim.trust}</span>
      </div>
      {sim.extrapolated && (
        <p className="warn">Outside the tested NASA ranges: the model is extrapolating (no direct NASA data).</p>
      )}
      <p className="m-0">{sim.explanation}</p>
      <div className="flex flex-wrap items-center gap-2">
        <span className="label">Nearest NASA tests</span>
        <Sources sources={sim.nearest_tests} />
      </div>
    </section>
  );
}
