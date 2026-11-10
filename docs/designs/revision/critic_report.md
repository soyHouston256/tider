# Goldfish Review Report

**Target:** `/Users/maxhoustonramirezmartel/code/utec/5/integrador/project/code/tider/docs/designs/tider-diseno-piloto.md` (lines 1-444)
**Stage:** 7 (Critic Review), Mode: REVIEW
**Standard:** `resources/document_standards/feature-spec-standard.md` (egm-design, egm-structural); persona defaults, judged in Spanish (egm-style)

## Reviewer Status

| Reviewer | Status | Raw findings |
| --- | --- | --- |
| `egm-design` | completed | 20 Major, 7 Nit |
| `egm-structural` | completed | 5 Major, 9 Nit |
| `egm-style` | completed | 12 Major, 12 Nit |

No reviewer accessed `ground_truth/` or `ENTREGA_*`. After deduplication: **0 Blocker, 27 Major, 18 Nit**. Where several lenses reported the same issue, the lens column lists all of them.

---

## Prioritized Findings (Blockers -> Major -> Nits)

No Blockers were raised.

### Major

### M1. CUJ 2 contradicts the "sano confirmado" predicate - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-style`
* **Affected Scope:** Lines 108-112, 126 (also 49)
* **Discrepancy Description**: CUJ 2 ends with `redis-cart` "sano confirmado, aunque los errores lo nombran". Predicate condition 2 (line 110) requires that no caller has errors naming it. Condition 3 (line 111) requires traffic, and under wrong_port no traffic reaches redis-cart. Under the document's own rules, redis-cart comes out as `sin_datos`, so the CUJ's "Then" can't be reached.
* **Rationale & Recommendation**: Either change CUJ 2 to expect `sin_datos`, or redefine condition 2. One option: errors that name a destination count against it only when the destination shows its own platform anomaly, not when a confirmed Cambio in the caller explains them. Add a truth-table test for this case.

### M2. The "sano confirmado" predicate fails on baseline noise, nested errors and traffic attribution - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-style`
* **Affected Scope:** Lines 108-112, 197, 202
* **Discrepancy Description**:
  - **Baseline noise:** "Cero errores propios" never holds for paymentservice, because RB-01 and PM-04 document recurring noise in it (UnacceptedCreditCard/Code(400), DeprecationWarning logged at ERROR).
  - **Nested errors:** checkoutservice, a real victim, writes nothing at WARNING or above. Its failure appears only nested inside frontend's error, so it could be painted sano.
  - **Traffic attribution:** "líneas de actividad normal ... de sus llamadores" (111) has no rule for attributing a line to a service.
  - **Undefined terms:** "anomalía respecto de la línea base" (197) and "patrón de laboratorio u observabilidad" (202) have no operational definition.
* **Rationale & Recommendation**: Restate the predicate as "sin anomalía sobre la línea base, excluyendo plantillas de ruido conocidas". Name the severities that count (RB-01 recommends >= WARNING). Add an explicit rule for nested error chains. Source per-service traffic and error patterns from the fichas, and define each of these terms or point to where it is defined.

### M3. Line 27 and CUJ 1 overstate checkoutservice's own errors - Severity: Major
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** Lines 27, 120
* **Discrepancy Description**: Line 27 names checkoutservice among the services that "más registran errores", and CUJ 1 cites "sus errores". RB-01 (line 60) says checkoutservice logged nothing at WARNING or above in all 5 historical runs. Its evidence is nested inside frontend's errors.
* **Rationale & Recommendation**: Base the line 27 example on PM-02 data. In CUJ 1, describe checkout's evidence as the nested error that frontend logs.

### M4. The recorder doesn't capture Services, so ClusterIP:port errors can't be resolved - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** Lines 120, 179, 204-205
* **Discrepancy Description**: RB-01 (lines 46-55) shows that caller errors name `ClusterIP:port`, and that a port alone is ambiguous: 50051 is both payment and shipping, and 6379 is both redis-cart and chaosforge-proxy. The recorder snapshots Deployments, StatefulSets, EndpointSlices and Pods, but not Services. Without ClusterIPs the Cartógrafo can't build observed edges, and CUJ 1's victim attribution can't be done. Nested errors would also create spurious observed edges (for example frontend->paymentservice), which become false discrepancies.
* **Rationale & Recommendation**: Add Services (ClusterIP and ports) to the snapshot. Specify how an IP is resolved to a Service, with the rule "never attribute by port alone". Specify how nested error chains are attributed to the right edge.

### M5. A latency injection can confirm "configuración incorrecta" - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** Lines 80-83, 126, 184, 205
* **Discrepancy Description**: A latency injection shows up as `REDIS_ADDR=chaosforge-proxy:6379`, a change to a `*_ADDR` variable that comes before the errors. That satisfies the rule "cambio de configuración precede al primer error" (decision 21), so both signatures confirm and the LLM ordering decides between them. Codex (VALIDACION_CODEX.md line 68) already warned that temporal precedence is not causation.
* **Rationale & Recommendation**: Give "configuración incorrecta" a discard predicate for a redirect to a reachable proxy that keeps answering. Add these as near-miss negative cases in the Goal 3 validation matrix (line 50).

### M6. Ground-truth isolation covers only the HTTP admin route - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-style`
* **Affected Scope:** Lines 56, 184, 192, 205, 296-297, 432
* **Discrepancy Description**: The test at line 297 only checks that "ninguna URL configurable apunte al puerto de administración". Goal 9 promises that no Tider tool can reach the evidence route. Several other channels can reveal the injection:
  - the namespace-wide read-only k8s event sweep, which sees ChaosForge objects, annotations and the proxy Deployment;
  - ChaosForge controller logs in the same Cloud Logging project;
  - the proxy env var, which the Cartógrafo deliberately reports;
  - the observer latency payload.

  Codex (line 74) makes the same point.
* **Rationale & Recommendation**: Inventory every readable channel (RBAC scope, log filters, observer fields). Exclude or label ChaosForge-owned resources. Add a test that searches prompts and traces for experiment ids and mechanism names. Otherwise, narrow Goal 9 to what the test actually proves.

### M7. The hypothesis contract can't express victims or link causes - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-style`
* **Affected Scope:** Lines 80, 230-241, 256, 271
* **Discrepancy Description**:
  - **Victims:** `firma_id` may be null only when `razon = desconocida`, and the Investigator may use only CONFIRMED signatures. So a victim hypothesis (`rol victima`) can't be expressed validly. It is also unclear whether victims are hypotheses or only `Nodo.rol_en_principal`.
  - **Links:** `Arista.estado` has no domain, so Judge rule 2 ("entidad en estado falla") is undefined for the latency link cause.
  - **Reasons without signatures:** `se-cae-al-arrancar` and `sin-memoria` have no executable signature in catalog v1 (lines 233-235).
* **Rationale & Recommendation**: Decide that hypotheses carry only causes (victims become node roles), or allow victim hypotheses with the cause's `firma_id`. Define the values of `Arista.estado` and how rule 2 applies to links. Say what the two reasons without a signature point to.

### M8. The verdict on a conflict is not stated - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-style`, `egm-structural`
* **Affected Scope:** Line 214
* **Discrepancy Description**: "precedencia SIN_DATOS -> DESCARTADA -> CONFIRMADA, y la marca conflicto..." doesn't say whether the arrow means "beats" or "is evaluated first", or which verdict a conflict produces. The RFC (lines 497 and 556) and decision 27.4 say DESCARTADA with the conflicto mark. An implementation could legally emit CONFIRMADA plus conflicto.
* **Rationale & Recommendation**: State the rule as an ordered list:
  1. If a required field is missing: SIN_DATOS.
  2. Otherwise, if a discard condition holds: DESCARTADA, marked `conflicto` if the required conditions also hold.
  3. Otherwise: CONFIRMADA.

### M9. LLM ordering of signatures: weak rejection rationale, weak Judge check, no aggregation rule - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** Lines 80-83, 101, 272, 372-375
* **Discrepancy Description**:
  - **Rationale:** Alternative J is rejected because starts "empatan a 1 min", but recorder snapshots are taken every 10 s and log timestamps are sub-second. The risk "un despliegue ajeno acapararía la causa" applies to the LLM as well.
  - **Judge check:** rule 3 only checks that a t_inicio is cited, not that the order is consistent with it.
  - **Aggregation:** the rule that collapses N nondeterministic repetitions into "un valor por caso" is unspecified. Codex (line 180) warns against applying Wilson to fractional per-case means.
* **Rationale & Recommendation**: Fix the rationale. Make rule 3 check that the order is consistent with the cited times. Freeze N and the aggregation rule (for example majority, ties counted as wrong) in protocol.yaml. Consider a deterministic tie-break as a baseline.

### M10. The confirmatory judge comparison depends on the team's own choices and uses non-independent units - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** Lines 53, 95-99, 170, 306
* **Discrepancy Description**:
  - **Outcome set by the team:** the no-judge arm approves everything, so the discordant pairs, and therefore the result, depend on the true/false proportion and on how the team writes fabricated diagnoses. The proportion is acknowledged at line 98 but not fixed.
  - **Independence:** fabricated candidates derived from the same case are not independent units for McNemar.
  - **Undefined candidate:** the second Investigator round (line 170) makes "the candidate" differ between arms.
  - **Scope:** the only preregistered test says nothing about Tider's diagnostic value.
* **Rationale & Recommendation**: Freeze the proportion, the fabrication recipe and the counts, with a rationale. Define the candidate as the first-round diagnosis. Cluster by source case, or restrict McNemar to natural candidates. Add a power estimate (decision 27.5 gives about 92 pairs for 20 pp).

### M11. Pooled accuracy thresholds hide the near-trivial scale_zero stratum - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** Lines 58, 101-106, 304
* **Discrepancy Description**: A pool dominated by scale_zero cases, which decision 18 calls near-trivial, can clear "Wilson inferior >= 70 %" even if the subtle cartservice mechanisms fail. The document doesn't fix the stratum mix, doesn't require per-stratum reporting, and doesn't define the denominator for "afirmaciones incorrectas". Line 106 also hedges ("unos 60 ... como mínimo", "o aceptar que...").
* **Rationale & Recommendation**: Fix the stratum counts in protocol.yaml. Report Wilson per stratum and pooled with declared weights. Define the denominator.

### M12. CUJ 3 (loadgenerator control) has no expected label and will confirm a signature - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** Lines 128-132, 202
* **Discrepancy Description**: Scaling loadgenerator to zero is a real scale_zero, so "servicio sin instancias" will CONFIRM on it with rol causa. The RFC (N10) asked for a predefined expected label. The CUJ only says that no store service gets blamed, and doesn't say whether loadgenerator counts as tienda or auxiliar.
* **Rationale & Recommendation**: Define the expected output and how it is scored (for example `{loadgenerator, servicio-sin-instancias, sin_impacto_en_tienda}`). Decide whether a store-impact precondition applies.

### M13. A capped sample of 40 lines can't support counts, baselines or traffic checks; "evidencia completa" overstates it - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-style`
* **Affected Scope:** Lines 19, 48, 193, 195, 197, 436
* **Discrepancy Description**: 40 records per service, in temporal order, captures only the start of the window for noisy services (PM-02 has 1937 ERROR lines in recommendationservice). That can't support per-severity counts, baseline anomaly detection, or the K = 3 traffic check. Line 193 hedges ("por ejemplo, 40") while line 436 treats 40 as fixed. "Evidencia completa" (19, 48) overstates a sampled sweep.
* **Rationale & Recommendation**: Take exact aggregate counts (a Cloud Logging count or log-based metric) separately from the bounded raw sample. Group multi-line tracebacks into one event (RB-01 line 67). Fix the quota. Replace "completa" with "cobertura por servicio con cuota fija".

### M14. The recorder is a silent single point of failure, and line 191 uses the fallback Alternative F rejects - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** Lines 179, 191, 352-353
* **Discrepancy Description**: When the recorder has gaps, fields silently become SIN_DATOS, and nothing excludes such cases from the campaign. When there is no recorder, line 191 falls back to current state, which is exactly what Alternative F rejects; in a replay this injects post-incident state. Continuous production operation (availability, auth, storage) is not designed.
* **Rationale & Recommendation**: Add an admission rule: the window must be fully covered by snapshots, otherwise the case is excluded and reported. Forbid the current-state fallback in evaluation. Declare production operation of the recorder out of scope.

### M15. The Proponente verb filter is a bypassable blocklist with no matching rule, and its test is narrower than the list - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-style`, `egm-structural`
* **Affected Scope:** Lines 52, 263-265
* **Discrepancy Description**:
  - **Missing verbs:** the list misses annotate, label, taint, create, run, exec, cp, expose, autoscale, rollback, helm, `gcloud ... resize`, `curl -X POST`, rm, and others.
  - **No matching rule:** whole word, subcommand position or substring is never stated. Substring matching would reject RB-01's own read-only fallback step, which contains `ScalingReplicaSet`.
  - **Narrow test:** Goal 5 tests 6 verbs, while section 7 lists 11 plus `aws ecs update-service`.
  - **Undefined fallback:** the fallback step is undefined when `razon = desconocida`.
* **Rationale & Recommendation**: Replace the blocklist with a tokenized allowlist of read-only command forms (`kubectl get/describe/logs/top`, `gcloud logging read`, and so on), or at least specify matching as the subcommand of kubectl, gcloud or aws. Make the Goal 5 test cover the full list. Define the fallback for unknown reasons.

### M16. Prompt injection through log text is not addressed - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** Lines 255, 276, 430-434
* **Discrepancy Description**: Raw log lines, which can contain user-controlled input in real use, reach the Investigator, the Proponente fallback and the OpenAI Juez. The security section covers redaction and secrets, but not instructions embedded in evidence.
* **Rationale & Recommendation**: Delimit evidence in prompts and treat it as untrusted. Keep Judge rules 1-4 as deterministic gates. Add an adversarial test with injected log lines.

### M17. The cost and latency budget is incomplete - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-style`
* **Affected Scope:** Lines 104, 312, 315, 435-438
* **Discrepancy Description**:
  - **Cost:** there are no token or $ estimates per analysis or per campaign. The campaign multiplies runs by N repetitions, 3 judge arms, Lake with and without postmortems, direct LLM, and fabricated candidates. The ~14 h GKE estimate (65 x 12 min) has no $ figure and leaves out repetitions and controls.
  - **Latency:** the 120 s p95 target isn't broken down. The Investigator alone gets 90 s, plus the sweep, up to 2 Proponente calls, up to 2 judge calls and one extra round.
* **Rationale & Recommendation**: Add a per-stage latency budget, a token and $ estimate per run and per campaign, and the value of N. Say whether repetitions rerun on GKE or replay the frozen window.

### M18. "Ninguna por ahora" open questions hides undecided parameters and normative decisions - Severity: Major
* **Reviewer Lens:** `egm-structural`, `egm-style`, `egm-design`
* **Affected Scope:** Lines 46, 71-112, 81, 98, 106, 111, 217, 262, 274
* **Discrepancy Description**: Line 75 says there are no open questions, yet these are still undecided:
  - the true/false candidate proportion;
  - accepting n < 60;
  - the value of K, and its calibration runs;
  - the number of baseline runs behind media ± 3σ;
  - N repetitions and the aggregation rule;
  - the "cobertura baja" threshold;
  - when runbooks flip to `validado: true`.

  Line 46 points to Open Questions for thresholds that actually sit under "Preguntas resueltas". Normative design (entity model, inventory, health predicate, thresholds) also lives in that section rather than where it applies.
* **Rationale & Recommendation**: List the open items, each with an owner or the deadline "antes del hash del protocolo". Require calibration runs to be disjoint from evaluation runs, and freeze the `validado` flags before the first evaluation run. Move each resolved decision to its normative section (thresholds to Goals, predicate to section 2, entity and inventory to sections 3 and 5, comparison to section 12) and keep only a short dated decision log. Fix line 46.

### M19. Replay fidelity for on-demand tool calls is not specified - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** Lines 57, 255, 301, 305
* **Discrepancy Description**: Goal 10 promises recomputation without providers, but the Investigator pulls raw lines, events and Lake results on demand. The document doesn't say whether campaign-mode tool calls are served from the frozen snapshot. Recorder retention (48 h) and Cloud Logging retention limit later re-runs.
* **Rationale & Recommendation**: State that every tool call in campaign mode is served from the frozen case snapshot, and define what happens when a query falls outside it.

### M20. The dependencia-lenta signature relies on the injector's own instrumentation - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** Lines 184, 314
* **Discrepancy Description**: The only latency source is the ChaosForge observer's PING to Redis. That signal exists only in the lab, is a possible leakage channel (M6), and it's unverified whether the PING crosses the proxy.
* **Rationale & Recommendation**: State where the PING is taken relative to the proxy. Label the signature lab-only in the claims. Consider an independent source, such as client-side timing in cartservice logs.

### M21. Risks & Mitigations is thin, scattered, and has no mitigations - Severity: Major
* **Reviewer Lens:** `egm-structural`, `egm-design`
* **Affected Scope:** Lines 310-315 (and scattered: 93, 179, 183-185, 274, 430-434)
* **Discrepancy Description**: The standard requires a Risks & Limits section covering failure modes, security, scale and mitigations. Here risks sit in an H3 inside Technical Plan, without mitigations: line 313 only says "hay que verificarlo", and lines 312 and 315 name a cost with nothing to address it. Several failure modes are missing:
  - the judge unavailable or timing out;
  - a Chroma or Lake load failure;
  - a malformed signature catalog;
  - Cloud Logging throttling;
  - the issues in M4, M6, M14, M15, M16 and M19.
* **Rationale & Recommendation**: Add an H2 "Riesgos y mitigaciones" before NFR, as a table with columns Riesgo | Tipo | Impacto | Mitigación | Residual. Move the scattered items into it.

### M22. Alternatives give the decider as the reason, with no trade-off or link - Severity: Major
* **Reviewer Lens:** `egm-structural`, `egm-style`, `egm-design`
* **Affected Scope:** Lines 326-424 (notably 353, 358, 375, 380, 384-385, 390, 402, 414, 419)
* **Discrepancy Description**: Every "Motivo del rechazo" starts with "rechazada por el autor (decisión N / borrador)" and links nothing, which the Alternatives Rule forbids.
  - Several only restate the chosen option.
  - F (353) cites no decision number.
  - "borrador" references can't be traced.
  - L (384) is circular.
  - 385 and 402 ("rechazada en la revisión y aceptada por el autor") read ambiguously.
* **Rationale & Recommendation**: State the deciding trade-off in one clause, put the actor in parentheses, and link decisions to anchors in `recomend/_auditoria_consolidada.md`. Log the "borrador" decisions there.

### M23. Some realistic alternatives are missing - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** Lines 317-424
* **Discrepancy Description**: The Alternatives section omits:
  - GKE Managed Prometheus with kube-state-metrics instead of building tider-recorder;
  - an allowlist or closed grammar for the Proponente (the RFC line 379 notes it wasn't adopted, without a reason);
  - a rules-only judge baseline.
* **Rationale & Recommendation**: Add each one with its concrete trade-offs.

### M24. LLM role and call counts contradict each other and the diagram - Severity: Major
* **Reviewer Lens:** `egm-structural`, `egm-style`, `egm-design`
* **Affected Scope:** Lines 69, 144, 163-167, 170, 261-264, 437
* **Discrepancy Description**: "Seis roles, dos usan LLM" (69) and "dos puntos" (144) conflict with the Proponente's LLM fallback and with "2 roles LLM y 3 puntos de llamada" (264). The Proponente sits outside the LLM subgraph, and the six roles are never listed even though about eight components appear. "Como máximo 2 llamadas" (437) is not stated in section 7. Judge rounds disagree: at most 1 extra round in the diagram, at most 2 rounds in the NFR.
* **Rationale & Recommendation**: Add a roles table under Principio (rol | módulo | ¿LLM? | puntos de llamada | máx. llamadas). Fix line 144, draw the fallback inside the LLM subgraph, and reconcile the round counts.

### M25. Goals disagree with later decisions - Severity: Major
* **Reviewer Lens:** `egm-structural`, `egm-style`, `egm-design`
* **Affected Scope:** Lines 48, 50, 54, 80, 90, 191, 202, 372-375, 436
* **Discrepancy Description**:
  - **Goal 1:** counts "los 12 servicios", but the inventory covers every Deployment and StatefulSet, auxiliaries included (chaosforge-proxy, observer). The NFR's 12 x 40 budget repeats the figure. Decision 25 says 11 fichas while the Lake has 12.
  - **Goal 3:** requires "prioridad entre firmas", which line 80 and Alternative J reject.
  - **Goal 5:** see M15.
* **Rationale & Recommendation**: For Goal 1, say "todos los Deployments/StatefulSets del namespace (12 de la tienda + auxiliares)", state whether loadgenerator counts, and express the budget per service. For Goal 3, keep only the verdict precedence, or reword it as "orden del Investigador validado por el Juez".

### M26. Judge rule 5 contradicts the sentence that introduces the rules - Severity: Major
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** Lines 269, 274
* **Discrepancy Description**: Line 269 says that breaking a rule rejects the diagnosis, but rule 5 only marks the analysis `incompleto`.
* **Rationale & Recommendation**: Move rule 5 out of the list, or say which rules reject and which only mark.

### M27. The common model claims to be platform-neutral but its source enum is GCP- and ChaosForge-specific - Severity: Major
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** Line 181
* **Discrepancy Description**: The text says "el modelo no tiene nada propio de GCP", yet the `fuente` enum is `cloud_logging`, `monitoring`, `observer`. Decision 19 asks for "contrato a extraer" wording.
* **Rationale & Recommendation**: Use generic values plus a `proveedor` field, or say the enum is extended per adapter.

---

### Nit

### N1. Heading and metadata language is mixed - Severity: Nit
* **Reviewer Lens:** `egm-structural`, `egm-style`
* **Affected Scope:** Lines 3-7, 11, 25, 44, 60, 71, 114, 140, 310, 317, 428
* **Discrepancy Description**: English H2s and metadata keys (Author, Status, Technical Plan) sit alongside Spanish keys (Alcance, Fuentes) and Spanish H3s.
* **Rationale & Recommendation**: Keep the English H2s only if the template requires them, and make the metadata keys consistent.

### N2. Technical Plan H3s mix numbered and unnumbered headings and don't follow the diagram - Severity: Nit
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** Lines 142, 146, 175-299, 310
* **Discrepancy Description**: "Principio", "Flujo" and "Riesgos" are unnumbered while sections 1-12 are numbered, and the numbered order doesn't match the diagram.
* **Rationale & Recommendation**: Number every H3 or none. Match the diagram order, or add a node-to-section map.

### N3. List formatting in "Preguntas resueltas" is inconsistent - Severity: Nit
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** Lines 76-77, 94, 100, 107, 109-112
* **Discrepancy Description**: There is a double blank line before the H3, tight and loose list styles are mixed, and line 112 renders as part of item 3.
* **Rationale & Recommendation**: Use one list style, and re-indent line 112 after a blank line.

### N4. Bold lead-ins run straight into lists - Severity: Nit
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** Lines 183-184, 201-202, 254-255, 261-262, 286-287
* **Discrepancy Description**: These lead-ins have no blank line before the list, which can break Pandoc or PDF export.
* **Rationale & Recommendation**: Add a blank line before each list.

### N5. Path and reference formats are inconsistent and unlinked - Severity: Nit
* **Reviewer Lens:** `egm-structural`, `egm-style`
* **Affected Scope:** Lines 7, 29-38, 40, 177, 181, 192, 217, 257, 278, 287
* **Discrepancy Description**: Paths appear in different forms (`console/agentic.py`, `agentic.py:35`, `:179`). Sources are code spans rather than links. OpenRCA A.5, "cláusula 5" and the rubric C1-C4 have no reference.
* **Rationale & Recommendation**: Use repo-relative paths throughout, turn the sources into relative links, and add a "Referencias" list.

### N6. The flow diagram misrepresents the recorder and is missing Lake edges - Severity: Nit
* **Reviewer Lens:** `egm-structural`, `egm-style`, `egm-design`
* **Affected Scope:** Lines 150-154, 164-167
* **Discrepancy Description**: `REQ --> REC` implies the recorder starts per request, but it runs continuously (179). The Lake feeds only the Cartógrafo, with no edges to the Verificador, the Proponente or the Investigador (`context_search`), and nothing shows catalog or runbook reads.
* **Rationale & Recommendation**: Draw the recorder as an independent source, and add the missing labelled edges.

### N7. The output contract block types fields unevenly - Severity: Nit
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** Lines 223-248
* **Discrepancy Description**: `Nodo` and `Arista` fields have no types or value sets, and `Recomendacion=` breaks the column alignment.
* **Rationale & Recommendation**: Give every field a type, list the values of `rol_en_principal`, `cobertura` and `Arista.estado`, and align the block.

### N8. Bundled alternatives are hard to read - Severity: Nit
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** Lines 355-358, 377-380, 387-390, 411-414, 416-419
* **Discrepancy Description**: G, K, M, Q and R each combine two options, and their pros and cons mix both inline.
* **Rationale & Recommendation**: Split them into G1/G2 and so on, or use nested bullets per option.

### N9. Small CUJ and spec gaps - Severity: Nit
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** Lines 114-138, 288, 308
* **Discrepancy Description**:
  - No CUJ covers the link-latency case or a judge rejection followed by re-investigation.
  - Postmortem chunking ignores `###`, `---` and the raw "Señales observadas" block (PM-04).
  - The κ artifact is called `kappa_form.csv` here and `kappa_form.py` at line 680.
* **Rationale & Recommendation**: Add CUJ 5 and CUJ 6, define the chunking rules, and align the artifact name.

### N10. Some terms are used before they are defined - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** Lines 32, 39, 40, 58, 217, 278, 308, 324
* **Discrepancy Description**: E5, C09, "benchmark de recuperación", C1-C4 10/20, "Alberto y Jose" (role, and whether it should be "José"), [INF], OpenRCA A.5, "cláusula 5" and the 13-page atlas have no gloss at first use.
* **Rationale & Recommendation**: Add a one-line gloss or a link at first use.

### N11. Failure terminology drifts - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** Lines 98, 233, 306, 399-402
* **Discrepancy Description**: "mecanismo", "razón" and "modo de falla" are used as if interchangeable. The fabricated-diagnosis lists at 98 and 306 differ.
* **Rationale & Recommendation**: Keep "mecanismo" for the ChaosForge label and "razón" for Tider's output, and use the same list in both places.

### N12. Goal 8 is not testable - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** Line 55
* **Discrepancy Description**: "Se distinguen visualmente" has no verifiable criterion, which contradicts line 46.
* **Rationale & Recommendation**: Name a check, such as a distinct CSS class or attribute per role, verified by a test.

### N13. Decision-history notes sit inside the spec text - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** Lines 263, 289
* **Discrepancy Description**: Notes like "decidido al cerrar, 2026-11-09" are decision history rather than spec.
* **Rationale & Recommendation**: Move them to the decision log.

### N14. "Límites" lacks a subject - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** Line 292
* **Discrepancy Description**: The text says the numbers go "de 20 a 60 / de 300 a 600" without saying which parameter changes.
* **Rationale & Recommendation**: Name the parameter.

### N15. Some wording is vague or informal - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** Lines 6, 23, 42, 54, 106, 396, 412, 418, 424
* **Discrepancy Description**: Examples include "producto completo", "congelado de antemano", "en una línea", "como corresponde", "con mucha seguridad", "la que pide el pitch", "n chico" and "la afirmación queda acotada".
* **Rationale & Recommendation**: Drop or rephrase each. At line 424, quote the sentence from decision 18.

### N16. The κ construct is undefined - Severity: Nit
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** Lines 58, 308
* **Discrepancy Description**: The document doesn't say what the raters judge, what the 3 questions are, or what κ target applies. There is no CI for n = 30, and "30 casos" conflicts with decision 24's "mínimo 20".
* **Rationale & Recommendation**: Define the questions, the target and the CI, and reconcile the case count.

### N17. The admission criterion can drop the hard cases - Severity: Nit
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** Line 304
* **Discrepancy Description**: Requiring a "síntoma distinto del evento de la inyección" may exclude exactly the hard cases.
* **Rationale & Recommendation**: Report excluded cases and the reason for each.

### N18. Rollback compatibility is checked in one direction only - Severity: Nit
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** Lines 439-441
* **Discrepancy Description**: The text covers v2 code reading v1 data. A rollback also means v1 code reading stored v2 records, which isn't addressed.
* **Rationale & Recommendation**: Confirm that v1 code can read v2 records, or state that it can't.

---

## Suggested fix order

1. Make the core rules internally consistent: M1, M2, M7, M8, M24, M25 and M26.
2. Fix the evaluation-validity gaps: M6, M9, M10, M11, M13, M14 and M19.
3. Restructure the document: M18 and M21, then M22 and M23.
