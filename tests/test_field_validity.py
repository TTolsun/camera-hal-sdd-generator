"""Regression cases from the three saved libcamera test drafts."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from sdd import field_validity, generated_design, generated_visuals
from sdd.cli_checkpoint import design_validation_policy
from sdd.config import load
from sdd.facts.model import KnowledgeModel
from test_inhouse_template import TEMPLATE


SOURCE = r'''/**
 * \var FrameMetadata::FrameSuccess
 * The frame has been captured with success and contains valid data. All fields
 * of the FrameMetadata structure are valid.
 * \var FrameMetadata::FrameError
 * The frame data is partly or fully corrupted, missing or otherwise invalid.
 * This can for instance indicate a hardware transmission error, or invalid data
 * produced by the sensor during its startup phase. The sequence and timestamp
 * fields of the FrameMetadata structure is valid, all the other fields may be
 * invalid.
 * \var FrameMetadata::FrameCancelled
 * Capture stopped before the frame completed. The frame data is not valid. All
 * fields of the FrameMetadata structure but the status field are invalid.
 * \var FrameMetadata::FrameStartup
 * The frame has been successfully captured. All other fields of the
 * FrameMetadata structure are valid.
 */'''

PREVIOUS = ('`FrameSuccess`는 프레임 데이터와 모든 메타데이터 필드가 유효하지만, '
            '`FrameError`는 데이터가 유효하지 않으며 `sequence`와 `timestamp`만 유효합니다. '
            '`FrameCancelled`는 프레임 데이터와 상태를 제외한 모든 메타데이터 필드가 유효하지 않습니다.')
FRESH = ('`FrameError`에서는 프레임 데이터가 일부 또는 전체 손상되었거나 누락되는 등 유효하지 않으며, '
         '`sequence`와 `timestamp`는 유효하지만 나머지 필드는 유효하지 않을 수 있습니다.')
DECISION_COMPLETION = ('`FrameError`에서는 프레임 데이터가 일부 또는 전부 손상되었거나 없거나 유효하지 않으며, '
                       '`sequence`와 `timestamp`는 유효하지만 나머지 필드는 유효하지 않을 수 있습니다.')
DECISION_FAILURE = ('`FrameMetadata::FrameSuccess`에서는 프레임 데이터와 모든 메타데이터 필드가 유효하지만, '
                    '`FrameMetadata::FrameError`에서는 프레임 데이터가 유효하지 않고 메타데이터 중 시퀀스와 '
                    '타임스탬프만 유효하며 나머지 필드는 유효하지 않을 수 있습니다. `FrameMetadata::FrameCancelled`에서는 '
                    '프레임 데이터와 상태를 제외한 모든 메타데이터 필드가 유효하지 않습니다.')
DECISION_VERIFICATION = ('`FrameMetadata::FrameError`에서는 `sequence`와 `timestamp`만 유효하고 다른 필드는 '
                         '유효하지 않을 수 있으며, `FrameMetadata::FrameCancelled`에서는 프레임 데이터와 `status` '
                         '이외의 모든 필드가 유효하지 않습니다.')


def test_only_enabled_policy_binds_the_validity_validator():
    default = design_validation_policy({})
    active = design_validation_policy({'_check_field_validity': True})
    assert 'field_validity' not in default
    digest = hashlib.sha256(Path(field_validity.__file__).read_bytes()).hexdigest()
    assert active == {**default, 'field_validity': digest}


@pytest.mark.parametrize('claim', [PREVIOUS, DECISION_FAILURE, DECISION_VERIFICATION,
    'FrameError: only sequence and timestamp are valid. Other metadata fields may be invalid.',
    'FrameError: only sequence, timestamp, and status are valid.',
    'FrameError: sequence and timestamp are the only valid fields.',
    'FrameError: all the other fields are invalid.',
])
def test_stronger_validity_is_rejected_in_the_same_state(claim):
    with pytest.raises(ValueError, match='FrameMetadata::FrameError.*other fields may be invalid'):
        field_validity.check(claim, [SOURCE])


@pytest.mark.parametrize('claim', [FRESH, DECISION_COMPLETION,
    'FrameError에서는 `sequence`와 `timestamp`만 유효하다고 보장되며 나머지 필드는 유효하지 않을 수 있습니다.',
    'FrameError: only sequence and timestamp are guaranteed to be valid.',
    FRESH + ' `FrameCancelled`에서는 `status`만 유효합니다.',
    FRESH + ' FrameCancelled: only the status field is valid.',
    FRESH + ' 설정 입력값은 초기 구간에서만 유효합니다.',
    FRESH + ' 이 경로에서는 숫자 입력값 둘만 유효합니다.',
    'FrameError에서는 메타데이터 조건을 확인하며, 이 경로에서는 입력값 둘만 유효합니다.',
    'FrameError: other fields may be invalid, only listed input values are valid.',
])
def test_qualified_validity_and_other_scopes_are_preserved(claim):
    field_validity.check(claim, [SOURCE])


@pytest.fixture
def section_with_status_evidence(tmp_cfg):
    tmp_cfg.agent.kind = 'cli'
    tmp_cfg.agent.max_input_chars = 30_000
    section = load(TEMPLATE / 'sdd.yaml').section('vendor-contract')
    section.pop('reader_profile')
    section['design_topics'] = [t for t in section['design_topics'] if t['id'] == 'failure']
    section['design_requirements'] = [r for r in section['design_requirements'] if r['id'] == 'failure']
    topic, = section['design_topics']
    source = dict(id='metadata', file='framebuffer.cpp', start='/**', end=' */')
    topic['sources'] = [source]
    model = KnowledgeModel(meta={'source_commit': 'a' * 40}, evidence={'vendor-contract/failure/metadata': {
        'selector': source, 'file': source['file'], 'line': 39, 'status': 'available', 'commit': 'a' * 40,
        'text': SOURCE, 'sha256': hashlib.sha256(SOURCE.encode()).hexdigest(),
    }})
    return section, model


def test_failed_prose_is_corrected_through_existing_retry(tmp_cfg, section_with_status_evidence):
    section, model = section_with_status_evidence
    tags = []

    def chat(system, user, *, tag, response_schema):
        assert field_validity.INSTRUCTIONS in system
        tags.append(tag)
        text = DECISION_FAILURE
        if len(tags) == 2:
            assert 'source says "other fields may be invalid"' in user
            text = FRESH
        return json.dumps({'statements': [dict(text=text, quote_id='metadata:0', evidence=['metadata'],
                                             covers=['failure'], kind='behavior')]}, ensure_ascii=False)

    result = generated_design.generate(tmp_cfg, model, SimpleNamespace(chat=chat), section)
    assert [row['text'] for row in result.artifact['answers']['failure']] == [FRESH]
    assert tags == ['vendor-contract_failure_0', 'vendor-contract_failure_1']


def test_graph_checks_korean_english_and_retries(tmp_cfg, section_with_status_evidence, monkeypatch):
    section, model = section_with_status_evidence
    plan = dict(id='field-status', question='상태마다 어느 필드를 사용할 수 있습니까?',
                kind='flow', topic='failure', title='상태별 필드 유효성', generation='llm')
    monkeypatch.setattr(generated_visuals, 'plans', lambda cfg, section: [plan])
    responses = [
        ('sequence와 timestamp만 유효합니다.', 'sequence and timestamp are valid. The other fields may be invalid.'),
        ('sequence와 timestamp는 유효하며 나머지 필드는 유효하지 않을 수 있습니다.', 'Only sequence and timestamp are valid.'),
        ('sequence와 timestamp는 유효하며 나머지 필드는 유효하지 않을 수 있습니다.',
         'sequence and timestamp are valid. The other fields may be invalid.'),
    ]
    tmp_cfg.max_retries = 2
    tags = []

    def chat(system, user, *, tag, response_schema):
        assert field_validity.INSTRUCTIONS in system
        if tags:
            assert 'source says "other fields may be invalid"' in user
        ko, en = responses[len(tags)]
        tags.append(tag)
        node = dict(shape='box', quote_ids=['metadata:0'])
        return json.dumps({'nodes': [
            dict(node, id='error', symbol='FrameError', label=ko, label_en=en),
            dict(node, id='cancelled', symbol='FrameCancelled', label='status만 유효합니다.', label_en='Only status is valid.'),
        ], 'edges': [{'from': 'error', 'to': 'cancelled', 'label': '상태별 유효성을 확인합니다.',
                     'label_en': 'Check validity for each state.', 'condition_ref': 'always', 'quote_ids': ['metadata:0']}]},
            ensure_ascii=False)

    result = generated_visuals.generate(tmp_cfg, model, section, SimpleNamespace(chat=chat))
    assert result['records']['field-status']['graph']['nodes'][0]['label_en'] == responses[2][1]
    assert tags == ['visual_vendor-contract_field-status_0', 'visual_vendor-contract_field-status_1',
                    'visual_vendor-contract_field-status_2']
