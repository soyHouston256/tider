from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tider.llm import AnthropicLLM, ModelResponseError


def model(text, stop_reason='end_turn'):
    llm = AnthropicLLM.__new__(AnthropicLLM)
    llm.model = 'test-model'
    llm.client = Mock()
    llm.client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(type='text', text=text)], stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=100, output_tokens=20))
    return llm


def test_remaining_timeout_reaches_provider_and_metadata_is_retained():
    llm = model('{"supported":true}')
    assert llm.complete_json('judge', 'system', 'user', timeout=2.5)['supported'] is True
    assert llm.client.messages.create.call_args.kwargs['timeout'] == 2.5
    assert llm.last_response_metadata == {'stop_reason':'end_turn', 'input_tokens':100, 'output_tokens':20}
    assert 'output_config' not in llm.client.messages.create.call_args.kwargs


def test_effort_is_only_sent_when_configured():
    llm = model('{"supported":true}')
    llm.effort = 'low'
    llm.complete_json('judge', 'system', 'user')
    assert llm.client.messages.create.call_args.kwargs['output_config'] == {'effort':'low'}


@pytest.mark.parametrize('text,stop,code', [
    ('{"supported":', 'max_tokens', 'truncated_response'),
    ('private raw payload', 'end_turn', 'invalid_json'),
])
def test_invalid_and_truncated_responses_are_explicit_and_do_not_leak_text(text, stop, code):
    llm = model(text, stop)
    with pytest.raises(ModelResponseError) as err:
        llm.complete_json('judge', 'system', 'user')
    assert err.value.code == code
    assert text not in str(err.value)
