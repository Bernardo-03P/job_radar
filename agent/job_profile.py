"""Regras explícitas de seleção; não estima a experiência do candidato."""
import json
import re
import unicodedata
from pathlib import Path

from .work_hours import check_hours

PROFILE_PATH = Path(__file__).with_name("search_profile.json")


def folded(value):
    return "".join(c for c in unicodedata.normalize("NFKD", value.casefold())
                   if not unicodedata.combining(c))


def load_profile():
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def stage(job):
    title = folded(job["title"])
    if re.search(r"estagi|intern(?:ship)?\b", title):
        return "internship"
    if re.search(r"trainee\b", title):
        return "trainee"
    return None


def profile_match(job, profile):
    title = folded(job["title"])
    text = folded(job["description"])
    location = folded(job["location"])
    if not stage(job):
        return False, "fora_de_estagio_trainee"
    area = (r"dados|data|\bia\b|\bai\b|inteligencia artificial|machine learning|"
            r"sistemas|software|desenvolv|developer|programa[cd]|suporte|support|"
            r"service desk|help.?desk|\bti\b|informatica|infraestrutura|tecnologia")
    if not re.search(area, title):
        # Títulos genéricos só passam com evidência técnica nas atividades/requisitos.
        if not re.search(r"python|sql|suporte tecnico|equipamentos de ti|"
                         r"curs\w*.{0,50}(?:computacao|informatica|\bti\b|sistemas)", text):
            return False, "area_nao_confirmada"
    n2 = re.search(r"\bn[ -]?2\b|nivel (?:2|ii)\b|suporte ii\b", title)
    if n2 and re.search(r"(?:experiencia|vivencia).{0,70}(?:obrigatori|necessari|minim|[1-9]\s*anos)|"
                        r"[1-9]\s*anos?.{0,40}experiencia", text):
        return False, "n2_exige_experiencia_revisar"
    compatible_hours, hours_reason = check_hours(title + '\n' + text, profile.get('work_hours'))
    if not compatible_hours:
        return False, hours_reason
    hybrid = re.search(r"hibrid|hybrid|presencial|on.?site", location + " " + title)
    hybrid = hybrid or re.search(r"(?:modelo|regime|modalidade) de trabalho.{0,20}(?:hibrid|presencial)", text)
    remote = re.search(r"remot|telecommute|home office", location + " " + title)
    nationwide = re.search(r"territorio nacional|qualquer lugar do brasil|todo o brasil", text)
    if (profile.get("allow_remote_brazil") and remote and not hybrid
            and (re.search(r"brasil|brazil", location) or nationwide)):
        restrictions = re.findall(r"(?:residir em|residente em|residencia em|comparecer em)[^\n.;]{0,100}", text)
        if any(not re.search(r"brasil|florianopolis", restriction) for restriction in restrictions):
            return False, "local_ou_elegibilidade_nao_confirmado"
        return True, "remoto_brasil"
    # Usa o endereço da fonte e trechos de localização, sem confundir cidades de clientes.
    address_lines = " ".join(line for line in text.splitlines()
                             if re.search(r"local de trabalho|endereco|bairro|localizacao", line))
    address = location + " " + title + " " + address_lines
    for excluded in profile["excluded_locations"]:
        if re.search(r"(?<!\w)" + re.escape(folded(excluded)) + r"(?!\w)", address):
            return False, "local_excluido"
    if folded(profile["onsite_city"]) in location:
        if re.search(r"anuncio nao (?:informa|especifica) (?:o )?bairro|"
                     r"bairro.{0,30}(?:a confirmar|nao (?:informado|especificado))|"
                     r"confirmar (?:o )?endereco(?: exato)?", location + " " + text):
            return False, "florianopolis_bairro_a_confirmar"
        if "grande florianopolis" in location or "regiao" in location:
            return False, "regiao_sem_endereco_confirmado"
        for neighborhood in profile.get("island_locations", []):
            if folded(neighborhood) in location + " " + text:
                return True, "florianopolis_ilha"
        return False, "florianopolis_bairro_a_confirmar"
    return False, "local_ou_elegibilidade_nao_confirmado"


def schedule_group(job, profile):
    matched, reason = profile_match(job, profile)
    if matched:
        return 'confirmed'
    if reason in ('horario_nao_confirmado', 'horario_alternativas_a_confirmar'):
        if profile_match(job, profile | {'work_hours': None})[0]:
            return 'unconfirmed'
    return None


def prioritize(jobs, limit, profile):
    internships = [job for job in jobs if stage(job) == "internship"]
    trainees = [job for job in jobs if stage(job) == "trainee"]
    # A proporção é uma meta de seleção, sem fabricar vagas para completar lotes.
    target = round(limit * profile["internship_share"])
    selected = internships[:target] + trainees[:limit - target]
    if len(selected) < limit:
        selected += internships[target:target + limit - len(selected)]
    return sorted(selected, key=lambda job: (
        stage(job) != "internship",
        bool(re.search(r"\bn[ -]?2\b|nivel (?:2|ii)\b", folded(job["title"]))),
    ))
