# Derived analysis policy

Similar-task lookup is deliberately conservative: normalized `task_type` is the match basis, and ordered actor/event types form a path signature. Results are candidates for human analysis, not a semantic identity claim — and never a ranking: output carries no best/score/rank fields.

Fewest steps is never "best". A future `BEST_KNOWN_PATH` claim must include source task/path IDs, method version, sample size, observation window, confidence and explicit treatment of adoption, quality, corrections, failures, recovery, human interventions, duration, cost, risk and prerequisites. It must be supersedable and must never erase historical alternatives. With small samples, the only honest statement is "insufficient data".

Derived knowledge lives only in the `derived_knowledge` layer with `lineage` back to raw records. v2 ships no derived-write API: nothing in this runtime can overwrite or decorate raw history with analysis results. Any future derived write path must record `sample_size`, `method_version`, `confidence` and source lineage.

Do not create Skill, automation or Agent implementations automatically. Produce reviewable candidates with lineage and seek separate authorization.
