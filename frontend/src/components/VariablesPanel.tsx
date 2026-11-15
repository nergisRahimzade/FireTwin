/* Right-side controls stay visible on desktop and collapse behind a floating mobile toggle. */
import { useId, useState } from "react";
import { useScenario } from "../store/useScenario";
import { ControlPanel } from "./ControlPanel";

export function VariablesPanel() {
  const [open, setOpen] = useState(false); // only matters on mobile; desktop always shows the panel
  const bodyId = useId();
  const inputs = useScenario(s => s.inputs);
  return (
    <aside className="area-vars vars-panel" aria-label="Controls">
      <button
        type="button" className="collapsible-toggle glass" aria-expanded={open} aria-controls={bodyId}
        onClick={() => setOpen(o => !o)}
      >
        <span aria-hidden="true">⚙️</span>
        <b>Controls</b>
        <span className="note">{inputs.o2_pct}% O₂ · {inputs.flow_speed_cm_s} cm/s</span>
        <span aria-hidden="true">{open ? "▴" : "▾"}</span>
      </button>
      <div id={bodyId} className={`collapsible-body${open ? " open" : ""}`}>
        <ControlPanel />
      </div>
    </aside>
  );
}
