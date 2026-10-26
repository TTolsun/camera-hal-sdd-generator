"""A legacy HTTP receipt may omit CLI markers, but cannot claim both origins."""
import json

import pytest

from sdd.provenance import verify_calls
from test_provenance import setup as provenance_record


def test_http_origin_cannot_also_claim_a_cli_call(tmp_path):
    model, manuscripts, calls, _, _ = provenance_record(tmp_path)
    path = calls / '001.receipt.json'
    receipt = json.loads(path.read_text(encoding='utf-8'))
    receipt['cli_call'] = True
    path.write_text(json.dumps(receipt), encoding='utf-8')
    with pytest.raises(ValueError, match='receipt mismatch'):
        verify_calls(model, manuscripts, calls, provider='ollama', model_name='test')
