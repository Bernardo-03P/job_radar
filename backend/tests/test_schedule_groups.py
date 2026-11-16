import httpx
from agent.job_profile import load_profile, schedule_group

from app.models.job import Job
from main import app


async def test_confirmed_and_unknown_groups_never_include_morning_or_bad_location(database):
    with database() as db:
        for name, location, hours in [('confirmed', 'Remoto, Brasil', 'Das 13h às 19h.'),
                                      ('unknown', 'Remoto, Brasil', 'Horário flexível.'),
                                      ('morning', 'Remoto, Brasil', 'Das 9h às 15h.'),
                                      ('excluded', 'Presencial, São José, SC', '')]:
            db.add(Job(title='Estágio em Dados', company=name, location=location,
                       description='Projetos Python e SQL. '+hours, source_url=f'https://example.com/{name}', skills=[]))
        db.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        confirmed = (await client.get('/api/v1/jobs?matching_profile=true')).json()
        assert [row['company'] for row in confirmed] == ['confirmed']
        groups = (await client.get('/api/v1/jobs?matching_profile=true&include_unconfirmed_hours=true')).json()
        assert [(row['company'], row['schedule_status']) for row in groups] == [
            ('confirmed', 'confirmed'), ('unknown', 'unconfirmed')]


def test_unknown_schedule_does_not_bypass_other_profile_rules():
    job = {'title':'Estágio em Dados', 'location':'Presencial, Florianópolis, bairro a confirmar',
           'description':'Projetos Python e SQL.'}
    assert schedule_group(job, load_profile()) is None
