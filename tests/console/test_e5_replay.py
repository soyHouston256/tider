"""Protect the frozen protocol against leakage and permissive transcript replay."""
import importlib.util
import json
from pathlib import Path
import pytest

PATH=Path(__file__).resolve().parents[2]/'eval/course_e5.py'
spec=importlib.util.spec_from_file_location('course_e5',PATH)
eval5=importlib.util.module_from_spec(spec)
spec.loader.exec_module(eval5)

def test_corpus_integrity_and_point_in_time():
    manifest,cases,labels=eval5.verify_data()
    assert len(cases)==12 and set(labels)=={c['id'] for c in cases}
    for case in cases:
        assert 'expected_component' not in json.dumps(case)
        req=eval5.AnalyzeRequest.model_validate(case['request'])
        for raw in case['signals']:
            signal=eval5.Signal.model_validate(raw)
            assert req.start<=signal.timestamp<=req.end

def test_replay_rejects_changed_prompt_but_ignores_wall_clock():
    key=eval5.prompt_hash('judge','system',json.dumps({'observations':[{'elapsed_seconds':1,'data':'x'}]}))
    rec={'prompt_sha256':key,'response_text':'{"supported":true}'}
    m=eval5.RecordedModel('unused',replay=[rec])
    assert m.complete_json('judge','system',json.dumps({'observations':[{'elapsed_seconds':99,'data':'x'}]}))['supported']
    m=eval5.RecordedModel('unused',replay=[rec])
    with pytest.raises(AssertionError):m.complete_json('judge','changed system',json.dumps({'observations':[{'data':'x'}]}))
