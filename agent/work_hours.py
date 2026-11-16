"""Compatibilidade de horários explícitos; flexibilidade não confirma turno."""
import re

TIME = r'(?<!\d)(?:[01]?\d|2[0-3])(?:(?::|h)[0-5]\d)?h?(?!\d)'
RANGE = re.compile(r'(?P<start>' + TIME + r')\s*(?:as|ate|a|[-–])\s*(?P<end>' + TIME + r')')


def minutes(value):
    parts = re.fullmatch(r'(\d{1,2})(?:[:h](\d{2}))?h?', value)
    return int(parts[1]) * 60 + int(parts[2] or 0)


def check_hours(text, policy):
    if not policy:
        return True, 'horario_sem_restricao'
    earliest = minutes(policy['earliest_start'])
    ranges = []
    for match in RANGE.finditer(text):
        prefix = text[max(0, match.start()-35):match.start()]
        if not (re.search(r'[h:]', match[0]) or re.search(r'\b(?:das|horario|jornada)\b', prefix)):
            continue
        # Datas de inscrição, faixas salariais e horários de eventos não são jornada.
        if re.search(r'inscric|entrevista|processo seletivo|evento', prefix):
            continue
        ranges.append(minutes(match['start']))
    morning = bool(re.search(r'(?:turno|periodo|jornada).{0,15}(?:manha|matutino)', text))
    if ranges:
        if all(start >= earliest for start in ranges) and not morning:
            return True, 'horario_compativel'
        if any(start >= earliest for start in ranges) and re.search(r'\bou\b|opcoes de horario', text):
            return False, 'horario_alternativas_a_confirmar'
        return False, 'horario_antes_da_disponibilidade'
    if morning:
        return False, 'horario_antes_da_disponibilidade'
    if re.search(r'(?:turno|periodo|jornada).{0,15}(?:tarde|vespertino|noturno)|\bturno da noite\b', text):
        return True, 'horario_compativel'
    return False, 'horario_nao_confirmado'
