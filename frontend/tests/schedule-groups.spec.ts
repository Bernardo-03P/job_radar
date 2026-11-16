import { expect, test } from '@playwright/test';

test('separa horários confirmados e pendentes sem impedir selecionar a vaga', async ({ page }) => {
  await page.route('**/api/v1/resumes/versions*', route => route.fulfill({ json: [] }));
  await page.route('**/api/v1/jobs*', route => route.fulfill({ json: [
    { id: 901, title: 'Estágio de dados à tarde', company: 'Teste', location: 'Remoto, Brasil',
      description: 'Python e SQL, das 13h às 19h.', skills: ['Python'], source_url: 'https://example.com/1', schedule_status: 'confirmed' },
    { id: 902, title: 'Estágio de suporte sem turno', company: 'Teste', location: 'Remoto, Brasil',
      description: 'Suporte técnico, horário não informado.', skills: [], source_url: 'https://example.com/2', schedule_status: 'unconfirmed' },
  ] }));
  await page.goto('/');
  await expect(page.getByRole('region', { name: 'Horário confirmado', exact: true })
    .getByRole('heading', { name: 'Estágio de dados à tarde' })).toBeVisible();
  const pending = page.getByRole('region', { name: 'Horário a confirmar', exact: true });
  await expect(pending.getByRole('heading', { name: 'Estágio de suporte sem turno' })).toBeVisible();
  await pending.getByRole('button').click();
  await expect(page.getByLabel('Descrição da vaga')).toHaveValue('Suporte técnico, horário não informado.');
});
