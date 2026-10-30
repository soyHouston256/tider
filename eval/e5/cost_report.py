"""Reprice saved usage without contacting the provider; list estimate, not an invoice."""
import json
import statistics
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def main():
    methods={}
    records=[json.loads(p.read_text()) for p in (ROOT/'results/runs').glob('*.json')]
    assert len(records)==96, f'Expected 96 runs, found {len(records)}'
    for r in records:
        cost=0.0
        for c in r['calls']:
            u=c.get('usage',{})
            assert u.get('input_tokens',0)<=100000
            assert not u.get('cache_read_input_tokens',0) and not u.get('cache_creation_input_tokens',0)
            assert c.get('model_returned','claude-haiku-5-5')=='claude-haiku-5-5'
            cost+=(u.get('input_tokens',0)*0.10+u.get('output_tokens',0)*0.50)/1e6
        methods.setdefault(r['method'],[]).append(cost)
    out={'source':'https://platform.claude.com/docs/en/about-claude/pricing','consulted':'2026-10-29','currency':'USD','basis':'Haiku 5.5, standard global, prompts <=100k, no cache, input $0.10/MTok and output $0.50/MTok','limitations':'List estimate, not billed charge. Excludes infrastructure, energy, storage and human review.','methods':{k:{'n':len(v),'mean':statistics.mean(v),'min':min(v),'max':max(v),'total':sum(v)} for k,v in methods.items()},'total_usd':sum(sum(v) for v in methods.values())}
    (ROOT/'results/costs.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(out,indent=2))

if __name__=='__main__':main()
