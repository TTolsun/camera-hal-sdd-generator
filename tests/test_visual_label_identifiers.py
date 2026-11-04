import html

from sdd.visuals import wrap_label


def test_qualified_callback_identifier_stays_intact_in_both_languages():
    name = 'CameraSession::processRequest'
    for text in [f'진입 {name} 처리 한도 확인', f'Enter {name} and check the limit']:
        rendered = wrap_label(text)
        assert all(component in rendered for component in name.split('::'))
        assert 'processReq<br/>uest' not in rendered
        assert '<br/>' in rendered
        assert html.unescape(rendered.replace('<br/>', '')) == text


def test_long_qualified_identifier_keeps_html_escaped_and_other_text_wrapped():
    text = 'entry Namespace::CameraSession::processRequest <check> ' + 'x' * 80
    rendered = wrap_label(text)
    assert 'Namespace::' in rendered
    assert 'CameraSession::<br/>processRequest' in rendered
    assert '&lt;check&gt;' in rendered
    assert 'x' * 80 not in rendered
    assert html.unescape(rendered.replace('<br/>', '')) == text


def test_virtual_callback_wraps_at_namespace_boundary_before_mermaid_layout():
    name = 'VirtualCameraData::processRequest'
    for suffix in ['가 목표 시각까지 대기', ' waits until target time']:
        rendered = wrap_label(name + suffix)
        assert 'VirtualCameraData::<br/>processRequest' in rendered
        assert html.unescape(rendered.replace('<br/>', '')) == name + suffix


def test_guard_expression_wraps_between_fitting_identifier_tokens():
    expression = 'activeStreams_.find(stream) == activeStreams_.end()'
    for prefix in ['검사 조건: ', 'Check condition: ']:
        for width in range(14, 36):
            text = prefix + expression
            rendered = wrap_label(text, width)
            visible = html.unescape(rendered)
            for token in ['activeStreams_', 'find', 'stream', 'end']:
                assert visible.count(token) == text.count(token)
            assert html.unescape(rendered.replace('<br/>', '')) == text


def test_fitting_identifier_survives_adjacent_html_sensitive_operators():
    text = '조건 requestCount < bufferCount && stream != nullptr'
    rendered = wrap_label(text, 14)
    assert '&lt;' in rendered and '&amp;&amp;' in rendered
    for token in ['requestCount', 'bufferCount', 'stream', 'nullptr']:
        assert token in rendered
    assert html.unescape(rendered.replace('<br/>', '')) == text
