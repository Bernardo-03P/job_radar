"""Revalidação de anúncios públicos do IEL/SC; nunca acessa a área autenticada."""
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit


class IELPage(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.heading = None
        self.headings = []
        self.sections = {}
        self.current = None
        self.application = False
        self.visible = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        if self.hidden:
            return
        if tag in ("h1", "h2", "h3"):
            self.heading = []
        if tag == "a":
            parsed = urlsplit(dict(attrs).get("href", ""))
            if (parsed.scheme == "https" and parsed.hostname == "admin-carreiras.sc.iel.org.br"
                    and parsed.path == "/logincandidato.aspx" and parsed.query):
                self.application = True
                self.current = None

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1)
        if tag in ("h1", "h2", "h3") and self.heading is not None:
            label = " ".join(self.heading).strip()
            self.headings.append(label)
            self.current = label
            self.sections[label] = []
            self.heading = None

    def handle_data(self, data):
        if self.hidden or not data.strip():
            return
        text = data.strip()
        self.visible.append(text)
        if self.heading is not None:
            self.heading.append(text)
        elif self.current:
            self.sections[self.current].append(text)


def fetch_iel(client, url):
    if not re.fullmatch(r"https://carreiras\.iel\.org\.br/SC/vaga/estagio/[0-9]+/[a-z0-9-]+", url):
        raise ValueError("Configure somente anúncios públicos originais do IEL/SC.")
    response = client.get(url)
    response.raise_for_status()
    parser = IELPage()
    parser.feed(response.content.decode("utf-8"))
    visible = " ".join(parser.visible)
    if re.search(r"vaga (?:encerrada|indisponível|não encontrada)|inscrições encerradas", visible, re.I):
        return []
    required = ("Empresa:", "Atividades:", "Requisitos:", "Cidade:", "Formato de trabalho:")
    if (not all(parser.sections.get(key) for key in required) or not parser.application
            or "se candidate" not in visible.lower()):
        raise ValueError("IEL sem detalhes ou candidatura pública verificável; revise a fonte.")
    title = next((heading for heading in parser.headings if re.match(r"Estágio\b", heading, re.I)), None)
    if not title:
        raise ValueError("IEL sem título de estágio verificável.")
    # Endereço vem somente dos campos da vaga, nunca do rodapé do IEL.
    location = ", ".join(" ".join(parser.sections.get(key, [])) for key in
                         ("Local:", "Cidade:", "Formato de trabalho:"))
    labels = ("Atividades:", "Requisitos:", "Cursos:", "Escolaridade:", "até",
              "Cidade:", "Local:", "Remuneração:", "Benefícios:", "Horários:", "Formato de trabalho:")
    description = "\n".join(key + "\n" + "\n".join(parser.sections[key])
                            for key in labels if parser.sections.get(key))
    return [({"title": title, "content": description, "absolute_url": url,
              "location": {"name": location}}, " ".join(parser.sections["Empresa:"]))]
