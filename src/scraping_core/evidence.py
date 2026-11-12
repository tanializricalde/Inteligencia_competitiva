import html

from bs4 import BeautifulSoup


def sanitize_html_evidence(raw_html: str, max_chars: int = 100_000) -> str:
    soup = BeautifulSoup(raw_html[:max_chars], "lxml")
    for node in soup.select("script, style, meta[http-equiv], input[type=password]"):
        node.decompose()
    for node in soup.find_all(True):
        for attribute in ("value", "src", "href", "action", "srcdoc"):
            node.attrs.pop(attribute, None)
        for attribute in tuple(node.attrs):
            if any(term in attribute.casefold() for term in ("token", "secret", "cookie", "auth")):
                node.attrs.pop(attribute, None)
    return html.escape(str(soup)[:max_chars])
