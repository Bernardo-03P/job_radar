import { expect, test } from "@playwright/test";

test("busca e seleção com backend real, sem mock de vagas", async ({ page, request }) => {
  test.skip(!process.env.E2E_REAL_API, "Integração opcional com o backend local iniciado.");
  const response = await request.get("http://127.0.0.1:8000/api/v1/jobs?matching_profile=true");
  expect(response.ok()).toBeTruthy();
  const jobs = await response.json();
  expect(jobs.length).toBeGreaterThan(0);
  const job = jobs[0];
  await page.goto("/");
  await expect(page.getByRole("heading", { name: job.title, exact: true })).toBeVisible();
  await page.getByRole("textbox", { name: "Buscar vagas" }).fill("sem-correspondencia-978xyz");
  await expect(page.getByText("Nenhuma vaga encontrada.")).toBeVisible();
  await page.getByRole("textbox", { name: "Buscar vagas" }).fill(job.title);
  const card = page.getByRole("button").filter({
    has: page.getByRole("heading", { name: job.title, exact: true }),
  });
  await card.click();
  await expect(page.getByLabel("Descrição da vaga")).toHaveValue(job.description);
});
