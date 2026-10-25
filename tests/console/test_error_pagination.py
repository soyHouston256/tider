from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from tider.console.providers.cloud_logging import gcp_signals
from tider.console.settings import Settings


def entry(i):
    return SimpleNamespace(payload={'message':f'shippingservice failed {i}'}, labels={'k8s-pod/app':'checkoutservice'},timestamp=datetime.now(timezone.utc),severity='INFO')


def test_reads_errors_beyond_first_page(monkeypatch):
    from google.cloud import logging_v2
    fake=Mock()
    def pages():
        for page in range(3):
            for i in range(100): yield entry(page*100+i)
    fake.list_entries.return_value=pages()
    monkeypatch.setattr(logging_v2,'Client',lambda **kw:fake)
    now=datetime.now(timezone.utc)
    signals=gcp_signals('checkoutservice',now-timedelta(minutes=5),now,Settings(evidence_mode='gcp'))
    assert len(signals)==300
    assert signals[-1].message.endswith('299')
    assert fake.list_entries.call_args.kwargs['max_results'] is None
    assert 'jsonPayload.message=~' in fake.list_entries.call_args.kwargs['filter_']
    fake.close.assert_called_once()


def test_empty_errors_uses_bounded_activity_sample(monkeypatch):
    from google.cloud import logging_v2
    fake=Mock();fake.list_entries.side_effect=[iter([]),iter([entry(1)])]
    monkeypatch.setattr(logging_v2,'Client',lambda **kw:fake)
    now=datetime.now(timezone.utc)
    assert len(gcp_signals('frontend',now-timedelta(minutes=5),now,Settings(evidence_mode='gcp')))==1
    assert fake.list_entries.call_args.kwargs['max_results']==100


def test_page_failure_is_not_silently_partial(monkeypatch):
    from google.cloud import logging_v2
    def broken():
        yield entry(1)
        raise RuntimeError('page failed')
    fake=Mock();fake.list_entries.return_value=broken()
    monkeypatch.setattr(logging_v2,'Client',lambda **kw:fake)
    now=datetime.now(timezone.utc)
    with pytest.raises(RuntimeError):
        gcp_signals('frontend',now-timedelta(minutes=5),now,Settings(evidence_mode='gcp'))
    fake.close.assert_called_once()
