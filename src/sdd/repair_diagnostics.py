"""Causal observations inside the existing execution journal, not a retry budget.

An observation is not a semantic resolution or a human approval. Exact review
request identity is useful for detecting no modification, not for matching
different claims by wording or declaring an old finding resolved.
"""
from __future__ import annotations

import hashlib
import json


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class UnchangedRejectedReview(ValueError):
    """No evidence, criterion or candidate changed after a semantic rejection."""


class RepairRequired(ValueError):
    def __init__(self, message, category, **details):
        self.category, self.details = category, details
        super().__init__(message + (': ' + json.dumps(details, ensure_ascii=False, default=repr) if details else ''))


class ReviewAttempt:
    def __init__(self, agent, rejected, profile):
        self.agent, self.rejected, self.profile = agent, rejected, profile
        self.request = self.receipt = None
        self.returned = self.failed = False

    def chat(self, system, user, **options):
        # Grounding's payload contains the complete source scope and candidate.
        # Parse only for canonical identity; preserve the original bytes sent.
        self.request = fingerprint(dict(system=system, payload=json.loads(user), profile=self.profile,
                                        schema=options.get('response_schema')))
        if self.request in self.rejected:
            raise UnchangedRejectedReview(
                '근거 검토에서 거절된 원고·근거·판정 기준이 그대로입니다. '
                '같은 검토를 반복해 해결로 표시하지 않습니다. '
                '원고의 지적된 조건을 수정하거나 필요한 근거 범위를 보완한 뒤 재개하세요. '
                '이전 지적: ' + self.rejected[self.request])
        try:
            result = self.agent.chat(system, user, **options)
        except BaseException:
            self.failed = True
            raise
        self.returned = True
        self.receipt = getattr(self.agent, 'last_receipt', None)
        return result


def rejected_reviews(target, context):
    """Carry only exact, explicitly rejected reviews within this operation.

    This is a diagnostic stop, not reuse eligibility or a review approval.
    Historical journals are never promoted into current successful receipts.
    """
    from .generation_run import observed
    execution = observed()
    if execution is None:
        return {}
    reports = [*execution.prior(), execution.report]
    return {row['details']['review_request_sha256']: row['error']
            for report in reports for row in report.get('repair_attempts', [])
            if row['target'] == target and row.get('source_commit') == context.get('source_commit')
            and row['category'] == 'semantic' and row.get('details', {}).get('review_request_sha256')}


def observe_attempt(target, stage, attempt, *, context, raw=None, category=None,
                    error=None, action=None, receipt=None, status='rejected', details=None):
    """Append; never rewrite a previous failure when another checker passes."""
    from .generation_run import observed
    execution = observed()
    if execution is None:
        return
    rows = execution.report.setdefault('repair_attempts', [])
    row = dict(target=target, stage=stage, attempt=attempt, context_sha256=fingerprint(context),
               response_sha256=hashlib.sha256(raw.encode()).hexdigest() if raw is not None else None,
               category=category, error=str(error) if error is not None else None,
               next_action=action, status=status, human_review='pending')
    row['source_commit'] = context.get('source_commit')
    row['source_windows'] = {key: hashlib.sha256(text.encode()).hexdigest()
                             for key, text in context.get('sources', {}).items()}
    row['criterion_sha256'] = fingerprint(context.get('topic', context.get('input_fingerprint')))
    if receipt is not None:
        from pathlib import Path
        path = Path(receipt)
        try:
            row['receipt'] = dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        except OSError as exc:
            # Diagnostic enrichment must not replace the original validation
            # outcome. The checkpoint/provenance owner still enforces integrity.
            row['receipt'] = dict(path=str(path), status='unreadable', error=str(exc))
    if details is not None:
        row['details'] = details
        if details.get('code'):
            # The message and English wording are observations, never identity.
            # Keep distinct source conditions/locations separate even if the
            # checker uses the same error text for both.
            row['finding_id'] = fingerprint(dict(rule=details['code'], target=target,
                context=row['context_sha256'], locations=[{key: item.get(key) for key in
                    ('target', 'label', 'evidence')} for item in (details['first'], details['second'])]))
    previous = next((i for i in range(len(rows)-1, -1, -1)
                     if rows[i]['target'] == target and rows[i]['stage'] == stage), None)
    row['previous_observation'] = previous
    row['same_response_and_context'] = bool(previous is not None and
        rows[previous]['context_sha256'] == row['context_sha256'] and
        rows[previous]['response_sha256'] == row['response_sha256'])
    # A changed/absent error does not establish that the original condition was
    # inspected. Keep the earlier finding unresolved until an explicit review.
    row['prior_finding_disposition'] = 'unjudged' if previous is not None else None
    rows.append(row)
    try:
        execution.persist()
    except OSError as exc:
        # This extra diagnostic write must not prevent saving the original
        # result/checkpoint or replacing the original validation failure.
        # Execution's existing progress and provenance gates remain enforced.
        import warnings
        row['diagnostic_write_error'] = str(exc)
        warnings.warn('Repair diagnostic journal write failed: ' + str(exc), RuntimeWarning, stacklevel=2)


def compare_checks(before, after):
    """Compare explicitly inspected condition IDs; absent checks stay unjudged.

    Each mapping is supplied by a validated independent review or deterministic
    checker, with identity=(target, criterion, evidence hashes, condition).
    This function reports transitions, never approves an artifact. A semantic
    disagreement on unchanged input requires a separate evidence disposition.
    """
    result = {}
    for key in before.keys() | after.keys():
        old, new = before.get(key), after.get(key)
        state = 'unjudged'
        if old and new and old['identity'] == new['identity']:
            if new['status'] == 'error':
                state = 'maintained' if old['status'] == 'error' else 'new-error' if old['status'] == 'supported' else 'newly-observed'
            elif new['status'] == 'supported' and old['status'] == 'error':
                if old['candidate_sha256'] != new['candidate_sha256']:
                    state = 'resolved' if new.get('verification') in ('deterministic', 'independent-source-review') else 'unjudged'
                elif new.get('disposition') == 'no-change-needed' and new.get('additional_evidence') and new.get('verification') == 'independent-source-review':
                    state = 'no-change-needed'
                else:
                    state = 'verdict-conflict'
            elif new['status'] == old['status'] == 'supported':
                state = 'preserved'
        elif new and new['status'] == 'error':
            state = 'newly-observed'
        result[key] = state
    replacement = 'resolved' in result.values() and any(s in result.values() for s in ('new-error', 'newly-observed'))
    unmatched = [key for key, old in before.items() if old['status'] == 'error' and
                 (key not in after or old['identity'] != after[key]['identity'])]
    return dict(findings=result, unmatched_prior_findings=unmatched, error_replacement=replacement,
                successful_repair=bool('resolved' in result.values() and not replacement and
                    not unmatched and not any(s in result.values() for s in ('unjudged', 'verdict-conflict', 'maintained'))))
