/* Type-level check (no runtime code): `tsc` fails here if the hand-written types in ./types drift
   from the backend contract generated into ./schema.d.ts. After changing schemas.py, run
   `npm run gen:api`, then fix whatever this file reports. */
import type { components } from "./schema";
import type * as T from "./types";

type S = components["schemas"];
type SameKeys<A, B> = [keyof A] extends [keyof B] ? ([keyof B] extends [keyof A] ? true : false) : false;
const same = <Ok extends true>() => undefined;
const fits = <Ours extends Theirs, Theirs>() => undefined;

// Every model has exactly the backend's fields.
same<SameKeys<T.TestRef, S["TestRef"]>>();
same<SameKeys<T.ScenarioIn, S["ScenarioIn"]>>();
same<SameKeys<T.SimulateOut, S["SimulateOut"]>>();
same<SameKeys<T.DetectOut, S["DetectOut"]>>();
same<SameKeys<T.ActionResult, S["ActionResult"]>>();
same<SameKeys<T.SuppressOut, S["SuppressOut"]>>();
same<SameKeys<T.ResultsOut, S["ResultsOut"]>>();
same<SameKeys<T.ChatOut, S["ChatOut"]>>();
same<SameKeys<T.MetaOut, S["MetaOut"]>>();
same<SameKeys<T.HealthOut, S["HealthOut"]>>();

// What we send is accepted by the backend as typed.
fits<T.ScenarioIn, S["ScenarioIn"]>();
fits<T.ActionName, S["ApplyIn"]["action"]>();
fits<T.SimulateOut, S["SimulateOut"]>();
fits<T.SuppressOut, S["SuppressOut"]>();
