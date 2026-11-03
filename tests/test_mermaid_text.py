from sdd.mermaid_text import label, wrapped_html_label
from sdd.visuals import wrap_label
from sdd.diagrams import class_diagram, scenario_call_map
from sdd.facts.model import ClassInfo, KnowledgeModel, Message, Location


def test_literal_punctuation_uses_mermaid_codes_not_html_entities():
    text = 'Request\'s "ready" & <Frame> #quot; \\path | next'
    result = wrapped_html_label(wrap_label(text, width=999))
    assert result == 'Request#39;s #34;ready#34; #38; #60;Frame#62; #35;quot; #92;path #124; next'
    assert '&amp;' not in result and '&#x27;' not in result


def test_only_generated_breaks_are_markup():
    result = wrapped_html_label(wrap_label('one two <br/>', width=5))
    assert '<br/>' in result
    assert '#60;br/#62;' in result.replace('<br/>', '')
    assert label('" ] --> EXTRA["') == '#34; #93; --#62; EXTRA#91;#34;'
    assert label('`**literal**`') == '#96;#42;#42;literal#42;#42;#96;'
    assert label('[x](y) _z_ ~~w~~!') == '#91;x#93;#40;y#41; #95;z#95; #126;#126;w#126;#126;#33;'


def test_static_type_and_call_labels_keep_template_and_operator_text():
    model = KnowledgeModel()
    model.classes['Type<int>'] = ClassInfo(name='Type<int>')
    assert 'Type#60;int#62;' in class_diagram(model, ['*'])
    source = scenario_call_map([Message('Type<int>', 'Other', 'operator<', Location('a.cpp', 1))])
    assert 'Type#60;int#62;' in source and 'operator#60;#40;#41;' in source
