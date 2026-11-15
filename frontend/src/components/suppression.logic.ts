/* FE-08: when the suppression panel asks /suppress on its own. */
import type { Phase } from "../store/useScenario";

/** Rank actions once the alarm trips, if they aren't ranked or being ranked already. */
export function shouldAutoRank(alarmId: string | null, hasRanking: boolean, loading: boolean): boolean {
  return alarmId != null && !hasRanking && !loading;
}

/** A fire is still there to act on (Apply stays available after an action that failed). */
export function canAct(phase: Phase): boolean {
  return phase === "burning" || phase === "detected" || phase === "suppressing" || phase === "still_burning";
}
