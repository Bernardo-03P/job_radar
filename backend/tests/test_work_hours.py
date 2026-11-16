import pytest
from agent.job_profile import folded, load_profile, profile_match
from agent.work_hours import check_hours


@pytest.mark.parametrize('description,accepted,reason', [
    ('Horário: das 12h às 18h', True, 'horario_compativel'),
    ('Das 13:00 às 19:00', True, 'horario_compativel'),
    ('De segunda a sexta das 14h00 às 18h00', True, 'horario_compativel'),
    ('Turno vespertino', True, 'horario_compativel'),
    ('Das 08h às 14h', False, 'horario_antes_da_disponibilidade'),
    ('Das 11h30 às 17h30', False, 'horario_antes_da_disponibilidade'),
    ('Período matutino', False, 'horario_antes_da_disponibilidade'),
    ('100% remoto, 30h semanais, horário flexível', False, 'horario_nao_confirmado'),
    ('Inscrições de 13 a 19 de novembro', False, 'horario_nao_confirmado'),
    ('Opções: das 9h às 15h ou das 13h às 19h', False, 'horario_alternativas_a_confirmar'),
])
def test_requires_explicit_work_hours(description, accepted, reason):
    assert check_hours(folded(description), load_profile()['work_hours']) == (accepted, reason)


def test_remote_is_not_exempt_from_availability():
    job = {'title': 'Estágio em Dados', 'location': 'Remoto, Brasil', 'description': 'Python e SQL. Das 9h às 15h.'}
    assert profile_match(job, load_profile()) == (False, 'horario_antes_da_disponibilidade')
