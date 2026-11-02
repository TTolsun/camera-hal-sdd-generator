import html

from sdd.visuals import wrap_label


def test_qualified_callback_identifier_stays_intact_in_both_languages():
    name = 'CameraSession::processRequest'
    for text in [f'진입 {name} 처리 한도 확인', f'Enter {name} and check the limit']:
        rendered = wrap_label(text)
        assert name in rendered
        assert '<br/>' in rendered
        assert html.unescape(rendered.replace('<br/>', '')) == text


def test_long_qualified_identifier_keeps_html_escaped_and_other_text_wrapped():
    text = 'entry Namespace::CameraSession::processRequest <check> ' + 'x' * 80
    rendered = wrap_label(text)
    assert 'Namespace::CameraSession::processRequest' in rendered
    assert '&lt;check&gt;' in rendered
    assert 'x' * 80 not in rendered
    assert html.unescape(rendered.replace('<br/>', '')) == text
