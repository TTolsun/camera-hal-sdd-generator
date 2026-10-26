"""The public verifier must reject changed prose even when local hashes are reset."""

import pytest

from replay_fixture import replay_record


@pytest.fixture
def replay(tmp_path):
    return replay_record(tmp_path, 'verify_overview_replay.py')


def test_public_verifier_accepts_original_record(replay):
    module, root, _, _, save = replay
    save()
    module.verify(root, complete=False)


def test_public_verifier_rejects_rewritten_prose_with_new_body_hash(replay):
    module, root, artifact, _, save = replay
    artifact['answers']['queue-limit'][0]['text'] = '기본 한도는 32이며 모든 요청의 성공을 보장합니다.'
    save()
    with pytest.raises(AssertionError):
        module.verify(root, complete=False)


def test_public_verifier_rejects_fabricated_quote(replay):
    module, root, artifact, _, save = replay
    artifact['answers']['queue-limit'][0]['quote'] = 'unsigned limit = 16;'
    save()
    with pytest.raises(AssertionError):
        module.verify(root, complete=False)


def test_public_verifier_rejects_wrong_expected_source_value(replay):
    module, root, _, proof, save = replay
    proof['stages']['baseline']['queue_limit'] = 16
    save()
    with pytest.raises(AssertionError):
        module.verify(root, complete=False)


def test_public_command_requires_both_pages_and_all_stages(replay):
    module, root, _, _, save = replay
    save()
    with pytest.raises(AssertionError):
        module.verify(root)
