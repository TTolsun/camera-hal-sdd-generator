"""Validate scenario output ownership without loading renderers or facts."""


def validate(sections, scenarios, section_output):
    configured = {s['id'] for s in scenarios}
    owners, outputs = {}, set()
    indexes = [s for s in sections if s.get('kind') == 'per-scenario']
    if len(indexes) > 1:
        raise ValueError('Only one per-scenario section can own the scenario index and legacy pages.')
    for section in sections:
        output = section_output(section)
        if output in outputs:
            raise ValueError(f'Multiple sections would overwrite the same document: {output}')
        outputs.add(output)
        if 'index_only' in section and (section.get('kind') != 'per-scenario'
                                      or type(section['index_only']) is not bool):
            raise ValueError('index_only requires a per-scenario section and a boolean.')
        if 'scenario' not in section:
            continue
        sid = section['scenario']
        if not isinstance(sid, str) or sid not in configured:
            raise ValueError('A scenario prose page must select a configured scenario.')
        if (section.get('kind', 'prose') != 'prose' or not section.get('design_topics')
                or not section.get('design_requirements') or not section.get('show_evidence')):
            raise ValueError('Scenario prose requires prose, design_topics, design_requirements and show_evidence.')
        if sid in owners or output != f'scenarios/{sid}.md':
            raise ValueError(f'Duplicate or noncanonical scenario output: {sid}')
        owners[sid] = section
    if indexes:
        if indexes[0].get('index_only', False):
            if set(owners) != configured:
                raise ValueError('index_only requires one source-question prose owner for every scenario.')
        elif owners or outputs.intersection(f'scenarios/{sid}.md' for sid in configured):
            raise ValueError('Legacy per-scenario output conflicts with an explicit document owner; use index_only.')
    return sections
