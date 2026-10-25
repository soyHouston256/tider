"""Generic failure patterns bound to a reviewed documentary topology."""
import re
from .models import Analysis

FAILURE = re.compile(r'connection refused|no available endpoints|\bUnavailable\b|deadline exceeded|\btimeout\b|timed out', re.I)
NEGATED = re.compile(r'\b(no|without)\s+(errors?|failures?|timeouts?)\b|\bnot\s+unavailable\b', re.I)


def diagnose_catalog(incident_id, service, evidence, catalog):
    nodes = {s['id']: s for s in catalog.get('services', [])}
    edges = catalog.get('relations', [])
    adjacency = {s['name']: set() for s in nodes.values()}
    for edge in edges:
        if edge['source'] in nodes and edge['target'] in nodes:
            adjacency[nodes[edge['source']]['name']].add(nodes[edge['target']]['name'])

    def path_to(source, target):
        pending=[source]; seen=set()
        while pending:
            current=pending.pop()
            if current==target: return True
            if current in seen: continue
            seen.add(current); pending.extend(adjacency.get(current, ()))
        return False

    candidates={}
    for signal in evidence:
        match=FAILURE.search(signal.message)
        if not match or NEGATED.search(signal.message): continue
        # The named target must be in the same failure record and reachable from its reporter.
        named=[]
        for item in nodes.values():
            terms=[item['name'], *item.get('aliases', [])]
            if any(re.search(r'(?<![\w-])'+re.escape(term)+r'(?![\w-])',signal.message,re.I) for term in terms if term):
                named.append(item)
        # Do not guess between multiple mentioned services, even on a known path.
        if len(named)!=1: continue
        item=named[0]
        if not path_to(signal.service,item['name']): continue
        candidates.setdefault(item['name'],[]).append((signal,match.group()))
    if len(candidates)==1:
        component, matches=next(iter(candidates.items()))
        unavailable=any('refused' in pattern.lower() or 'endpoints' in pattern.lower() or pattern.lower()=='unavailable' for _,pattern in matches)
        symptom='no es accesible' if unavailable else 'no responde dentro del tiempo esperado'
        item=next(s for s in nodes.values() if s['name']==component)
        files=sorted({s['file'] for s in item.get('sources',[])})
        refs=', '.join(s.id for s,_ in matches[:8])
        return Analysis(incident_id=incident_id,component=component,evidence=evidence,confidence=.65,
            hypothesis=f'{component} {symptom} según la evidencia y el catálogo confirmado.',
            recommendation=f'Verificar conectividad, endpoints, readiness y dependencias de {component}. El síntoma no determina por qué falló. Evidencias: {refs}. Fuentes del catálogo: {", ".join(files)}.')
    return Analysis(incident_id=incident_id,component=service,evidence=evidence,confidence=0,status='insufficient_evidence',
        hypothesis='La evidencia no permite identificar una causa raíz.',
        recommendation='Revisar nombres y alias confirmados, relaciones documentadas y señales adicionales.' + (' Hay varios componentes candidatos.' if len(candidates)>1 else ''))
