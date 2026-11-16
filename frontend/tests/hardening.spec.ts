import { expect, test } from "@playwright/test";

const job = { id: 1, title: "Backend Python", company: "Empresa sintética", location: "Remoto",
  description: "Desenvolvimento de APIs Python e FastAPI para produtos web.",
  skills: ["Python"], source_url: "https://example.com/synthetic" };
const data = { match_score: 50, summary_of_changes: [], missing_critical_skills: [],
  adapted_resume_markdown: "## Perfil\n\nVersão recente preservada" };
function version(index: number) {
  return { id: `11111111-1111-4111-8111-${String(index).padStart(12, "0")}`, job_id: 1,
    job_title: job.title, company: job.company, job_description: job.description,
    source_fingerprint: "a".repeat(64), created_at: "2026-11-12T12:00:00Z", data };
}
test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/jobs?matching_profile=true&include_unconfirmed_hours=true", route => route.fulfill({ json: [job] }));
});

test("resposta inválida de vagas apresenta erro sem quebrar a página", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/api/v1/jobs?matching_profile=true&include_unconfirmed_hours=true", route => route.fulfill({ json: [{ id: 1, skills: null }] }));
  await page.route("**/api/v1/resumes/versions", route => route.fulfill({ json: [] }));
  await page.goto("/");
  await expect(page.getByRole("alert").filter({ hasText: "Não foi possível carregar as vagas" })).toBeVisible();
  await expect(page.getByLabel("Selecionar currículo PDF")).toBeAttached();
  expect(errors).toEqual([]);
});

test("excluir versão antiga da mesma vaga preserva versão aberta", async ({ page }) => {
  const latest = version(1), older = { ...version(2), data: { ...data, adapted_resume_markdown: "Antiga" } };
  await page.route("**/api/v1/resumes/versions", route => route.fulfill({ json: [latest, older] }));
  await page.route(`**/api/v1/resumes/versions/${older.id}`, route => route.fulfill({ status: 204 }));
  await page.goto("/");
  await page.getByRole("button", { name: `Abrir currículo de ${job.title}` }).first().click();
  await expect(page.getByText("Versão recente preservada")).toBeVisible();
  await page.getByRole("button", { name: `Excluir versão de ${job.title}` }).nth(1).click();
  await expect(page.getByRole("button", { name: `Abrir currículo de ${job.title}` })).toHaveCount(1);
  await expect(page.getByText("Versão recente preservada")).toBeVisible();
});

test("histórico acima de cem versões carrega a página seguinte", async ({ page }) => {
  await page.route("**/api/v1/resumes/versions*", route => route.fulfill({ json:
    route.request().url().includes("before_id=") ? [version(101)] : Array.from({ length: 100 }, (_, i) => version(i + 1)) }));
  await page.goto("/");
  await expect(page.getByRole("button", { name: `Abrir currículo de ${job.title}` })).toHaveCount(100);
  await page.getByRole("button", { name: "Carregar versões anteriores" }).click();
  await expect(page.getByRole("button", { name: `Abrir currículo de ${job.title}` })).toHaveCount(101);
  await expect(page.getByRole("button", { name: "Carregar versões anteriores" })).toHaveCount(0);
});

test("resposta atrasada do histórico não apaga uma versão recém-gerada", async ({ page }) => {
  let release!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  await page.route("**/api/v1/resumes/versions", async route => { await held; await route.fulfill({ json: [] }); });
  await page.route("**/api/v1/resumes/tailor", route => route.fulfill({ json: { status: "success", data, version: version(1) } }));
  await page.goto("/");
  await page.getByLabel("Selecionar currículo PDF").setInputFiles({ name: "sintetico.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 fixture") });
  await page.getByRole("button", { name: /Empresa sintética/ }).click();
  await page.getByRole("button", { name: "Adaptar meu currículo" }).click();
  await expect(page.getByText("Versão recente preservada")).toBeVisible();
  const received = page.waitForResponse(response => response.url().endsWith("/resumes/versions"));
  release();
  await received;
  await expect(page.getByRole("button", { name: `Abrir currículo de ${job.title}` })).toHaveCount(1);
  await expect(page.getByText("Versão recente preservada")).toBeVisible();
});
