from or_extractor.text_cleaner import clean_ocr_text


def test_clean_ocr_text_removes_html_css_and_decodes_entities():
    raw = """
    <!doctype html>
    <html>
      <head><style>.x { color: red; }</style></head>
      <body>
        <div>LISTE DES PI&Egrave;CES&nbsp;</div>
        <br>
        <div>! 1!PARE-CHOCS AV!735707751!E! 1163,23!</div>
      </body>
    </html>
    """

    cleaned = clean_ocr_text(raw)

    assert "style" not in cleaned.lower()
    assert "<div>" not in cleaned
    assert "LISTE DES PIÈCES" in cleaned
    assert "! 1!PARE-CHOCS AV!735707751!E! 1163,23!" in cleaned
