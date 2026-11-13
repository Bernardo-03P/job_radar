import { expect, test } from "@playwright/test";
import { createHash } from "node:crypto";

const job = {
  id: 1, title: "Backend Python", company: "Empresa de teste", location: "Remoto",
  description: "Desenvolvimento de APIs com Python, FastAPI e PostgreSQL.",
  skills: ["Python", "FastAPI"], source_url: "https://example.com/job",
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/jobs?matching_profile=true", route => route.fulfill({ json: [job] }));
  await page.route("**/api/v1/resumes/versions", route => route.fulfill({ json: [] }));
});

test("JavaScript carrega e a pesquisa filtra as vagas", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/");
  const card = page.getByRole("button", { name: /Empresa de teste/ });
  await expect(card).toBeVisible();
  await page.getByRole("textbox", { name: "Buscar vagas" }).fill("inexistente");
  await expect(card).toHaveCount(0);
  await expect(page.getByText("Nenhuma vaga encontrada.")).toBeVisible();
  await page.getByRole("textbox", { name: "Buscar vagas" }).fill("Python");
  await expect(card).toBeVisible();
  await card.click();
  await expect(page.getByLabel("Descrição da vaga")).toHaveValue(job.description);
  expect(errors).toEqual([]);
});

test("clique abre seletor, aceita PDF e permite adaptar com IA mockada", async ({ page }) => {
  await page.route("**/api/v1/resumes/tailor", route => route.fulfill({ json: {
    status: "success", data: { match_score: 100, summary_of_changes: ["Texto preservado"],
      missing_critical_skills: [], adapted_resume_markdown: "## Perfil\n\nAna Silva — Python" },
  } }));
  await page.goto("/");
  await expect(page.getByRole("button", { name: /Empresa de teste/ })).toBeVisible();
  const chooser = page.waitForEvent("filechooser");
  await page.getByRole("button", { name: "Arraste seu currículo ou clique para selecionar" }).click();
  await (await chooser).setFiles({ name: "curriculo-teste.pdf", mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4\nfixture sintética em memória") });
  await expect(page.getByRole("button", { name: "curriculo-teste.pdf" })).toBeVisible();
  await page.getByRole("button", { name: /Empresa de teste/ }).click();
  await page.getByRole("button", { name: "Adaptar meu currículo" }).click();
  await expect(page.getByText("Ana Silva — Python")).toBeVisible();
  await expect(page.getByRole("button", { name: "Copiar Markdown" })).toBeEnabled();
  await page.getByRole("button", { name: "Remover currículo" }).click();
  await expect(page.getByRole("button", { name: "Adaptar meu currículo" })).toBeDisabled();
});

test("valida arquivo incompatível e explica falha na adaptação", async ({ page }) => {
  await page.route("**/api/v1/resumes/tailor", route => route.fulfill({ status: 503,
    json: { detail: "Configure GROQ_API_KEY ou OPENAI_API_KEY no backend." } }));
  await page.goto("/");
  await page.getByLabel("Selecionar currículo PDF").setInputFiles({ name: "cv.txt",
    mimeType: "text/plain", buffer: Buffer.from("fixture") });
  await expect(page.getByText("Selecione um arquivo PDF.", { exact: true })).toBeVisible();
  await page.getByLabel("Selecionar currículo PDF").setInputFiles({ name: "cv.pdf",
    mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 fixture") });
  await page.getByRole("button", { name: /Empresa de teste/ }).click();
  await page.getByRole("button", { name: "Adaptar meu currículo" }).click();
  await expect(page.getByText("Configure GROQ_API_KEY ou OPENAI_API_KEY no backend.")).toBeVisible();
});

test("mantém uma versão por vaga e permite baixar sem nova chamada de IA", async ({ page }) => {
  const otherJob = { ...job, id: 2, title: "Engenharia de Dados", company: "Outra empresa",
    description: "Engenharia de dados com Python, SQL e construção de pipelines." };
  await page.route("**/api/v1/jobs?matching_profile=true", route => route.fulfill({ json: [job, otherJob] }));
  let calls = 0;
  await page.route("**/api/v1/resumes/tailor", route => {
    calls += 1;
    return route.fulfill({ json: { status: "success", data: {
      match_score: 90, summary_of_changes: ["Texto preservado"], missing_critical_skills: [],
      adapted_resume_markdown: `## Perfil\n\nCurrículo exclusivo da vaga ${calls}`,
    } } });
  });
  await page.goto("/");
  await page.getByLabel("Selecionar currículo PDF").setInputFiles({ name: "cv.pdf",
    mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 fixture") });
  await page.getByRole("button", { name: /Empresa de teste/ }).click();
  await page.getByRole("button", { name: "Adaptar meu currículo" }).click();
  await expect(page.getByText("Currículo exclusivo da vaga 1")).toBeVisible();
  await page.getByRole("button", { name: /Outra empresa/ }).click();
  await expect(page.getByText("Currículo exclusivo da vaga 1")).toHaveCount(0);
  await page.getByRole("button", { name: "Adaptar meu currículo" }).click();
  await expect(page.getByText("Currículo exclusivo da vaga 2")).toBeVisible();
  await page.getByRole("button", { name: /Empresa de teste/ }).click();
  await expect(page.getByText("Currículo exclusivo da vaga 1")).toBeVisible();
  await expect(page.getByRole("button", { name: "Versão já gerada" })).toBeDisabled();
  await expect(page.getByText("Currículo pronto", { exact: true })).toHaveCount(2);
  expect(calls).toBe(2);
  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "Baixar Markdown" }).click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toBe("curriculo-backend-python.md");
  const stream = await download.createReadStream();
  const chunks = [];
  for await (const chunk of stream!) chunks.push(chunk);
  expect(Buffer.concat(chunks).toString("utf8")).toContain("Currículo exclusivo da vaga 1");
  expect(calls).toBe(2);
});

test("alterar a descrição ou trocar o PDF não reaproveita uma versão incompatível", async ({ page }) => {
  let calls = 0;
  await page.route("**/api/v1/resumes/tailor", route => {
    calls += 1;
    return route.fulfill({ json: { status: "success", data: { match_score: 80,
      summary_of_changes: [], missing_critical_skills: [],
      adapted_resume_markdown: "## Perfil\n\nVersão da experiência original" } } });
  });
  await page.goto("/");
  await page.getByLabel("Selecionar currículo PDF").setInputFiles({ name: "original.pdf",
    mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 fixture original") });
  await page.getByRole("button", { name: /Empresa de teste/ }).click();
  await page.getByRole("button", { name: "Adaptar meu currículo" }).click();
  await expect(page.getByText("Versão da experiência original")).toBeVisible();
  await page.getByLabel("Descrição da vaga").fill(job.description + " Experiência com Docker.");
  await expect(page.getByText("Versão da experiência original")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Adaptar meu currículo" })).toBeEnabled();
  await page.getByLabel("Descrição da vaga").fill(job.description);
  await expect(page.getByText("Versão da experiência original")).toBeVisible();
  expect(calls).toBe(1);
  await page.getByLabel("Selecionar currículo PDF").setInputFiles({ name: "atualizado.pdf",
    mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 fixture atualizado") });
  await expect(page.getByText("Versão da experiência original")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Adaptar meu currículo" })).toBeEnabled();
  await expect(page.getByText("Currículo pronto", { exact: true })).toHaveCount(0);
  expect(calls).toBe(1);
});

test("histórico restaura após recarregar e permite excluir sem gerar novamente", async ({ page }) => {
  const pdf = Buffer.from("%PDF-1.4 fixture de persistência");
  const data = { match_score: 90, summary_of_changes: ["Texto preservado"],
    missing_critical_skills: [], adapted_resume_markdown: "## Perfil\n\nCurrículo restaurado do banco" };
  const version = { id: "11111111-1111-4111-8111-111111111111", job_id: job.id,
    job_title: job.title, company: job.company, job_description: job.description,
    source_fingerprint: createHash("sha256").update(pdf).digest("hex"),
    created_at: "2026-11-12T12:00:00Z", data };
  let records: typeof version[] = [];
  let calls = 0;
  const tokens: string[] = [];
  await page.route("**/api/v1/resumes/versions", route => {
    tokens.push(route.request().headers()["x-resume-token"]);
    return route.fulfill({ json: records });
  });
  await page.route("**/api/v1/resumes/tailor", route => {
    calls += 1;
    records = [version];
    return route.fulfill({ json: { status: "success", data, version, cached: false } });
  });
  await page.route(`**/api/v1/resumes/versions/${version.id}`, route => {
    expect(route.request().method()).toBe("DELETE");
    records = [];
    return route.fulfill({ status: 204 });
  });
  await page.goto("/");
  await expect(page.getByRole("button", { name: /Empresa de teste/ })).toBeVisible();
  await page.getByLabel("Selecionar currículo PDF").setInputFiles({ name: "cv.pdf",
    mimeType: "application/pdf", buffer: pdf });
  await page.getByRole("button", { name: /Empresa de teste/ }).click();
  await page.getByRole("button", { name: "Adaptar meu currículo" }).click();
  await expect(page.getByRole("button", { name: `Abrir currículo de ${job.title}` })).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: `Abrir currículo de ${job.title}` }).click();
  await expect(page.getByText("Currículo restaurado do banco")).toBeVisible();
  expect(calls).toBe(1);
  expect(new Set(tokens).size).toBe(1);
  expect(tokens[0].length).toBeGreaterThanOrEqual(32);
  await page.getByRole("button", { name: `Excluir versão de ${job.title}` }).click();
  await expect(page.getByRole("button", { name: `Abrir currículo de ${job.title}` })).toHaveCount(0);
  await expect(page.getByText("Currículo restaurado do banco")).toHaveCount(0);
  expect(calls).toBe(1);
});
