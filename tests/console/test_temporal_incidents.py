from datetime import datetime, timedelta, timezone
from threading import RLock
from types import SimpleNamespace

import pytest

from tider.console.agentic import AgenticEngine
from tider.console.investigation_tools import InvestigationTools
from tider.console.models import AnalyzeRequest, Signal
from tider.console.providers.error_filter import is_error, logging_error_filter
from tider.console.providers.kubernetes_events import event_filter, event_from_entry
from tider.console.settings import Settings
from tider.llm import ScriptedLLM

START = datetime(2026, 10, 31, 14, 31, tzinfo=timezone.utc)
END = START + timedelta(minutes=10)


class Lake:
    lock = RLock()

    def __init__(self, names):
        self.names = names

    def catalog(self):
        return {'status':'confirmed','revision':1,'confirmed':{
            'services':[{'name':s} for s in self.names], 'relations':[]}}

    def snapshot_documents(self):
        return []


def cfg(**kwargs):
    return Settings(evidence_mode='gcp', llm_provider='anthropic', tider_model='test', **kwargs)


def req():
    return AnalyzeRequest(incident_id='TEST', objective='nadie puede entrar a la web',
                          scope='general', start=START, end=END, mode='gcp')


def event(service, minute=9):
    return {'service':service,'timestamp':(START+timedelta(minutes=minute)).isoformat(),
            'object_kind':'Deployment','object_name':service,'reason':'ScalingReplicaSet',
            'message':f'Scaled down replica set {service}-abc from 1 to 0',
            'mapping':'exact_workload_name','type':'Normal','availability_change':True}


def rows(events):
    return {'events':events,'records_read':len(events),'truncated':False,'incomplete':None}


@pytest.mark.parametrize('message', [
    'Type Name # reqs # fails | Avg Min Max Med | req/s failures/s',
    '<bf> { bf-error-rate : 0.01 }',
    '<search> Cluster configuration: AUTO partitions, coordinator timeout: 0ms',
    '<search> gc: ON, query timeout (ms): 500, timeout policy: return',
    'error_rate=0.01',
])
def test_statistical_headings_and_configuration_are_not_errors(message):
    assert not is_error(message)


@pytest.mark.parametrize('message', [
    'shippingservice failed', 'connection refused', 'request timed out',
    'StackExchange.Redis.RedisConnectionException: SocketClosed (ReadEndOfStream)',
    'RPC timeout while connecting',
])
def test_actual_failures_still_match(message):
    assert is_error(message)


def test_cloud_filter_uses_word_boundaries_and_escapes_regex_for_the_api():
    query = logging_error_filter()
    assert 'jsonPayload.message=~' in query
    assert r'\\b' in query  # JSON escapes reach RE2 as a literal word boundary.
    assert 'severity >= ERROR' in query


def test_historical_event_filter_includes_scope_window_and_both_pod_and_cluster_events():
    query = event_filter(START, END, cfg(), ['storefront','session-cache'])
    for value in ['tider-ops','chaosforge-lab','us-central1','boutique','logs/events',START.isoformat(),END.isoformat()]:
        assert value in query
    assert 'k8s_container' not in query
    assert 'involvedObject.name' in query and 'involvedObject.namespace' in query
    assert 'session-cache' in query and r'\\-' not in query


def test_event_mapping_and_time_cannot_escape_the_authorized_scope():
    entry = SimpleNamespace(timestamp=START+timedelta(minutes=5), payload={
        'involvedObject':{'name':'storefront','kind':'Deployment','namespace':'boutique'},
        'reason':'ScalingReplicaSet','message':'Scaled from 1 to 0','type':'Normal'})
    parsed = event_from_entry(entry,['storefront'],'boutique',START,END)
    assert parsed['mapping']=='exact_workload_name' and parsed['availability_change']
    assert event_from_entry(entry,['storefront'],'another-namespace',START,END) is None
    assert event_from_entry(entry,['another-service'],'boutique',START,END) is None
    assert event_from_entry(entry,['storefront'],'boutique',END,END+timedelta(minutes=1)) is None
    entry.payload['involvedObject'].update(name='storefront-abc-xyz',kind='Pod')
    assert event_from_entry(entry,['storefront'],'boutique',START,END)['mapping']=='name_prefix_not_verified_ownership'


@pytest.mark.parametrize('current,previous', [('frontend','redis-cart'),('gateway','session-store')])
def test_old_dependency_error_cannot_hide_a_later_outage_even_if_judge_would_approve(monkeypatch,current,previous):
    monkeypatch.setattr('tider.console.investigation_tools.gcp_signals',lambda *a,**k:[
        Signal(timestamp=START+timedelta(minutes=5),service=previous,source='log',message='connection refused')])
    monkeypatch.setattr('tider.console.investigation_tools.gcp_events',lambda *a,**k:rows([event(current)]))
    # Even citing the event query is insufficient if the finding ignores that workload entirely.
    llm=ScriptedLLM({'investigator':{'action':'final','component':previous,'finding':'The old error explains the outage',
                                   'cites':['Q1','Q2']},'judge':{'supported':True,'notes':'Would approve'}})
    result=AgenticEngine(cfg(agent_max_steps=2),Lake([current,previous]),llm).analyze_live(req())
    assert result.status=='partial' and result.component=='desconocido'
    assert result.investigation['review_status']=='temporal_gap'
    assert not result.workflow.verdict.supported
    assert current in result.workflow.verdict.notes
    assert not any(agent=='judge' for agent,_ in llm.calls)


def test_silent_frontend_can_be_investigated_from_historical_events_without_error_logs(monkeypatch):
    monkeypatch.setattr('tider.console.investigation_tools.gcp_signals',lambda *a,**k:[])
    monkeypatch.setattr('tider.console.investigation_tools.gcp_events',lambda *a,**k:rows([event('frontend')]))
    llm=ScriptedLLM({'investigator':{'action':'final','component':'frontend','finding':'Se redujeron réplicas; actor no determinado.',
                                   'cites':['Q2']},'judge':{'supported':True,'notes':'Evento histórico citado'}})
    result=AgenticEngine(cfg(),Lake(['frontend','redis-cart']),llm).analyze_live(req())
    assert result.status=='hypothesis' and result.component=='frontend'
    assert result.investigation['observations'][0]['kind']=='empty'
    assert [s.source for s in result.evidence]==['event']
    assert result.investigation['observations'][1]['data']['events'][0]['signal_ids']==['S01']


def test_overlapping_incidents_are_reported_separately(monkeypatch):
    monkeypatch.setattr('tider.console.investigation_tools.gcp_signals',lambda *a,**k:[
        Signal(timestamp=START+timedelta(minutes=5),service='cartservice',source='log',message='Redis connection refused')])
    monkeypatch.setattr('tider.console.investigation_tools.gcp_events',lambda *a,**k:rows([
        event('redis-cart',5),event('frontend',9)]))
    llm=ScriptedLLM({'investigator':{'action':'final','component':'frontend','finding':'Cambio posterior en la entrada web.',
        'cites':['Q2'],'other_findings':[{'component':'redis-cart','finding':'Episodio anterior separado.', 'cites':['Q1','Q2']}]},
        'judge':{'supported':True,'notes':'Se distinguen ambos episodios'}})
    result=AgenticEngine(cfg(),Lake(['frontend','redis-cart','cartservice']),llm).analyze_live(req())
    assert result.status=='hypothesis' and result.component=='frontend'
    assert result.investigation['candidate']['other_findings'][0]['component']=='redis-cart'


def test_events_have_a_separate_cache_key_and_validate_query_bounds(monkeypatch):
    calls=[]
    def read(*a,**kw):
        calls.append(kw)
        return rows([event('frontend')])
    monkeypatch.setattr('tider.console.investigation_tools.gcp_events',read)
    tools=InvestigationTools(cfg(),req(),Lake(['frontend']))
    first=tools.search_events()
    second=tools.search_events()
    assert first==second and len(calls)==1 and len(tools.signals)==1
    assert tools.log_remaining==1999
    with pytest.raises(ValueError):
        tools.search_events(services=['outside'])
    with pytest.raises(ValueError):
        tools.search_events(start='2000-01-01T00:00:00Z')
    with pytest.raises(ValueError):
        tools.search_events(limit=201)


def test_empty_event_metadata_is_not_evidence(monkeypatch):
    monkeypatch.setattr('tider.console.investigation_tools.gcp_signals',lambda *a,**k:[])
    monkeypatch.setattr('tider.console.investigation_tools.gcp_events',lambda *a,**k:rows([]))
    llm=ScriptedLLM({'investigator':{'action':'final','component':'frontend','finding':'Unsupported','cites':['Q2']},
                    'judge':{'supported':True,'notes':'Must not be called'}})
    result=AgenticEngine(cfg(agent_max_steps=2),Lake(['frontend']),llm).analyze_live(req())
    assert result.status=='insufficient_evidence'
    assert not any(agent=='judge' for agent,_ in llm.calls)
