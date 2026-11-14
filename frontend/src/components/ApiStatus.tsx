import { useEffect, useState } from "react";
import { API_BASE, api } from "../api/client";

// One health check on load, so a missing backend is obvious instead of a silent empty screen.
export function ApiStatus() {
  const [status, setStatus] = useState<"checking" | "up" | "down">("checking");
  useEffect(() => {
    let live = true;
    api.health().then(() => live && setStatus("up"), () => live && setStatus("down"));
    return () => { live = false; };
  }, []);
  if (status === "up") return null;
  return (
    <p role="status" className={`api-status ${status}`}>
      {status === "checking"
        ? "Connecting to the FireTwin API…"
        : `The FireTwin API isn't reachable at ${API_BASE}. Start it with "make dev" (backend on port 8000).`}
    </p>
  );
}
