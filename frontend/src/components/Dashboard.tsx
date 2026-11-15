/* One-page layout: the data dashboard under the 3D view, with the whiteboard's columns
   (variable changed, result, date & time) and the Export button.
   Layout shell: FE-09 fills the rows from a timestamped timeline (updated on every variable change,
   with jump-back to past recordings) and adds the charts. Export: the backend serves PDF today
   (/export/{id}.pdf); DOCX and CSV wait on a team decision. */
import { api } from "../api/client";
import { useScenario } from "../store/useScenario";

export function Dashboard() {
  const scenarioId = useScenario(s => s.simulate?.scenario_id ?? null);
  const pdfUrl = scenarioId ? api.exportUrl(scenarioId) : null;
  return (
    <section className="area-dash glass panel" aria-label="Results dashboard">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="panel-title">Dashboard</h2>
        <div className="export-menu" role="group" aria-label="Export">
          {pdfUrl ? (
            <a className="btn-ghost" href={pdfUrl} target="_blank" rel="noreferrer">Export PDF</a>
          ) : (
            <button type="button" className="btn-ghost" disabled title="Run a scenario first">Export PDF</button>
          )}
          <button type="button" className="btn-ghost" disabled title="Not available yet">DOCX</button>
          <button type="button" className="btn-ghost" disabled title="Not available yet">CSV</button>
        </div>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>Variable changed</th><th>Result</th><th>Date &amp; time</th></tr>
          </thead>
          <tbody>
            <tr><td colSpan={3} className="na">Every result will be recorded here with its date and time.</td></tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}
