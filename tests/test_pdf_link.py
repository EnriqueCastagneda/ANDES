import app


def test_detects_pdf():
    assert app.find_pdf_url("Ver https://a.pe/doc/x.pdf fin") == "https://a.pe/doc/x.pdf"


def test_uppercase():
    assert app.find_pdf_url("https://a.pe/X.PDF") == "https://a.pe/X.PDF"


def test_query_string():
    assert app.find_pdf_url("https://a.pe/x.pdf?v=2 mas") == "https://a.pe/x.pdf?v=2"


def test_first_link():
    assert app.find_pdf_url("https://a.pe/1.pdf y https://a.pe/2.pdf") == "https://a.pe/1.pdf"


def test_absent():
    assert app.find_pdf_url("sin enlaces https://a.pe/pagina.html") is None
    assert app.find_pdf_url("") is None
    assert app.find_pdf_url(None) is None
