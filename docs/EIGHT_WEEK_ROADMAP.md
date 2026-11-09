# Eight-week learning and extension roadmap

The project files already implement the core pipeline and deliverables. This is a suggested **8–12 hours/week** roadmap to understand, reproduce, extend and prepare to present the work. It is an estimate for independent study, not a claim about time spent producing these files.

| Week | Focus | Concrete evidence of mastery |
|---|---|---|
| 1 | Business framing and source audit | Rebuild from raw bytes; explain event, offer and application grains; write your own endpoint rationale |
| 2 | SQL data model | Recreate the marts; demonstrate a deliberately incorrect many-to-many join and prove why totals inflate |
| 3 | Temporal process analysis | Trace five applications by hand; reconcile every interval; explain repeat states, ties and unresolved cases |
| 4 | Dashboard and segmentation | Rebuild charts from SQL outputs; add one justified segment; audit counts and denominators after every filter |
| 5 | Statistics and uncertainty | Reproduce the bootstrap and Kaplan–Meier outputs; compare endpoint mixes; investigate calendar-clustered uncertainty |
| 6 | Landmark modeling | Reproduce baseline and model results; explain leakage prevention; run a new preregistered experiment on a separately reserved cohort |
| 7 | Decision economics and experiment design | Gather defensible intervention-cost assumptions; estimate an effect worth detecting; calculate sample size and specify guardrails |
| 8 | Polish and defense | Record a three-minute demo, publish approved materials, rewrite the README in your voice and practice the SQL/interview walkthrough |

## Strong extensions after the delivered baseline

1. **Calendar robustness:** Add month-block uncertainty or rolling-origin evaluation. Clearly separate exploratory backtests from the already-used final holdout.
2. **Point-in-time field audit:** Compare the model with and without source trace attributes whose revision history is unavailable. Document the availability assumption.
3. **Outcome-specific warning:** Distinguish long cancellation journeys from delayed pending endpoints. Formulate the new target before inspecting new holdout results.
4. **Historical replay:** Add weekly queue snapshots and score cases from event histories at each snapshot, preserving the original seven-day landmark contract or explicitly defining a new dynamic model.
5. **Operational semantics:** Review official event descriptions and manually inspect transitions to refine state interpretation. Do not translate elapsed intervals into labor cost without evidence.
6. **Pilot economics:** Model intervention cost against a stakeholder-defined value of a worthwhile outcome. Label assumptions and show break-even sensitivity; never infer actual revenue or staffing cost from absent fields.

Avoid adding infrastructure purely to enlarge the stack. Each extension should answer a new question or address an identified limitation.
