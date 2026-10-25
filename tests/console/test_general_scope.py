from unittest.mock import Mock, patch

import pytest

from tider.console.models import AnalyzeRequest
from tider.console.providers import EvidenceProvider
from tider.console.settings import Settings
from tider.console.analysis import LabEngine


def request(**kwargs):
    return AnalyzeRequest(incident_id='general-test', start='2026-10-25T10:00:00Z', end='2026-10-25T10:10:00Z', **kwargs)


def test_general_queries_only_confirmed_catalog():
    lake = Mock()
    lake.catalog.return_value = {'status': 'confirmed', 'confirmed': {'services': [{'name': 'frontend'}, {'name': 'paymentservice'}]}}
    provider = EvidenceProvider(Settings(), lake)
    with patch('tider.console.providers.gcp_signals', return_value=[]) as read:
        provider.load(request(scope='general', mode='gcp'))
    assert read.call_args.kwargs['services'] == ['frontend', 'paymentservice']
    lake.query_scope.assert_not_called()


def test_general_requires_confirmation():
    lake = Mock()
    lake.catalog.return_value = {'status': 'pending'}
    with patch('tider.console.providers.gcp_signals') as read:
        with pytest.raises(ValueError, match='Confirma'):
            EvidenceProvider(Settings(), lake).load(request(scope='general', mode='gcp'))
        read.assert_not_called()


def test_general_mock_diagnoses_without_selected_service():
    req = request(scope='general', mode='mock', scenario='redis_down')
    evidence = EvidenceProvider(Settings()).load(req)
    result = LabEngine(Settings()).analyze(req, evidence)
    assert req.service is None
    assert result.component == 'redis-cart'
    assert result.status == 'hypothesis'


def test_focused_requires_service():
    with pytest.raises(ValueError, match='Selecciona'):
        request(scope='focused')
