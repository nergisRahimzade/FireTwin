import { StrictMode, Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import FireTwinApp from "./FireTwinApp";

// The earlier "Flame in Freefall Concepts" prototype stays reachable at ?prototype while the
// FireTwin tabs are built. It reads bundled data, not the API, so it is not the real app.
const Prototype = lazy(() => import("./App.js"));
const showPrototype = new URLSearchParams(window.location.search).has("prototype");

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {showPrototype ? (
      <Suspense fallback={null}>
        <Prototype />
      </Suspense>
    ) : (
      <FireTwinApp />
    )}
  </StrictMode>,
);
