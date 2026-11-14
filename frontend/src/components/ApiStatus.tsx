import { useEffect } from "react";
import { API_BASE } from "../api/client";
import { useScenario } from "../store/useScenario";

// One health check on load, so a missing backend is obvious instead of a silent empty screen.
export function ApiStatus() {
  const apiUp = useScenario(s => s.apiUp);
  useEffect(() => { useScenario.getState().checkHealth(); }, []);
  if (apiUp) return null;
  return (
    <p role="status" className={`api-status ${apiUp === false ? "down" : "checking"}`}>
      {apiUp === null
        ? "Connecting to the FireTwin API…"
        : `The FireTwin API isn't reachable at ${API_BASE}. Start it with "make dev" (backend on port 8000).`}
    </p>
  );
}
