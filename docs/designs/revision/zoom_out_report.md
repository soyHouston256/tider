# Goldfish Review Report: Stage 5 (Initial Zoom Out)

**Target:** `/Users/maxhoustonramirezmartel/code/utec/5/integrador/project/code/tider/docs/designs/tider-diseno-piloto.md` (`1-727`)

**Mode:** REVIEW. **Standard (zoom-out):** `/Users/maxhoustonramirezmartel/.claude/plugins/cache/egm/egm/0.1.1/resources/document_standards/zoom-out-standard.md`

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-zoom-out` | completed (0 Blocker, 7 Major, 5 Nit; verdict: needs revision) |
| `egm-inventive-catalyst` | completed (12 Major, 1 of them an escalation candidate to Blocker; 3 Nit) |

Each reviewer ran once (one instance each, no A/B pair). Neither reviewer read `project/ground_truth/` or `ENTREGA_*`.

**Severity triage note:** The inventive-catalyst persona can only issue Major or Nit in REVIEW mode. It marked F1 (missing Service/ClusterIP data) as "escalation candidate: Blocker", and this report promotes it to Blocker: as written, several core mechanisms cannot be computed. Four findings appeared in both reviews and are merged here. Each merged finding names both lenses.

**After deduplication:** 1 Blocker, 15 Major, 7 Nit (23 findings).

## Prioritized Findings (Blockers -> Major -> Nits)

---

### B1. Caller errors cannot be mapped to a service: Services/ClusterIPs are never recorded - Severity: Blocker
* **Reviewer Lens:** `egm-inventive-catalyst` (F1, escalated by the synthesizer)
* **Affected Scope:** Lines 110, 120, 179, 204, 480, 487 (cross-check RB-01 lines 46-55, PM-04)
* **Discrepancy Description**: Four mechanisms need to link a caller's error line to the entity it names:
  * victim role (CUJ 1);
  * observed edges ("errores que nombran un destino host:puerto");
  * clause 2 of the "sano" predicate;
  * the RB-01 corroborant.

  RB-01 and PM-04 show that callers name the **ClusterIP:port** (for example `10.49.5.115:50051`). The port alone is ambiguous: 50051 is used by both payment and shipping, and 6379 by both redis-cart and the proxy. The recorder snapshots only Deployments, StatefulSets, EndpointSlices and Pods (179, 480), and the RBAC does not grant `services` (487). EndpointSlices carry pod IPs, not ClusterIPs, so the design cannot build the address-to-entity mapping. It silently falls back to matching by name or port, which the Lake documents as unreliable.
* **Rationale & Recommendation**:
  * Add Services (ClusterIP and ports) to the recorder snapshot and to the RBAC.
  * Build one time-versioned `(ip, port) -> entidad` index per window, from ClusterIPs plus EndpointSlice pod IPs. Sweep, Cartógrafo, state predicate and verifier should all use it.
  * Add a fixture test that resolves the 50051 collision using the PM-04 lines.
  * Errors whose address cannot be resolved go to `sin_datos`.

---

### M1. Scope: stages 1 and 2 and the full product are bundled into one plan - Severity: Major
* **Reviewer Lens:** `egm-zoom-out` (M1)
* **Affected Scope:** Lines 6, 44-58, 445-707
* **Discrepancy Description**: The header covers "etapas 1 y 2" in one design. The plan has 41+ file changes across two repos, and the only internal gate is that Fase 6 depends on everything else. It includes:
  * map edges in the UI;
  * two ways into the Lake;
  * a second LLM provider;
  * the Proponente's LLM fallback;
  * a retrieval study;
  * κ tooling.

  Other sources draw the line elsewhere. The RFC (`tider-asesor-incidentes.md` 728-751) separates "Etapa 1: cambios mínimos para una evaluación válida" from Etapa 2. VALIDACION_CODEX §8 (line 335) recommends closing a vertical slice first, and notes about one person of capacity (line 332).
* **Rationale & Recommendation**:
  * Cut an MVP that alone makes the campaign valid:
    * recorder or equivalent, plus sweep and state;
    * signature verifier;
    * contract v2 without UI;
    * ground-truth isolation;
    * trace, protocol, runner and score.
  * Move these to a second slice behind an explicit go/no-go after the signature confusion matrix:
    * map edges and colours (item 26);
    * the Proponente's LLM fallback (M2);
    * `retrieval_check` (N1);
    * explanation-text changes (item 27).
  * State an owner and hours for each phase.

---

### M2. The Proponente's LLM fallback and verb filter: an unneeded LLM call, a filter that blocks catalog actions, and a leaky denylist - Severity: Major
* **Reviewer Lens:** `egm-zoom-out` (M2) + `egm-inventive-catalyst` (F3)
* **Affected Scope:** Lines 52, 259-265, 273, 437, 577-582, 596
* **Discrepancy Description**:
  * **YAGNI:** with no catalog action, the Proponente makes a dedicated LLM call, filters its verbs, and falls back to the runbook's "Pasos de verificación (SOLO LECTURA)" after rejections. That deterministic content already exists in every runbook (RB-01 lines 88-110). The LLM step adds a call point, a prompt, retries, latency, cost and a prompt-injection surface. "Runbook más cercano" (263) is undefined when `razon = desconocida`. Item 19 still calls `proposer.py` "determinista".
  * **Filter scope (inconsistent rule):** lines 52 and 263 apply the filter only to the LLM fallback text. Judge rule 4 (273) applies it to "la recomendación" in general. The validated RB-01 catalog action is `kubectl ... scale ...`, so rule 4 would reject every catalog recommendation and CUJ 1 could never pass. The RFC already flagged this defect as N12, and it is back.
  * **Wrong polarity:** the denylist misses `exec`, `label`, `annotate`, `create`, `expose`, `autoscale`, `taint`, `cp`, `helm upgrade`, `gcloud ... update`, `aws ... put-*`, and Spanish imperative prose ("escala el deployment a 1").
  * **Retry count:** line 581 says "rechaza dos veces", line 265 implies one attempt, and line 437 says 2 calls.
* **Rationale & Recommendation**:
  * Scope Judge rule 4 explicitly to `tipo = diagnostico_no_verificado`.
  * For the pilot, make the Proponente fully deterministic:
    * show the catalog action when the signature is CONFIRMADA and the runbook is validated;
    * otherwise show the runbook's read-only steps, with parameters (SVC, CLUSTER_IP, window) filled from evidence and labelled "sugerencia no verificada".
  * If an LLM step stays, use an allowlist grammar of read-only commands (`kubectl get|describe|logs|top`, `gcloud logging read`, `gcloud monitoring ...`) instead of a denylist.
  * Settle on one retry rule.
  * If κ on LLM suggestions (decision 4) needs the LLM path, run it only as an exploratory arm on the 30 κ cases.

---

### M3. The pilot evaluation rewrites tooling the repo already has - Severity: Major
* **Reviewer Lens:** `egm-zoom-out` (M3)
* **Affected Scope:** Lines 299-308, 650-693 (items 33-38)
* **Discrepancy Description**: Only `proportion()`/`paired()` from `eval/quality/score.py` are reused. The repo already has:
  * **Freeze:** `eval/quality/data.py` `digest()`/`verify()` with `manifest.json`.
  * **Run stamping:** `eval/quality/live.py` 69-75 writes `run.json` with protocol, model and code hashes.
  * **Causal scoring:** `tider/console/causal_evaluation.py` `score_causal()`, plus `score_window()`/`score_diagnoses()`, which already handle false attribution on controls and technical errors.
  * **Retrieval scoring:** `score_retrieval()` already computes Hit@1, Hit@4 and MRR@4, and item 37b re-derives them.
  * **Replay:** `eval/course_e5.py` `RecordedModel`/`FrozenTools` (46-115).
* **Rationale & Recommendation**:
  * Build `eval/pilot` as an extension of `eval/quality`:
    * freeze `protocol.yaml` with `digest`/`verify`;
    * stamp runs the way `live.py` does;
    * extend `score_causal` with a link entity and a partial-credit field;
    * have `retrieval_check` call `score_retrieval`;
    * reuse `FrozenTools`/`RecordedModel`, noting that arms which change prompts cannot reuse recorded responses.
  * State this reuse explicitly in items 33-38. See also M12.

---

### M4. Two pipelines kept side by side behind `TIDER_PIPELINE` - Severity: Major
* **Reviewer Lens:** `egm-zoom-out` (M4)
* **Affected Scope:** Lines 207, 250, 441, 527-528, 569-571, 586-590, 599
* **Discrepancy Description**:
  * v1 and v2 branches are kept in `agentic.py`, `analysis.py`, `service.py`, `investigation_tools.py` and `providers/catalog.py`, and the tests are split as well.
  * `catalog.py` stays alive, marked obsolete only in a docstring.
  * The justification is SQLite history, but `investigation_history_path` is off by default (`service.py:39-47`).
  * The work already happens on a branch (447).
* **Rationale & Recommendation**:
  * Keep the flag only until signature validation passes.
  * Add a plan item that deletes the v1 path, `catalog.related_services` and the v1-only tests.
  * Treat reading old v1 analyses as deserialization only, not as a second pipeline.

---

### M5. The state recorder: no comparison with platform sources, and failures pass silently - Severity: Major
* **Reviewer Lens:** `egm-zoom-out` (M5) + `egm-inventive-catalyst` (F8)
* **Affected Scope:** Lines 175-185, 191, 312-313, 350-353, 477-483, 493
* **Discrepancy Description**:
  * **No alternatives weighed:** a new always-on process (`tider-recorder`: `kubectl` snapshots every 10 s, 48 h in SQLite, a new RBAC file, an `spec_at()` API) is framed as running "en uso real, de forma continua". Two platform sources that may hold the same data are not considered:
    * GKE Admin Activity audit logs, in the Cloud Logging Tider already reads;
    * kube-state-metrics through Managed Prometheus.

    Alternative F only rejects "current state only".
  * **Silent failure:** the inventory and state fall back to "estado actual si no hay registrador". That quietly reintroduces the rejected Alternative F: cases turn into SIN_DATOS or mix time frames, and nothing signals it.
* **Rationale & Recommendation**:
  * Add an alternative comparing the recorder with audit logs plus kube-state-metrics. [INF: verify that audit logs include request bodies for Deployment patches.]
  * If the recorder stays:
    * scope it to the pilot and lab;
    * justify 10 s against the 30-120 s fault duration;
    * add a heartbeat and per-window coverage;
    * make the campaign runner check recorder freshness before each injection and abort the case under a pre-registered exclusion rule;
    * never use current state for a past window (mark it SIN_DATOS with `fuente_fallida = recorder`).
  * Move the implementation constants (10 s, 48 h, `spec_at` signatures) out of the Technical Plan.

---

### M6. A third evidence abstraction is added without retiring the other two - Severity: Major
* **Reviewer Lens:** `egm-zoom-out` (M6)
* **Affected Scope:** Lines 181, 451-471
* **Discrepancy Description**: The plan adds `EvidenceAdapter` and `GKEAdapter`. The code already has `EvidenceSource(Protocol)` (`service.py:16-17`) and the concrete `EvidenceProvider` (`providers/__init__.py`). The design does not say which one survives, which leaves three overlapping seams.
* **Rationale & Recommendation**: State that `EvidenceAdapter` replaces `EvidenceSource`/`EvidenceProvider`, and plan their removal. Otherwise keep `gke.py` as a plain module until a second adapter exists. Decision 22 (common model) stays either way. If M12's `BundleAdapter` is adopted, it is the natural second implementation that justifies the interface.

---

### M7. Cause vs. victim, the headline problem, has no deterministic owner, no metric, and an unsatisfiable CUJ - Severity: Major
* **Reviewer Lens:** `egm-zoom-out` (M7) + `egm-inventive-catalyst` (F10)
* **Affected Scope:** Lines 13, 27, 42, 55, 93, 101-106, 120, 144, 236, 240, 670-677
* **Discrepancy Description**:
  * Separating cause from victims is the core operator promise. Yet `rol` is set by the LLM Investigator, and the Principle (42, 144) lists only sweep, signatures, state and filters as computed. Line 93 says edges are used "para separar causa de víctimas" without saying by whom.
  * Scoring is top-1 entity accuracy only, which `scale_zero` makes almost trivial (decision 18). Victims are checked only in the CUJ 1 acceptance step, and the RFC (M2) notes there is no labelling procedure for them.
  * CUJ 1 expects `checkoutservice` to be cited as a victim "con citas de sus errores". RB-01 60-66 and PM-04 show that checkoutservice writes no lines at WARNING or above; its failure appears only nested inside frontend's errors.
* **Rationale & Recommendation**:
  * Derive roles deterministically in the sweep/Cartógrafo stage. A victim is a node upstream of the cause with attributed errors (B1/M8) starting at or after `t_inicio`, including nested chains parsed from frontend messages (`failed to charge card`, `failed to prepare order`). Keep that application-specific parsing knowledge in Lake fichas.
  * The LLM only explains, or overrides with a justification.
  * Fix CUJ 1 to cite checkoutservice through the nested frontend line.
  * Add a descriptive victim precision/recall metric on cascade cases with a frozen labelling rule, or explicitly declare that roles are not evaluated in this iteration.

---

### M8. CUJ 2 contradicts the agreed "sano confirmado" predicate - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst` (F2)
* **Affected Scope:** Lines 108-112 vs 126; also 49
* **Discrepancy Description**: CUJ 2 requires `redis-cart` to come out as sano confirmado "aunque los errores lo nombran". Clause 2 requires "ningún llamador con errores que lo nombren". With `wrong_port`, cartservice's errors name redis-cart at port 6380, so redis-cart can at best reach `sin_datos`.
* **Rationale & Recommendation**: Attribute each caller error to the tuple (caller, destination address), using the B1 index. When the destination resolves to a service whose port or endpoints do not match (6380 against an exposed 6379), charge the error to the caller's configuration or the edge, not to the target. Reword clause 2 to "no caller errors *attributed* to this entity". Add near-miss fixtures: correct port with the target down, and wrong port with the target healthy.

---

### M9. The LLM orders signatures on the premise of 1-minute ties, but the sources are finer-grained - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst` (F4)
* **Affected Scope:** Lines 80-83, 101, 315, 372-375, 659
* **Discrepancy Description**:
  * Alternative J is rejected because "con datos de resolución de 1 minuto los inicios empatan". Yet the recorder samples every 10 s, and log and event timestamps are sub-second (PM-04 shows nanoseconds).
  * LLM ordering costs every case 3 repetitions, a summary and extra tokens.
  * Line 101 does not define how 3 binary repetitions collapse to one value per case. Codex warns that Wilson on fractional means is invalid.
* **Rationale & Recommendation**:
  * Use a deterministic tier first:
    1. a Cambio on the entity that precedes and *explains* the first error (the RB-02 condition);
    2. earliest `t_inicio` at recorder or log resolution;
    3. most-upstream anomaly in the graph.
  * Call the LLM only for residual ties within a pre-registered tolerance.
  * Repeat only those cases, pre-register the collapse rule (for example, majority of 3), and report the fraction that reached the LLM tier.

---

### M10. The confirmatory judge result depends on a free knob: the true:false ratio - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst` (F5)
* **Affected Scope:** Lines 53, 95-99, 659
* **Discrepancy Description**:
  * Against the "sin juez = approve all" arm, McNemar's discordant pairs are "judge rejects a false" and "judge rejects a true". Raising the share of fabricated falses mechanically raises the first, so the ratio partly decides the result. The text admits it "cambia el resultado" and only freezes the ratio.
  * Fabricated mutations of the same case are not independent, and the design does not group them.
  * Offline-built mutations may be easier than natural errors.
* **Rationale & Recommendation**:
  * Pre-register a ratio-free confirmatory quantity: balanced accuracy or Youden's J, with "sin juez" fixed at J = 0.
  * Test it with a cluster bootstrap by source incident, or run McNemar within each class.
  * Keep FAR and FRR with Wilson, and report natural and fabricated cases separately.
  * Make this change before the protocol hash is registered.

---

### M11. The stage budgets already use the whole p95 latency target - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst` (F6)
* **Affected Scope:** Lines 104, 170, 264, 436-438, 502
* **Discrepancy Description**: The sweep timeout (30 s) plus the Investigator budget (90 s) equals the p95 target of 120 s. The Proponente (up to 2 calls) and the Judge come on top, over up to 2 rounds, for up to 8 LLM calls in the worst case. The design does not say which gives way.
* **Rationale & Recommendation**:
  * Set explicit per-stage budgets that add up to less than the target, or state that the target excludes round 2.
  * Consider pre-aggregating per-service, per-minute counts in the recorder or a companion process, so the sweep becomes a lookup. Watch the roughly 60 calls/min Cloud Logging quota (RFC line 227).
  * Run the deterministic Proponente concurrently with the Judge's fixed rules.

---

### M12. A fixed 40-line temporal sample can certify "zero errors" it never read - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst` (F7)
* **Affected Scope:** Lines 48, 108-112, 193, 197, 274, 436
* **Discrepancy Description**:
  * A service that is chatty early in the window fills its 40-line quota with pre-incident INFO lines. Its later errors are never read, clause 2 can pass, and the node becomes sano.
  * `truncado` only makes the Judge mark the analysis `incompleto` (274). The RFC required that truncation force `sin datos` (RFC line 230).
  * Templates built from 40 samples are incomplete: PM-02 had 1937 ERROR lines from one service.
* **Rationale & Recommendation**:
  * Separate counting from sampling. Get complete per-service, per-severity counts per time bucket from aggregate queries, and evaluate "zero errors" and the anomaly check on those counts.
  * Spend the quota on stratified samples: per bucket, errors first.
  * Rule: `truncado` with zero errors read can never yield sano.
  * Verify that counts cover both `textPayload` and `jsonPayload.message` (RB-01 line 110, marked [INF]).

---

### M13. The "dependencia lenta" signature relies on a lab artifact, which the design rejects elsewhere - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst` (F9)
* **Affected Scope:** Lines 184, 202, 205, 217, 314, 378-380
* **Discrepancy Description**:
  * Alternative K rejects lab artifacts in the product, yet `latencia_dependencia_p95` comes only from the ChaosForge observer.
  * Thresholds "salen ... de ChaosForge", so verifier and injector share criteria. Codex §5.4: that shows conformity, not causal validity.
  * `REDIS_ADDR=chaosforge-proxy:6379` (205) is itself a fingerprint of the injection.
* **Rationale & Recommendation**:
  * Give Tider its own latency source: caller-side durations from logs, or a Tider-owned read-only probe.
  * Calibrate thresholds only on no-fault baselines (217), never from injector parameters.
  * Otherwise, declare that this signature is validated only against the lab observer, and exclude it from claims that are meant to carry over to SIBI.
  * Pre-register how the proxy discrepancy is treated: legitimate evidence or excluded fingerprint.

---

### M14. Ground-truth isolation is a single port boundary, and the leakage paths are untested - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst` (F11)
* **Affected Scope:** Lines 56, 297, 631-648
* **Discrepancy Description**: Isolation is reduced to "a different port, not exposed over the tunnel", and the test only checks configured URLs. Codex D17 rates this insufficient. Paths left open:
  * ChaosForge annotations or labels on Deployments, persisted by the recorder's spec snapshot [verify];
  * ChaosForge or proxy log lines in the swept namespace (the sweep now reads all Deployments, auxiliaries included);
  * experiment ids in events.
* **Rationale & Recommendation**:
  * Persist only allowlisted fields at ingestion: replicas, generation, spec hash, `*_ADDR`, resources.
  * Strip `chaosforge*` labels and annotations.
  * Exclude ChaosForge's own log streams.
  * Add a test that greps a frozen case bundle for the experiment id and the mechanism name, with the ground truth held on the evaluator side only.

---

### M15. Live and replay use two evidence paths, so offline arms are underspecified - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst` (F12)
* **Affected Scope:** Lines 57, 189-195, 255, 299-305, 661-665
* **Discrepancy Description**: The Investigator's tools fetch raw lines, events and the Lake live, and the runner "congela la ventana". The design never says the tools read from the frozen bundle. Arms with different adaptive queries (Lake with and without postmortems, Tider against direct LLM) break per-query fixtures. This is RFC N11, which the RFC IFR (2.5) resolved and the target only partly adopts.
* **Rationale & Recommendation**:
  * At t0, capture a superset bundle: all severities, all services, events, the recorder slice and the Services index from B1.
  * Serve the sweep and every Investigator tool through a `BundleAdapter` that implements `EvidenceAdapter`. In live mode, build the bundle on demand.
  * One code path means every arm re-runs offline on identical evidence.
  * Note the bundle limits: Cloud Logging quota, and export truncation (PM-04's export was cut at 20000 entries).
  * See also M3 and M6.

---

### N1. `retrieval_check.py` is exploratory, and its result is not used now - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out` (N1)
* **Affected Scope:** Lines 289-292, 683-690
* **Discrepancy Description**: The design says the result "se usa en la siguiente iteración, no en esta".
* **Rationale & Recommendation**: Make it the last optional item, built on `score_retrieval` (M3).

### N2. Existing rules-mode code (`catalog_diagnosis.py`) is not accounted for - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out` (N2)
* **Affected Scope:** Lines 207, 217, 542, 590
* **Discrepancy Description**: The verifier "reemplaza a `baseline.py`". But rules mode in `analysis.py` (lines 6-7, 64) also uses `catalog_diagnosis.diagnose_catalog`, which already does graph-path reasoning and failure-pattern regexes. `topology.py` and `signatures.py` overlap with it.
* **Rationale & Recommendation**: Name it in the plan. Either reuse its logic or remove it together with v1 (M4).

### N3. Signature count is inconsistent (4 vs 6), and two are unvalidated - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out` (N3) + `egm-inventive-catalyst` (F13)
* **Affected Scope:** Lines 50, 67, 233-234, 530-535, 545-548
* **Discrepancy Description**: Goal 3 says 4 signatures, but `catalog_v1.yaml` has 6. "Se cae al arrancar" and "sin memoria" have no injector or validation path. They pull in model fields (`terminaciones_en_ventana`, `motivo_fin`) that only they use. The design does not say whether they can reach CONFIRMADA and enter the candidate set.
* **Rationale & Recommendation**: Keep both reasons in the closed vocabulary and pick one of two options:
  * leave out their predicates and fields until an injector exists; or
  * add `estado: validada | declarada`. Declared signatures are traced but marked `no_validada`, never carry a catalog action, and are excluded from the confusion matrix.

### N4. Lab knowledge is hard-coded in the Cartógrafo, and Goal 3 contradicts a resolved question - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out` (N4)
* **Affected Scope:** Lines 50, 80, 90, 202
* **Discrepancy Description**: Nodes are marked `auxiliar` by matching name patterns, which puts application and lab knowledge in code, against the Lake-only rule. Goal 3 still requires "prioridad entre firmas", but the resolved question at line 80 removed fixed priority.
* **Rationale & Recommendation**: Mark auxiliaries in `topologia.yaml`, which already has an auxiliary entry. Reword Goal 3.

### N5. Implementation details sit in the Technical Plan - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out` (N5)
* **Affected Scope:** Lines 179, 193, 265 + 582, 269 + 572
* **Discrepancy Description**:
  * The Technical Plan holds implementation constants (10 s, 48 h, "40 registros").
  * The verb list is written out twice.
  * The judge's fixed rules sit inside `agentic.py`.
* **Rationale & Recommendation**: Move the constants to the Implementation Plan and settings. Put the judge rules in a small deterministic module (for example `judge_rules.py`) that `judge_set.py` can also use.

### N6. The loadgenerator control has no pre-registered expected label - Severity: Nit
* **Reviewer Lens:** `egm-inventive-catalyst` (F14)
* **Affected Scope:** Lines 128-132, 304, 655-656
* **Discrepancy Description**: RB-01 line 86 says "servicio sin instancias" confirms from Deployment state alone, so the verifier will CONFIRM it on `loadgenerator`. CUJ 3's "no atribuye una falla a ningún servicio de la tienda" needs loadgenerator to count as non-store. But line 202 classifies nodes by their presence in `topologia.yaml`, which lists loadgenerator.
* **Rationale & Recommendation**: Pre-register the control label in `protocol.yaml` (for example `{loadgenerator, servicio-sin-instancias, sin_impacto_en_tienda}`), as RFC N10 proposed, and score it separately.

### N7. Serial campaign cost, and an aggregate threshold that the near-trivial mechanism can meet on its own - Severity: Nit
* **Reviewer Lens:** `egm-inventive-catalyst` (F15)
* **Affected Scope:** Lines 64, 106, 312, 657
* **Discrepancy Description**: "Cerca de 14 horas de GKE en serie" is treated as fixed. With `scale_zero` on 11-12 services, a 60-case aggregate Wilson ≥ 70% can be met almost entirely by the near-trivial case (decision 18).
* **Rationale & Recommendation**:
  * Consider parallel isolated namespaces, each with its own ChaosForge.
  * Combined with M15, only the injections need GKE; LLM arms run offline.
  * Pre-register per-mechanism strata reporting, with a minimum per stratum alongside the aggregate. Small strata are descriptive only.

---

## Severity Summary

| Severity | Count | IDs |
| --- | --- | --- |
| Blocker | 1 | B1 |
| Major | 15 | M1-M15 |
| Nit | 7 | N1-N7 |

**Merged duplicates:** M2 (zoom-out M2 + catalyst F3), M5 (M5 + F8), M7 (M7 + F10), N3 (N3 + F13).

**Cross-references:**
* B1 -> M7, M8, M15
* M3 <-> M15
* M6 <-> M15
