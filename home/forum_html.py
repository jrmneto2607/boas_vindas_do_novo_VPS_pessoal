from html.parser import HTMLParser

import nh3


MESSAGE_MAX_LENGTH = 10000


CLEANER = nh3.Cleaner(
    tags={
        "p", "br",
        "strong", "b",
        "em", "i", "u", "s", "blockquote",
        "ul", "ol", "li",
        "a", "span",
    },
    attributes={
        "a": {"href", "title"},
        "*": {"style"},
    },
    clean_content_tags={
        "script", "style", "iframe", "object", "svg", "math",
    },
    filter_style_properties={"color"},
    url_schemes={"http", "https"},
    url_relative="deny",
    link_rel="nofollow noopener noreferrer",
)


class MessageTextParser(HTMLParser):
    """Extrai texto para identificar mensagens vazias."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def has_text(self):
        text = "".join(self.parts)
        text = text.replace("\u200b", "").replace("\ufeff", "")
        return bool(text.strip())


def sanitize_message(value):
    """Remove HTML não permitido e preserva a formatação aceita."""
    return CLEANER.clean(value).strip()


def message_has_text(value):
    parser = MessageTextParser()
    parser.feed(value)
    parser.close()
    return parser.has_text()
