# Stage 6 · Comprehension Test

Target: `tider/docs/designs/tider-diseno-piloto.md` (FeatureRange 1–444, DetailedRange 445–727). Reviewer: egm-comprehension, which read only the target document.

**What this proposes**

Tider is a read-only incident advisor for microservices. This design turns it from an agent that names one component into a pipeline for the Online Boutique on GKE pilot. The pipeline has six steps:
1. A deterministic sweep collects evidence for every service in the namespace. It does not depend on the Context Lake. A new state recorder takes Kubernetes snapshots every 10 s.
2. A Cartographer builds a dependency graph. Its nodes come from the platform. Its edges are either configured in the Lake or observed in the specs and in errors.
3. A data-driven signature verifier marks each failure signature CONFIRMADA, DESCARTADA or SIN_DATOS.
4. An LLM Investigator ranks only the confirmed signatures as hypotheses. Each hypothesis has a role (cause, victim or independent) and an entity (a service or a link).
5. A Proposer returns a catalog runbook action only when the signature is confirmed and the runbook is validated. Otherwise it returns read-only diagnostic steps that pass through a verb filter.
6. A judge from OpenAI, preceded by fixed rules, validates the result.

The evaluation runs on ChaosForge injections. The ground truth is isolated on a separate port, the protocol is frozen and hashed before the first run, and the targets are about 60 cases, Wilson thresholds, a confirmatory McNemar test (OpenAI judge vs. no judge) and Cohen's kappa between two raters.

**How the existing system works, per this document**

An agent loop (`agentic.py`) starts with a global error search seeded from the Context Lake catalog. It returns a single component with citations and a free-text LLM recommendation. A judge reviews it using the same model as the investigator. Kubernetes state is read live, so by investigation time it no longer reflects the incident, because ChaosForge restores the service at 120 s. Event and log queries are filtered by the Lake's catalog. Nothing checks what the citations actually say. The map highlights one node. ChaosForge serves its answer key (`/api/evidence`) on the same port Tider reads observations from. A previous evaluation ("E5") can no longer be reproduced.

## Findings

1. **Major · CUJ 2 (line 126) vs. the "Sano confirmado" predicate (line 110).** The predicate says a service is healthy only if "ningún llamador con errores que lo nombren" (no caller has errors that name it). CUJ 2 says `redis-cart` is marked "sano confirmado, aunque los errores lo nombran" (healthy even though errors name it). Under the stated predicate, `redis-cart` would end up as "sin datos" or not healthy. A reader cannot tell which rule wins, or whether an exception exists, for example when the observed edge points at a different port than the one configured. The CUJ and the predicate need to agree, or the exception has to be stated.

2. **Major · Proposer (§7, lines 261–265; item 19, line 578); Non-Goals line 69 ("seis roles, de los cuales dos usan LLM"); flow.js stage list (line 282).** The Proposer is called "determinista" but makes a dedicated LLM call. The document then counts "2 roles LLM y 3 puntos de llamada". It is unclear whether the Proposer is an LLM role.
   - The "six roles" are never listed. The text names Recolector, Cartógrafo, Verificador, Investigador, Proponente, Juez and Reportero (seven), plus the Estado step.
   - The flow.js stage list leaves out the Cartographer.

   A new reader cannot reconstruct the role model the design keeps referring to.

3. **Major · Signature count.** Goal 3 (line 50) says "las 4 firmas del catálogo v1". Item 12 (line 533) says "6 firmas", with runbooks RB-01 to RB-06. Item 39 updates RB-01 to RB-04. The feature range says catalog v1 has four signatures. The detailed plan says six, of which four are validated. It is never stated that the two extra ones are "se cae al arrancar" and "sin memoria", and only the Non-Goals hint at it. Apart from RB-01 (restore replicas), no RB-ID is mapped to its failure mode.

4. **Major · Verificador de firmas (§4), Goal 3.** Goal 3 promises a truth table for each signature, but the document never states what any signature actually requires. For example, it never says which predicates confirm "servicio sin instancias" or rule out "configuración incorrecta". Without at least a one-line summary per signature, the reader cannot check CUJ 1–3 against the verifier. In CUJ 2, for instance, "el cambio de configuración precede al primer error" (the config change comes before the first error) appears as reasoning, but it is unclear whether that is a verifier predicate or Investigator judgment.

5. **Major · Judge fixed rule 2 (line 271), the Arista model (line 241), and the link entity.** Rule 2 requires the cause entity to have estado `falla`. Only nodos carry that 3-value state. When the hypothesis entity is a link (`cartservice→redis-cart`), the document does not say how the rule applies. The values of `Arista.estado` are never defined. Since latency cases are always link entities, this gap affects a whole class of evaluation cases.

6. **Major · CUJ 3 (lines 128–132).** `loadgenerator` is a Deployment in the namespace, so it is in the inventory. Scaled to zero, it would satisfy "servicio sin instancias". The document does not explain how Tider avoids reporting that as the cause. Possible mechanisms include auxiliar classification or exclusion from the store roles, but none is stated. It also does not say how the report knows to say that traffic generation stopped. The auxiliar rule (line 202: not in `topologia.yaml` and name matches a lab or observability pattern) is not tied to this case, and the patterns are not given.

7. **Major · Evaluation sets: "historial / evaluación / control" (lines 58, 304, 312, 718), "5 corridas de historial y los postmortems".** The document never explains what the history set is for. The likely meaning is that these runs produce postmortems that go into the Lake, but that is not stated. It also never defines what a control case is. The reader has to infer that history runs feed the Lake's memory and must not overlap with evaluation. That separation is a key anti-contamination claim, and the reader has to guess it.

8. **Major · Kappa (Goal 11, CUJ 4, §12 `kappa_form.csv`, item 37).** The document names "Alberto y Jose" but never says who they are or what expertise they have. It does not say what they rate: the "3 preguntas acordadas" are never listed. It also does not say what "la variante que los produjo" means; the variants are presumably the arms, but that is never stated. Because kappa answers the course rubric objection, the reader needs to know what agreement is being measured.

9. **Major · "Falla confirmada" (line 197), "servicios con anomalía" (line 213), and the incident window and `t0` (lines 150, 193, 494).** "Errores propios con anomalía respecto de la línea base" (own errors that are anomalous against the baseline) is not defined. The mean ± 3σ rule is given only for signature thresholds. It is also unclear how `t0` relates to the operator's requested window. `t0` could be the injection time, the start of the window, or something else, and in real use there is no injection. Goal 2 promises an explicit predicate only for "healthy", which leaves the "failure" state underspecified.

10. **Nit · "the proxy" / `chaosforge-proxy` (lines 84, 205, 546).** The document mentions "la latencia introducida en el proxy" and `REDIS_ADDR=chaosforge-proxy:6379` without explaining that ChaosForge injects latency by rerouting `cartservice` through a proxy in front of Redis. That is why the link entity exists, so the mechanism deserves one sentence.

11. **Nit · "Observador de ChaosForge" (lines 181, 184, 297).** The document uses it as an evidence source (Redis PING latency, `/api/observations`, Prometheus CPU) but never introduces it as a component.

12. **Nit · References that are not defined in the document.** All of these are cited as rationale or context without a one-line gloss:
    - "E5" and "caso C09"
    - "rúbrica del curso (C1–C4, 10/20)"
    - "OpenRCA A.5"
    - "cláusula 5"
    - the "[INF]" marker
    - "el pitch"
    - "LLM directo"
    - "atlas de 13 páginas" and "grafo del núcleo / ejecutor"
    - "D08"
    - "SIBI", used at line 6 but described only at line 330
    - decision numbers 1–27

    The decision numbers are mostly glossed inline, which is acceptable.

13. **Nit · Service counts (Goal 1, line 48; lines 90 and 191).** Goal 1 says the inventory comes from Deployments and that "los 12 servicios" appear. Later the inventory is Deployments plus StatefulSets, including auxiliaries. It is unclear whether 12 counts only store services and whether auxiliaries add rows to the sweep table. The NFR budget of "12 servicios × 40" assumes exactly 12.

14. **Nit · Proposer retry count (line 265 vs. lines 437 and 581).** §7 implies a single LLM attempt before falling back to the runbook. The NFR and item 19 allow two attempts ("rechaza dos veces").

15. **Nit · Field name.** `recomendacion` (§5, line 246) vs. `recomendacion_estructurada` (item 15). Item 15 also adds `incompleto`, which §5 does not list.

16. **Nit · Judge rule 5 (line 274).** The rule says "cobertura baja", but no threshold is given. The rule marks the analysis `incompleto` rather than rejecting it, which contradicts the opening line of the list ("Un incumplimiento rechaza el diagnóstico", a violation rejects the diagnosis).

17. **Nit · Line 447, "partir de `archivo-grafo-antiguo` una vez confirmada".** The document does not say what must be confirmed, or by whom, before work branches off.

18. **Nit · Line 534.** "Las 4 firmas a validar pasan a `validado: true` solo después de la Fase 6" reads as unconditional. Line 696 says a signature that fails stays "declarado, no validado". The condition should be stated in item 12 as well.
