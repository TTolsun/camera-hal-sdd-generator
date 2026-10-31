"""Explicit scoped vocabulary constraints; never infer semantic approval."""
def required_phrases(strings, rules):
    failures={}
    if not isinstance(rules,list):raise ValueError('Translation phrase rules must be a list')
    for rule in rules:
        if (not isinstance(rule,dict) or set(rule)-{'source_all','source_any','english_any','english_none','expected_matches'}
                or not rule.get('source_all') or not (rule.get('english_any') or rule.get('english_none'))):
            raise ValueError('Invalid scoped translation phrase rule')
        for field in ['source_all','source_any','english_any','english_none']:
            values=rule.get(field,[])
            if not isinstance(values,list) or any(not isinstance(v,str) or not v.strip() for v in values):
                raise ValueError('Translation phrase terms must be nonempty strings')
        count=rule.get('expected_matches',1)
        if type(count) is not int or count<1:raise ValueError('Expected translation matches must be positive')
        selected=[source for source in strings if all(v in source for v in rule['source_all'])
                  and (not rule.get('source_any') or any(v in source for v in rule['source_any']))]
        if len(selected)!=count:raise ValueError('Scoped translation phrase rule matched an unexpected number of source strings')
        for source in selected:
            value=str(strings[source]).casefold();errors=[]
            if rule.get('english_any') and not any(v.casefold() in value for v in rule['english_any']):
                errors.append('Must preserve one of: '+', '.join(rule['english_any']))
            if any(v.casefold() in value for v in rule.get('english_none',[])):
                errors.append('Contains a prohibited ambiguous phrase')
            if errors:failures.setdefault(source,[]).extend(errors)
    return failures
