from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from google.cloud.logging_v2.types import ListLogEntriesResponse, LogEntry

from tider.console.providers.cloud_logging import gcp_signals
from tider.console.providers.logging_sdk import BoundedLoggingClient
from tider.console.settings import Settings


def test_each_page_has_remaining_timeout_no_retry_and_follows_empty_pages(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr('tider.console.providers.logging_sdk.monotonic', lambda: clock[0])
    client = Mock()
    calls = []
    def read(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            clock[0] = 7
            page = ListLogEntriesResponse(next_page_token='second')
        else:
            page = ListLogEntriesResponse(entries=[LogEntry(text_payload='failed', severity=500,
                timestamp='2026-10-31T05:24:10Z', labels={'k8s-pod/app':'frontend'})])
        return SimpleNamespace(pages=iter([page]))
    client.list_log_entries.side_effect = read
    reader = BoundedLoggingClient('test-project', 9, client)
    rows = list(reader.list_entries('scoped', 'timestamp desc', 100, 201))
    assert rows[0].payload == 'failed' and rows[0].severity == 'ERROR'
    assert [c['timeout'] for c in calls] == [9, 2]
    assert all(c['retry'] is None for c in calls)
    assert calls[1]['request']['page_token'] == 'second'
    assert calls[0]['request']['resource_names'] == ['projects/test-project']


def test_partial_page_failure_keeps_rows_and_marks_incomplete(monkeypatch):
    now = datetime.now(timezone.utc)
    def rows():
        yield SimpleNamespace(payload='connection refused', labels={'k8s-pod/app':'frontend'},
                              timestamp=now, severity='ERROR')
        raise TimeoutError('provider details')
    fake = Mock()
    fake.list_entries.return_value = rows()
    monkeypatch.setattr('tider.console.providers.logging_sdk.BoundedLoggingClient', lambda *a: fake)
    result = gcp_signals('general', now-timedelta(minutes=10), now, Settings(evidence_mode='gcp'),
                         services=['frontend'], max_records=201, deadline=float('inf'))
    assert len(result) == 1 and result[0].service == 'frontend'
    assert result.incomplete['code'] == 'timeout'
    assert 'provider details' not in str(result.incomplete)
    fake.close.assert_called_once()
