from datetime import datetime, timezone
from tider.console.models import Signal
from tider.console.catalog_diagnosis import diagnose_catalog


def catalog(target='deliveryservice', alias='delivery'):
    return {'services':[{'id':'a','name':'web','sources':[]},{'id':'b','name':target,'aliases':[alias], 'sources':[{'file':'architecture.md'}]}], 'relations':[{'source':'a','target':'b'}]}


def signal(message,service='web'):
    return Signal(id='S01',timestamp=datetime.now(timezone.utc),service=service,source='log',message=message)


def test_arbitrary_service_and_info_error():
    r=diagnose_catalog('x','general',[signal('delivery quote failed: connection refused')],catalog())
    assert r.component=='deliveryservice' and r.status=='hypothesis'
    assert 'architecture.md' in r.recommendation and 'S01' in r.recommendation


def test_no_alias_no_invented_mapping():
    c=catalog();c['services'][1]['aliases']=[]
    assert diagnose_catalog('x','general',[signal('delivery quote failed: connection refused')],c).status=='insufficient_evidence'


def test_unknown_reporter_and_ambiguous_alias():
    assert diagnose_catalog('x','general',[signal('delivery unavailable','unknown')],catalog()).status=='insufficient_evidence'
    c=catalog();c['services'].append({'id':'c','name':'other','aliases':['delivery']})
    assert diagnose_catalog('x','general',[signal('delivery unavailable')],c).status=='insufficient_evidence'


def test_graph_alone_and_negation_not_evidence():
    for text in ['delivery is healthy','delivery not unavailable']:
        assert diagnose_catalog('x','general',[signal(text)],catalog()).status=='insufficient_evidence'


def test_two_candidates_abstain():
    c=catalog();c['services'].append({'id':'c','name':'billing','aliases':[]});c['relations'].append({'source':'a','target':'c'})
    assert diagnose_catalog('x','general',[signal('delivery unavailable'),signal('billing timeout')],c).status=='insufficient_evidence'
