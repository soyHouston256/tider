# Goldfish Review Report — Stage 9 (Implementation Readiness Test)

**Target:** `/Users/maxhoustonramirezmartel/code/utec/5/integrador/project/code/tider/docs/designs/tider-diseno-piloto.md` (`445-727`; lines 1-444 used as reference only)

**Verdict: NOT READY.** The file list and phase order are a good skeleton. But several core algorithms (anomaly detection, destination resolution, the healthy predicate, the verifier truth table and role assignment), the pre-registered protocol content and the trace/replay path are named without being specified. Some instructions contradict a CUJ or the real codebase. An engineer would have to come back with questions.

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-implementation-readiness` | completed |
| `egm-codebase-details` | completed (ChaosForge source exists at `/Users/maxhoustonramirezmartel/code/utec/5/integrador/project/code/chaosforge/` and was checked) |
| `egm-style` | completed |

**Severity breakdown (after deduplication):** 11 Blocker, 27 Major, 18 Nit.

**References confirmed with no finding (codebase-details):**
- **Tider functions:** `gcp_signals`, `gcp_events`, `event_filter`, `event_from_entry`, `InvestigationTools.service_state`, `operation_evidence`, `observer_url`, `EDGES`, `related_services`, `baseline.diagnose`, `LabEngine`, `AnalysisService`, `proportion`, `paired`, `last_response_metadata`.
- **Line citations:** `agentic.py:377-388` and `:395-398`, `investigation_tools.py:44-51`, `catalog.js:146-164`.
- **Other references:** all Modify targets; D08 as the next decision; `eval.quality --verify`; the ChaosForge test command; `REDIS_ADDR=chaosforge-proxy:6379`; the V3 Lake contents (12 fichas, 6 runbooks, topologia.yaml).
- **Unverified:** the counts of 142 tests and 20 ruff errors (no shell available; a static count makes them plausible).

---

## Prioritized Findings (Blockers -> Major -> Nits)

### B1. No way to resolve an IP:port in an error to a service - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** Lines 477-488, 493-495, 523 (and 110, 204)
* **Discrepancy Description**: RB-01 ("Cómo atribuir el IP:puerto", RB-01:46-55) and PM-04 show that callers' errors name the Service ClusterIP:port. A port alone is ambiguous: 50051 is used by both payment and shipping, and 6379 by both redis-cart and chaosforge-proxy. The recorder does not snapshot `services`, and the RBAC role does not grant them. Three things depend on this resolution: healthy predicate clause 2, the observed edges, and victim attribution in CUJ 1. None of them can be implemented as written.
* **Rationale & Recommendation**:
  - Add `services` to the recorder snapshot and to the RBAC role.
  - Add a function, with its file and signature, such as `resolve_destination(ip, port, t) -> servicio | None`. It should try the ClusterIP first, then pod IPs via EndpointSlices or Pods, and never attribute by port alone.
  - Give the regexes for the Go and Python error formats quoted in RB-01.
  - Add tests for the 50051 and 6379 ambiguity.

### B2. "Anomalía respecto de la línea base" is never defined - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** Lines 493-495, 513 (and 197, 213)
* **Discrepancy Description**: A confirmed fault and the verifier's candidate set both depend on "anomalía". Item 7 only says the baseline window has the same length. It gives no statistic, threshold or minimum count. RB-01 also requires two rules the plan never mentions:
  - discard lifecycle noise (ERROR lines between `Killing` and the start log, such as the Node DeprecationWarning in PM-04);
  - group a multi-line Python trace as one event.
* **Rationale & Recommendation**: In item 7, specify the anomaly function, the template de-duplication, the trace grouping and the lifecycle-noise exclusion, each with a test.

### B3. `estado_servicio()` is in the wrong phase and its dependencies are circular - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** Lines 493-495, 514-515 (against 521-541)
* **Discrepancy Description**: `estado_servicio()` sits in `sweep.py` (Phase 1), but it needs three things that come later:
  - caller errors and caller traffic, from the graph (Phase 2, item 10);
  - "alguna firma CONFIRMADA", from the signatures (Phase 2, item 13).

  At the same time, the verifier picks its candidates from "servicios con anomalía", which is an output of the state computation.
* **Rationale & Recommendation**:
  - Fix the call order explicitly: sweep → topology → signatures → estado_servicio.
  - Move the function to its own module (or into `signatures.py`) with the signature `estado_servicio(barrido, grafo, veredictos, k) -> dict[str, Nodo]`.
  - Move its tests to Phase 2.

### B4. CUJ 2 contradicts the healthy predicate - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** Lines 495, 722 (against 110, 126)
* **Discrepancy Description**: CUJ 2 requires `redis-cart` to come out as "sano confirmado aunque los errores lo nombran". Predicate clause 2 forbids a healthy state whenever a caller's errors name the service. Line 722 requires CUJ 1-4 to reproduce, so no implementation can satisfy both.
* **Rationale & Recommendation**: Decide the rule. For example: errors that name a destination whose own platform and traffic evidence is healthy, and whose caller had a preceding config Change, do not count against that destination. Write the rule into item 7 and add a wrong_port test.

### B5. The verifier truth table and the catalog schema are not specified - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-style`
* **Affected Scope:** Lines 533-540 (and 214)
* **Discrepancy Description**:
  - "precedencia SIN_DATOS → DESCARTADA → CONFIRMADA" does not say whether the arrows mean evaluation order or which verdict wins.
  - The verdict on `conflicto` is not stated here. Decision 27.4 says DESCARTADA plus the `conflicto` flag.
  - The plan does not cover the case where data is present, a mandatory predicate is false and no discard predicate fires (flagged in VALIDACION_CODEX §245).
  - It does not say whether "todo obligatorio + al menos un corroborante" is a general rule.
  - The `catalog_v1.yaml` schema is missing:
    - the keys;
    - the operators;
    - the unit of `persistencia`;
    - how OR alternatives are written (RB-01's mandatory predicate is a disjunction).
  - Codex also notes that RB-04 can confirm and discard at the same time, and that the common model has no CPU-usage field.
* **Rationale & Recommendation**:
  - Embed the full truth table, a YAML schema with one worked firma (RB-01), and the operator list.
  - Write the precedence out in words: "SIN_DATOS prevalece sobre DESCARTADA, y DESCARTADA sobre CONFIRMADA".
  - State what a conflict yields.
  - Add a CPU-usage field to the model, or drop that predicate from RB-04.

### B6. No one is assigned to compute the cause and victim roles - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** Lines 541-542, 567-575 (and 236, 240)
* **Discrepancy Description**: The contract has `rol` and `rol_en_principal`, but the plan never says whether the LLM or deterministic graph logic computes them. The rules-only `signatures.baseline()` must also order several confirmed firmas and assign roles without an LLM, yet Alternative J rejected any fixed order.
* **Rationale & Recommendation**:
  - Specify a deterministic function, for example `asignar_roles(hipotesis, grafo, nodos)`. A victim would be an upstream caller with errors resolved to the cause, starting at or after `t_inicio`.
  - Specify the ordering rule the baseline uses.
  - Say whether the LLM may override the roles.

### B7. The pre-registered protocol content is left to the implementer - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-style`
* **Affected Scope:** Lines 652-696 (items 33-37b)
* **Discrepancy Description**: `protocol.yaml` lists categories but no values:
  - the service×mechanism pair table;
  - the history/eval/control split;
  - the admission criteria and exclusions;
  - the ratio of true to false candidates (line 98 says it changes the result);
  - the mutation composition. L659 and L668 give it three different names, and the four transformations are never listed. The earlier lists at L98 and L306 also disagree with each other.

  Also undefined:
  - how the 3 repetitions are summarized per case (Codex §180 warns against fractional means under Wilson);
  - which repetition feeds the judge set;
  - the "3 preguntas acordadas" and "la variante" for kappa, and how the 30 cases are sampled (L681);
  - what "los 4 puntos del asesor" are (L690). "Asesor" also clashes with the product name.
* **Rationale & Recommendation**:
  - Put the concrete values in the plan, or add a pre-implementation item "congelar contenido del protocolo" with an owner and the exact tables.
  - Define the per-case summary rule.
  - List the 3 questions and the 4 points verbatim, and say "asesor académico".
  - Use one term for the fabricated diagnoses and list the transformations consistently with §12.

### B8. No item builds the per-run trace or the replay - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** Lines 567-575, 661-678 (and 299-301, Goal 10)
* **Discrepancy Description**: §12 and Goal 10 require a trace JSON in `out/runs/`. It must hold the prompt hashes, Lake manifest hash, catalog hash, sweep table, verdicts, Lake queries and returned ids, and judge decisions. `score.py` and `retrieval_check.py` depend on it. No file item creates:
  - the exporter;
  - its schema;
  - the replay path that "recalcula sin llamar a ningún proveedor".
* **Rationale & Recommendation**:
  - Add an item such as `src/tider/console/trace.py` with its JSON schema.
  - Say how the prompt hashes are computed and how replay feeds the recorded responses back in.
  - Add a test that recomputes the metrics with no provider.

### B9. Phase 5 leaves the ChaosForge suite red and breaks deploy tooling - Severity: Blocker
* **Reviewer Lens:** `egm-codebase-details`
* **Affected Scope:** Lines 641-645, 712
* **Discrepancy Description**: Item 30 changes `abrir-panel.sh` to open two tunnels, and item 28 moves `/api/state` to the admin port. Three files still expect the old setup:
  - `chaosforge/admin/tests/test_open_panel.py:35,55` asserts the single tunnel `service/chaosforge-admin 8092:8080`;
  - `chaosforge/scripts/verify-admin.sh:12-15` port-forwards `18080:8080` and curls `/api/state`;
  - `chaosforge/.github/workflows/deploy.yml:167` prints the old tunnel command.

  None of the three is in the file list. `python3 -m unittest discover -s admin/tests -v` would fail, which contradicts line 447 ("cada fase deja la suite en verde").
* **Rationale & Recommendation**:
  - Add the three files as Modify, with the new expected values.
  - Also update the docs that cite 8092 as the panel: `README.md:82`, `admin/README.md:63`, `admin/DEPLOYMENT.md:88` and `admin/EXPERIMENTS.md:43`.

### B10. The dual-port ChaosForge admin design is underspecified and misses files - Severity: Blocker
* **Reviewer Lens:** `egm-codebase-details`, `egm-implementation-readiness`
* **Affected Scope:** Lines 633-645
* **Discrepancy Description**: Today the admin runs on one port:
  - `server.py:116-121` has only `--port` (default 8080) and builds a single `make_handler(controller)` (`:18`, `:153`);
  - `Dockerfile:7-8` exposes 8080 only;
  - `admin.yaml:93,111-121,136-138` uses 8080 for the container, both probes and the Service;
  - `test_http.py:20` calls `make_handler(self.controller)`.

  The plan does not give:
  - the defaults for `--port` and `--admin-port`;
  - how `make_handler` is split;
  - which port the probes use;
  - the start-up and `stop()` handling of two `ThreadingHTTPServer` instances;
  - the Dockerfile change;
  - for `abrir-panel.sh`, the bind check on both 8092 and 8093, how two port-forwards run concurrently (today one runs in the foreground at `:51`), and what the script prints.
* **Rationale & Recommendation**: Specify all of the above and add `admin/Dockerfile` as a Modify item.

### B11. `tider-lake-load` cannot load into the running console - Severity: Blocker
* **Reviewer Lens:** `egm-codebase-details`
* **Affected Scope:** Lines 613-614, 716
* **Discrepancy Description**: `context_lake.py:132-149` uses `chromadb.EphemeralClient`, whose data lives in memory inside one process. A separate `tider-lake-load <carpeta>` CLI would index into its own memory and exit, so the console would never see the documents. Verification step 1 depends on this load.
* **Rationale & Recommendation**: Choose one option and state it:
  - load at console start-up, for example through a `LAKE_V3_PATH` setting;
  - an API endpoint;
  - a persistent Chroma client with a path setting.

---

### M1. The working branch does not exist and its condition is ambiguous - Severity: Major
* **Reviewer Lens:** `egm-codebase-details`, `egm-implementation-readiness`, `egm-style`
* **Affected Scope:** Line 447
* **Discrepancy Description**: `archivo-grafo-antiguo` was renamed to `chore/archivar-grafo-remediacion` (`.git/logs/HEAD:10-11`). Only `main` and `soyHouston256/saithe` exist, and `main` already contains `archive/legacy_engine/` and `tests/_archivo/`. "Una vez confirmada" does not say who confirms or what. `docs/decisions.md:107` and `docs/archive/INVENTARIO_ARCHIVADO.md:3` still use the old name.
* **Rationale & Recommendation**: Name the real base, probably `main`, and the starting commit. Fix the old name in both docs.

### M2. Phase order breaks "cada fase deja la suite en verde" - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** Lines 447, 590, 603-614
* **Discrepancy Description**: The Cartógrafo (Phase 2) needs `topologia.yaml` loaded, and the Proponente (Phase 3) needs `context_lake.get()` to read runbooks. Both are built in Phase 4 (items 23-24).
* **Rationale & Recommendation**: Move items 23-24 before Phase 2, or have Phases 2-3 read the files directly behind an interface.

### M3. Core types and the id scheme are undefined - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** Lines 458-461, 465, 493, 523, 540
* **Discrepancy Description**: `Evidencia`, `Barrido`, `Grafo`, `VeredictoFirma` and `EvidenceAdapter` have no fields or method signatures. The id format `S##` has two digits, but the sweep can produce 12×40 or more observations. The plan does not say how `S`/`D` ids are assigned, or whether they stay stable on replay.
* **Rationale & Recommendation**: Give field lists and types for each, and a deterministic id scheme, for example `S0001` per run.

### M4. `gcp_signals` cannot be reused unchanged, and the sampling is unspecified - Severity: Major
* **Reviewer Lens:** `egm-codebase-details`, `egm-implementation-readiness`, `egm-style`
* **Affected Scope:** Lines 459, 465-467
* **Discrepancy Description**:
  - `max_records` is a total cap, not a per-service quota (`cloud_logging.py:50-53`).
  - The message is rebuilt and sanitized (`cloud_logging.py:97-106,115`), and event messages are truncated to 800 characters (`kubernetes_events.py:47`). So nothing can supply `texto_original`.
  - The mapping from `sweep_timeout_seconds` to the client deadline (`cloud_logging.py:58-66`) is not stated.
  - "Tomada en orden temporal" could bias the sample toward the start of the window.
  - The baseline quota, the severities and the filter are not given.
  - L466 has an agreement error: singular "reutilizado" after "logs".
* **Rationale & Recommendation**: Say whether `cloud_logging.py` is modified, how the quota is enforced, where `texto_original` comes from, and the sampling strategy and filter.

### M5. The classifier for "actividad normal" traffic is undefined - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** Line 495 (and 111)
* **Discrepancy Description**: RB-01 relies on service-specific markers such as `[PlaceOrder]` and `request complete`. The plan does not say what counts as normal traffic, or where these patterns would live.
* **Rationale & Recommendation**: Specify the classifier and where the patterns are stored, for example in the ficha.

### M6. Event service assignment "por prefijo" is undefined and `services=None` breaks - Severity: Major
* **Reviewer Lens:** `egm-codebase-details`, `egm-implementation-readiness`, `egm-style`
* **Affected Scope:** Line 474
* **Discrepancy Description**:
  - `kubernetes_events.py:41` matches names against a known list (`s + '-'`), so without a list there is nothing to match.
  - `:19` (`sorted(services)`) and `:75` raise on `None`.
  - `:42` drops ambiguous names.
  - The plan does not say how many hash segments to strip, or how to handle Deployment versus StatefulSet names.
* **Rationale & Recommendation**: Match `involvedObject.name` against the platform inventory using the pod/ReplicaSet naming pattern. Handle `None` in all three places and add a test.

### M7. The ChaosForge observer cannot provide `latencia_dependencia_p95`, and its config is unnamed - Severity: Major
* **Reviewer Lens:** `egm-codebase-details`, `egm-style`
* **Affected Scope:** Lines 458, 465-470, 499-507
* **Discrepancy Description**:
  - `operational_observer.py:42,50-52` reads only `GET /cart` and returns `dependency_median_ms`, not a dependency p95 with its `destino`. RB-03 needs that value.
  - Observations are kept for only 24 h (`controller.py:215`) and are recorded only while faults are enabled (`server.py:144`).
  - "Si está configurado" and "si está habilitado" do not name a setting, and item 8 does not list one.
* **Rationale & Recommendation**: Either modify `operational_observer.py` (and list it) or read the raw `/api/observations` rows. Name the settings in item 8.

### M8. Recorder storage, settings and failure handling are unspecified - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** Lines 477-482
* **Discrepancy Description**: The plan gives none of the following:
  - the SQLite schema;
  - how the spec hash is computed;
  - the return types of `snapshots()` and `spec_at()`;
  - error handling when kubectl fails;
  - settings for the namespace, interval (10 s) and retention (48 h);
  - how the sweep finds the database;
  - how a gap in recording becomes SIN_DATOS (line 179).

  The reuse of `agent_reader_kubeconfig` and `agent_kube_context` (`settings.py:27-28`) is only implied by "mismo patrón".
* **Rationale & Recommendation**: Specify all of the above.

### M9. RBAC is missing the subject, the API groups and the Monitoring IAM grant - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** Lines 485-488 (and 313)
* **Discrepancy Description**:
  - No ServiceAccount or subject is named.
  - No `apiGroups` are given. EndpointSlices belong to `discovery.k8s.io`, and deployments, statefulsets and replicasets to `apps`. Compare `archive/legacy_engine/deploy/rbac.yaml:9-49`.
  - No item grants the Monitoring / Managed Prometheus IAM permission needed for CPU.
* **Rationale & Recommendation**: Name the subject and the API groups, and add an IAM step or script.

### M10. No pass criterion for validating a firma, and 4 versus 6 firmas is unclear - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-style`
* **Affected Scope:** Lines 533-534, 666, 696, 717 (against Goal 3, L50)
* **Discrepancy Description**:
  - Item 12 creates 6 firmas but speaks of "las 4 a validar" without naming them.
  - L534 says the 4 become `validado: true`, while L696 allows a firma to fail validation.
  - No confusion-matrix criterion sets `validado: true`.
  - The plan does not say how many no-fault runs calibrate the ±3σ thresholds, or whether validation runs are kept apart from evaluation cases.
* **Rationale & Recommendation**:
  - List the 4 firmas to validate and the 2 declared-only ones.
  - Rewrite L534 as "las firmas que superen la validación pasan a `validado: true`".
  - Define the pass criterion, for example: CONFIRMADA in every run of its mechanism, and DESCARTADA or SIN_DATOS in the run with no fault.
  - Define the run counts and the separation from evaluation cases.

### M11. The Proponente's runbook choice, retry and "determinista" label are unclear - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-style`
* **Affected Scope:** Lines 579-582 (and 261-265)
* **Discrepancy Description**:
  - Item 19 calls the module "determinista", but L581 has it call an LLM.
  - "Sin acción de catálogo" is shorthand for a compound condition.
  - "Rechaza dos veces" implies a retry that is never stated, and the plan does not say what the second attempt receives.
  - The runbook choice is called "más cercano" in one place and "correspondiente" in another, and is undefined when `razon = desconocida`.
  - The plan does not say how the "Acción de reparación sugerida" and "Pasos de verificación" sections are extracted from the runbook.
* **Rationale & Recommendation**:
  - Write the condition in full.
  - State "reintenta una vez" and what the second call receives.
  - Define the runbook fallback and heading-based section extraction.
  - Fix the label to "determinista salvo la llamada LLM de respaldo".

### M12. Judge rule 4 would reject every catalog recommendation - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** Lines 581-582 (against 273)
* **Discrepancy Description**: Rule 4 requires every recommendation to pass the verb filter, but RB-01's catalog action is `kubectl ... scale deploy`. Multi-word commands such as `aws ecs update-service` also clash with matching "palabras completas".
* **Rationale & Recommendation**: Apply rule 4 and the filter only to `tipo = diagnostico_no_verificado`, and define phrase matching.

### M13. Judge thresholds are missing and the rules do not cover links - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** Lines 572-575 (and 270-274)
* **Discrepancy Description**: Rule 5's "cobertura baja" has no threshold. Rule 2 (the cause must be in state `falla`) has no meaning when the cause is a link such as `cartservice→redis-cart`.
* **Rationale & Recommendation**: Define both.

### M14. Agentic v2 prompts, LLM output handling and judge outcomes are missing - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** Lines 567-575
* **Discrepancy Description**: The plan does not give:
  - the Investigator v2 prompt;
  - how the table, graph and firmas are serialized for the LLM;
  - what happens when the LLM output is invalid (repair, retry or reject);
  - the judge's input and output schema;
  - the final state after a rejection in the last round;
  - a field that marks a diagnosis as "respaldado", which the "afirmaciones incorrectas" metric needs.
* **Rationale & Recommendation**: Specify all of these, and add fields such as `respaldado: bool` and `motivo_rechazo`.

### M15. `OpenAILLM` API details are open and agentic.py assumes `AnthropicLLM` - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`, `egm-style`
* **Affected Scope:** Lines 558, 567-575 (and 433)
* **Discrepancy Description**:
  - Not chosen: Chat Completions or Responses API, the structured-output method, the default `judge_model`, and the env var for the key.
  - "Lanza un error claro" cannot be tested.
  - The redaction NFR (L433) is neither wired nor tested.
  - `agentic.py:197-198,208-209` passes the timeout and reads metadata only for `isinstance(llm, AnthropicLLM)`.
  - A single `llm` serves both the Investigator and the Judge (`:161,257,348`), and the plan does not say how a second client is built or injected in tests.
* **Rationale & Recommendation**:
  - Specify the API choices and the exception type and message.
  - Replace the isinstance checks with a protocol check, and add `judge_model=` to the constructor.
  - Add a redaction test.

### M16. Construction order breaks the v2 name inventory - Severity: Major
* **Reviewer Lens:** `egm-codebase-details`
* **Affected Scope:** Lines 567-569, 584-587
* **Discrepancy Description**: `agentic.py:160` builds `tools_factory(settings, request, lake)` first, and `InvestigationTools.__init__` raises unless the catalog is confirmed (`investigation_tools.py:44-45`). In v2 the service names come from the graph, which exists only after the sweep and topology steps. The plan does not define:
  - the new `tools_factory` and `InvestigationTools` signatures;
  - whether the confirmation check is removed in v2;
  - how `sweep_lines` gets the Barrido data;
  - whether `context_search` (`:157-166`) passes the new `where` filter.
* **Rationale & Recommendation**: Specify the new signatures and the order of construction.

### M17. v1/v2 selection and the rules-only path do not fit the current code - Severity: Major
* **Reviewer Lens:** `egm-codebase-details`, `egm-style`
* **Affected Scope:** Lines 542, 589-590 (item 21)
* **Discrepancy Description**:
  - `LabEngine.analyze` receives `list[Signal]` (`analysis.py:55`), but `signatures.baseline(veredictos)` needs Barrido, Grafo and verdicts.
  - `diagnose_catalog` (`analysis.py:59-66`) runs whenever the Lake is non-empty, so replacing `baseline.diagnose` covers only part of the rules path.
  - `service.py:55` chooses a path by `llm_provider`, not by `pipeline`.
  - There is no v2 path for mock mode (`settings.py:13`), which most tests use.
  - One concept has three names: "modo por reglas v2", "modo sin LLM" and "baseline sin LLM".
* **Rationale & Recommendation**:
  - Define how `AnalysisService` chooses v1 or v2.
  - Define the v2 mock adapter.
  - Use one term ("modo sin LLM"), and keep "v1/v2" for the pipeline version only.

### M18. Stage and role names collide and are inconsistent - Severity: Major
* **Reviewer Lens:** `egm-codebase-details`, `egm-style`
* **Affected Scope:** Lines 491, 521, 579, 625-629 (and 282)
* **Discrepancy Description**:
  - `explanation.py:12,58-61` already uses the stage `verificador` for post-execution verification.
  - The closed stage-to-title dict in `agentic.py:176-178` would raise KeyError on any new stage, and agentic.py is not in item 27.
  - `explain()` is used only by the rules engine (`analysis.py:129`).
  - L629 calls the Recolector "barrido", leaves out the Cartógrafo, and writes roles in lowercase.
* **Rationale & Recommendation**:
  - Fix one list of six capitalized role names.
  - Rename the conflicting stage.
  - Extend the `event()` mapping in agentic.py.

### M19. Context Lake limits and the lexical-only variant have no interface - Severity: Major
* **Reviewer Lens:** `egm-codebase-details`, `egm-implementation-readiness`
* **Affected Scope:** Lines 603-611, 683-689
* **Discrepancy Description**:
  - `MAX_DOCUMENTS` and `MAX_CHUNKS` are module constants (`context_lake.py:23-24`), and the error text at `:177` hard-codes them.
  - `ContextLake.__init__` (`:134`) takes no settings.
  - `search()` (`:205-216`) always combines both signals, so there is no lexical-only path for item 37b.
  - Keeping the front matter changes the input to `extract_candidates` (`:190`), and the plan does not address that.
* **Rationale & Recommendation**:
  - Define how the limits are injected from settings.
  - Add a lexical-only switch, reusing the pattern in `eval/quality/score.py:38`.
  - Address the change to the `extract_candidates` input.

### M20. The exploratory arms have no implementing items - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** Lines 683-690 (and 95)
* **Discrepancy Description**: No item builds these arms:
  - Tider versus a direct LLM;
  - the Lake with and without postmortems;
  - the judge run alone on fabricated candidates.

  L690 also overclaims: "justifica con datos la estrategia de chunking", for an analysis marked exploratory.
* **Rationale & Recommendation**: Add the items or cut the arms from scope explicitly, and rephrase L690 as "aporta evidencia exploratoria".

### M21. The loader scope is incomplete - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** Lines 613-614 (and 288, 718)
* **Discrepancy Description**:
  - `load_v3` names only fichas and runbooks.
  - The V3 folder also holds `README.md`, PM-01 to PM-05 (which already exist), `postmortems/datos/**`, `correr_corridas.sh` and `corridas.log`.
  - The plan does not say where the topology is persisted for `analyze_live`.
  - Item 37b counts a link ficha as relevant, but no link fichas exist.
* **Rationale & Recommendation**: List the exact include and exclude globs, decide whether the existing postmortems are indexed, and define relevance for links.

### M22. Dependencies, entry points and build commands are incomplete - Severity: Major
* **Reviewer Lens:** `egm-codebase-details`, `egm-implementation-readiness`, `egm-style`
* **Affected Scope:** Lines 561-565, 614, 711
* **Discrepancy Description**:
  - Item 17 does not register `tider-lake-load` in `[project.scripts]` (`pyproject.toml:29-30`).
  - The YAML parser dependency is not stated.
  - The `uv.lock` regeneration appears only in the Verification Plan.
  - `scripts/setup.sh:8` runs `uv sync --frozen --extra dev --extra gcp --extra llm`. The second command in L711 omits `--extra gcp`, and running the two in either order removes the other's extras.
  - The relation between `make setup` and `uv sync` (a sequence or an alternative?) is unclear.
* **Rationale & Recommendation**: Complete item 17, add `uv.lock` (and `setup.sh` if it changes) to the file list, and give one consistent build command.

### M23. The isolation test does not match its guarantee and has no implementing item - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-style`, `egm-codebase-details`
* **Affected Scope:** Lines 647-648 (against 297, Goal 9)
* **Discrepancy Description**:
  - The test checks that `observer_url()` "rechaza cualquier ruta distinta de la raíz". Goal 9 promises something broader: no configurable URL reaches the admin port or the evidence route.
  - No Modify item implements a change to `observer_url()` or `operation_evidence`.
  - Root-path rejection is already tested at `tests/console/test_operational_observer.py:33`.
* **Rationale & Recommendation**:
  - Align the test with Goal 9.
  - Add a Modify item if the behaviour changes.
  - Extend the existing test file instead of creating a duplicate.

### M24. The output field name does not match the §5 contract - Severity: Major
* **Reviewer Lens:** `egm-style`, `egm-implementation-readiness`
* **Affected Scope:** Line 554 (against 246)
* **Discrepancy Description**: The plan uses `recomendacion_estructurada`, but the contract uses `recomendacion`. The plan also leaves open:
  - the default `schema_version` for v1 records;
  - the type of `cobertura`;
  - the allowed values of `Arista.estado`.
* **Rationale & Recommendation**: Use the contract's field name and specify the three missing details.

### M25. Some test criteria and claims cannot be checked - Severity: Major
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** Lines 513, 617
* **Discrepancy Description**:
  - "Los filtros funcionan" (L617) is not a checkable criterion.
  - "El barrido cubre 12 servicios" (L513) ignores the auxiliary workloads that L90 and L493 include.
* **Rationale & Recommendation**:
  - Write L617 as an assertion, e.g. `search(where={'servicio': X})` returns only fragments of X.
  - Rewrite L513 as "los 12 servicios más los auxiliares presentes".

### M26. "McNemar" drifts from the pre-registered "McNemar exacto" - Severity: Major
* **Reviewer Lens:** `egm-style`, `egm-codebase-details`
* **Affected Scope:** Lines 674, 678, 693 (against 58, 97, 307)
* **Discrepancy Description**: The plan writes "McNemar" without "exacto". The variant matters for a pre-registered test. `paired()` already implements the exact test (`eval/quality/score.py:27-35`).
* **Rationale & Recommendation**: Write "McNemar exacto vía `paired()`" so nobody writes a second implementation.

### M27. Verification Plan steps are not executable as written - Severity: Major
* **Reviewer Lens:** `egm-style`, `egm-implementation-readiness`
* **Affected Scope:** Lines 695, 714-722
* **Discrepancy Description**:
  - L695: the "Context Lake/V3-…" path "fuera del repositorio" has no base path.
  - L714: "Sigue dando el mismo informe" does not say compared with what, or how.
  - L718-720: steps 3-5 are noun phrases with no command.
  - L722: CUJ 4 does not happen in the console, and "se reproducen" does not require the result to match each CUJ's "Then".
  - No item implements the "se detuvo la generación de tráfico" message from CUJ 3.
* **Rationale & Recommendation**:
  - Give the absolute base path.
  - Name the reference file and the comparison.
  - Write imperative steps with commands.
  - Rewrite L722 as "la salida cumple el 'Then' de los CUJ 1-3 en la consola; el CUJ 4 se cumple con `eval.pilot.score`".
  - Add the CUJ 3 message to an item.

---

### N1. Template fields and labels are used inconsistently - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** Lines 445, 452+, 709, 727
* **Discrepancy Description**: English labels are mixed into Spanish prose: "Detailed Implementation Plan", "(Create)", "(Modify)", "Build:". Many items lack the "Tipo / alcance" and "Por qué" fields (items 4, 8, 11-13, 17, 18, 20, 21, 24).
* **Rationale & Recommendation**: Use the item fields the same way in every item.

### N2. Some "Por qué" lines are only references - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** Lines 496, 525, 559, 611
* **Discrepancy Description**: Several "Por qué" lines give only a decision or goal number.
* **Rationale & Recommendation**: Add one clause of rationale, or name the resolved question.

### N3. Anglicisms follow no consistent policy - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** Lines 478, 549, 569, 606, 614, 690
* **Discrepancy Description**: "Punto de entrada" and "entry point" are used for the same thing. "Fixtures", "chunking", "front matter", "package-data" and "replay" appear in prose.
* **Rationale & Recommendation**: Keep code identifiers as they are, and translate or define the prose terms once.

### N4. Colloquial verbs replace the defined states - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** Lines 514-515, 596
* **Discrepancy Description**: "Sale sano", "sale sin datos" and "cae en los pasos" stand in for the defined states and actions.
* **Rationale & Recommendation**: Use the state names ("queda en sin datos") and "usa los pasos".

### N5. "+" is used as a conjunction and L546 has no verb - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** Lines 458, 546
* **Discrepancy Description**: "+" joins terms in prose, and L546 is a fragment.
* **Rationale & Recommendation**: Write "y" and full clauses.

### N6. Wrong tense and an unanchored "el ejecutor" - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** Lines 475, 488
* **Discrepancy Description**: L475 says "quedaba" for something that does not exist yet. "El ejecutor" (L488) is introduced only in Alternative A.
* **Rationale & Recommendation**: Write "quedaría" and "el ejecutor del grafo antiguo (archivado)".

### N7. Ambiguous calques - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** Lines 547, 693
* **Discrepancy Description**: "Negativo cercano" and "ejemplo de manual" are ambiguous.
* **Rationale & Recommendation**: Define both.

### N8. Chained prepositions make sentences hard to parse - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** Lines 572, 689
* **Discrepancy Description**: For example "reglas fijas del Juez del Technical Plan §8" and "compara la híbrida con la léxica con `paired()`".
* **Rationale & Recommendation**: Reword both.

### N9. The "verificada" label has three forms - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** Line 624 (against 52, 242)
* **Discrepancy Description**: "Verificada/no verificada", "sugerencia no verificada" and `diagnostico_no_verificado` name the same concept.
* **Rationale & Recommendation**: Use one label.

### N10. "Congelar" has three meanings - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** Lines 614, 664, 719
* **Discrepancy Description**: It means copying an evidence window, writing a manifest and hashing the protocol.
* **Rationale & Recommendation**: Use concrete verbs ("guarda una copia", "registra el hash").

### N11. Number style is mixed and item 37b breaks the numbering - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** Lines 533, 668, 681, 683, 688, 690
* **Discrepancy Description**: Numbers are written sometimes in words and sometimes as digits, and "37b" breaks the item numbering.
* **Rationale & Recommendation**: Pick one convention and renumber the items.

### N12. Undefined terms and counts - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** Lines 684, 688, 712-713
* **Discrepancy Description**: "Decidido al cerrar" does not say closing what. "MRR" is not spelled out and k=4 is not justified. "(142)" and "(20)" have no unit or date.
* **Rationale & Recommendation**: Define each term and add units and a date to the counts.

### N13. The stated status value does not match the Lake - Severity: Nit
* **Reviewer Lens:** `egm-codebase-details`
* **Affected Scope:** Line 696
* **Discrepancy Description**: The plan writes "declarado, no validado", but the front matter of RB-05 and RB-06 uses `declarada, no validada`.
* **Rationale & Recommendation**: Use the exact Lake value.

### N14. The `complete_json` signature does not match `llm.py` - Severity: Nit
* **Reviewer Lens:** `egm-codebase-details`
* **Affected Scope:** Line 558
* **Discrepancy Description**: `timeout` is keyword-only (`llm.py:76`). The Protocol also requires `complete_text` (`:42-44`). The existing metadata keys are `stop_reason/input_tokens/output_tokens` (`:67-71`), with no "modelo" key.
* **Rationale & Recommendation**: Align the signature with `llm.py`.

### N15. New settings lack bounds and are not reconciled with the log budget - Severity: Nit
* **Reviewer Lens:** `egm-codebase-details`
* **Affected Scope:** Lines 498-507
* **Discrepancy Description**: The new settings have no `Field(ge/le)` bounds, unlike the existing ones (`settings.py:18,23-26`). There are no recorder interval or retention settings. A quota of 40 per service across 12 services is not reconciled with `agent_log_budget` (`settings.py:26`).
* **Rationale & Recommendation**: Add bounds, the missing settings, and the reconciliation with the budget.

### N16. Some test paths are not exact - Severity: Nit
* **Reviewer Lens:** `egm-codebase-details`, `egm-implementation-readiness`
* **Affected Scope:** Lines 509, 541, 544, 592, 616
* **Discrepancy Description**:
  - Some test paths lack the `tests/console/` prefix.
  - `test_topology_catalog.py` already exists, and the plan does not say whether its `EDGES` tests stay v1-only.
  - `baseline()` has no tests.
* **Rationale & Recommendation**: Give full paths, state the fate of the existing tests, and add tests for `baseline()`.

### N17. Minor interface gaps - Severity: Nit
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** Lines 586, 610, 619-626
* **Discrepancy Description**:
  - `sweep_lines` has no template-id type, return format or limit.
  - The shape of `manifest()` and its canonical serialization are not given.
  - The colours, borders and edge legend are left open.
* **Rationale & Recommendation**: Specify each.

### N18. L582's matching sentence has no clear subject - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** Line 582
* **Discrepancy Description**: "Que aplica como palabras completas" has no clear subject or object.
* **Rationale & Recommendation**: Rewrite as "compara cada término como palabra o frase completa, sin distinguir mayúsculas, incluido el contenido de bloques de código".
