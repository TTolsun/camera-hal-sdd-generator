"""Grade isolated reading answers without exposing the rubric to the reader."""
import argparse
import hashlib
import json
from pathlib import Path

from sdd.config import load
from sdd.document_metadata import split_frontmatter
from sdd.llm import Agent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--document', type=Path, required=True)
    parser.add_argument('--answers', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    base = Path(__file__).parent
    questions, rubric = base/'questions.json', base/'rubric.json'
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    answers = json.loads(args.answers.read_bytes())
    if answers['questions_sha256'] != sha(questions) or answers['document_sha256'] != sha(args.document):
        raise ValueError('Reading answers must match the exact fixed questions and document')
    ids = [q['id'] for q in json.loads(questions.read_bytes())['questions']]
    if [a['id'] for a in answers['result']['answers']] != ids:
        raise ValueError('Reading answers must cover the fixed questions in order')
    args.out.mkdir(parents=True, exist_ok=False)
    _, document = split_frontmatter(args.document.read_text(encoding='utf-8'))
    schema = dict(type='object', additionalProperties=False,
                  required=['verdict', 'questions', 'limitations'], properties={
        'verdict': {'enum': ['pass', 'needs-revision']},
        'questions': dict(type='array', items=dict(type='object', additionalProperties=False,
            required=['id', 'passed', 'reason'], properties={
                'id': {'type': 'string'}, 'passed': {'type': 'boolean'}, 'reason': {'type': 'string'}})),
        'limitations': dict(type='array', items={'type': 'string'})})
    agent = Agent(load(base/'independent-review.yaml').agent, args.out/'prompts')
    user = ('Grade the document-only reading answers against the fixed questions and source-based criteria. '
            'Do not assume author intent, hidden code or a device test. Distinguish a normal-path description '
            'from an asserted current-time guarantee. Report actual missing or incorrect decisions; do not '
            'fail merely on wording when condition, actor and modality are preserved.\nQUESTIONS\n'
            + questions.read_text(encoding='utf-8') + '\nCRITERIA (not supplied to the reader)\n'
            + rubric.read_text(encoding='utf-8') + '\nREADER ANSWERS\n'
            + json.dumps(answers['result'], ensure_ascii=False) + '\nDOCUMENT\n' + document)
    result = json.loads(agent.chat(
        'Independent source-based reading grader. This is automatic CLI evaluation, never a human comprehension study. Return JSON.',
        user, tag='reading-grading', response_schema=schema))
    if (len(result['questions']) != len(ids) or {r['id'] for r in result['questions']} != set(ids)
            or (result['verdict'] == 'pass') != all(r['passed'] for r in result['questions'])):
        raise ValueError('Grader result does not cover the fixed criteria consistently')
    report = dict(result=result, answer_sha256=sha(args.answers), rubric_sha256=sha(rubric),
                  document_sha256=sha(args.document), receipt=str(agent.last_receipt), human_review='pending')
    (args.out/'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
