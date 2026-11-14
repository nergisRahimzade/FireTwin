import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import FireTwinApp from "./FireTwinApp";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <FireTwinApp />
  </StrictMode>,
);
