import { useScenario } from "../store/useScenario";

export function ErrorToast() {
  const error = useScenario(s => s.error);
  const clearError = useScenario(s => s.clearError);

  if (!error) return null;

  return (
    <div className="error-toast" role="alert">
      <span>{error}</span>
      <button type="button" className="btn-ghost" onClick={clearError}>Dismiss</button>
    </div>
  );
}
