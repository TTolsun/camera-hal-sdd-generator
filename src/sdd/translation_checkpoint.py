"""Resume fully validated CLI translation units from their original receipts."""
import hashlib
from pathlib import Path

from .cli_checkpoint import Capture, UnitStore, execution_identity
from .llm import AgentError
from .validation_stage import read_bytes


class TranslationCall:
    def __init__(self, cfg, agent, system, user, schema, *, fresh=False, units=()):
        self.agent, self.system, self.user, self.schema, self.fresh = agent, system, user, schema, fresh
        self.options = dict(response_schema=schema) if schema is not None else {}
        self.units = units
        self.mark('running')
        self.store, self.saved, self.capture, self.response_text = None, None, None, None
        if cfg.agent.kind == 'cli' and cfg.agent.model and cfg.review.cli_checkpoint:
            root = Path(__file__).parent
            policy = {name: hashlib.sha256(read_bytes(root/name)).hexdigest() for name in
                      ('translation.py', 'translation_context.py', 'site_localization.py', 'translation_checkpoint.py')}
            identity = dict(purpose='translation', policy=policy,
                request=dict(system=system, user=user, response_schema=schema),
                execution=execution_identity(cfg.agent, schema))
            archive = Path(getattr(agent, 'dump_dir', None) or cfg.build_dir/'translation-prompts').resolve()
            identity['receipt_directory'] = str(archive/'calls')
            self.store = UnitStore(cfg, identity, calls=archive/'calls')
            cached = self.store.read()
            if cached is not None:
                self.saved = cached[0]

    def chat(self, tag):
        if self.saved is not None:
            self.response_text = self.saved['raw']
            return self.response_text
        self.capture = Capture(self.agent)
        if self.fresh:
            self.response_text = self.capture.fresh_chat(self.system, self.user, tag=tag, **self.options)
            receipt = getattr(self.agent, 'last_receipt', None)
            if receipt is not None:
                self.capture.receipts.append(Path(receipt))
        else:
            self.response_text = self.capture.chat(self.system, self.user, tag=tag, **self.options)
        return self.response_text

    def validated(self, values):
        if self.saved is not None:
            if self.saved['statements'] != values:
                raise AgentError('CLI translation checkpoint validated values mismatch; previous catalog preserved')
        elif self.store is not None:
            self.store.write(self.response_text, values, self.capture)
        self.mark('checkpoint-revalidated' if self.saved is not None else 'completed')

    def mark(self, status):
        update = getattr(self.agent, 'unit', None)
        if update is not None:
            for unit in self.units:
                update(unit, status)
