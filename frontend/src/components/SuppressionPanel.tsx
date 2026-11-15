/* One-page layout: "Rec. of supp.", the ranked suppression actions under the 3D view.
   Layout shell: lists what /suppress returned. FE-08 adds the probability bars, data-support
   badges, sources and Apply. */
import { useScenario } from "../store/useScenario";

export function SuppressionPanel() {
  const suppress = useScenario(s => s.suppress);
  return (
    <section className="area-recs glass panel" aria-label="Suppression recommendations">
      <h2 className="panel-title">Suppression recommendations</h2>
      {suppress?.actions.length ? (
        <ol className="recs-list">
          {suppress.actions.map(a => (
            <li key={a.action} className={a.action === suppress.recommended ? "recommended" : ""}>
              <span>{a.label}</span>
              <span className="mono">{Math.round(a.extinction_probability * 100)}% out</span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="note m-0">Ranked actions (fans off, cut power, CO₂, water mist) appear here once the alarm trips.</p>
      )}
    </section>
  );
}
