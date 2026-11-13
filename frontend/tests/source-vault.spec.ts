import { expect, test } from "@playwright/test";

test("guardar o PDF exige ação explícita, consulta após recarregar e permite excluir sem IA", async ({ page }) => {
  const source = { id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", filename: "synthetic.pdf",
    fingerprint: "a".repeat(64), created_at: "2026-11-13T15:00:00+00:00" };
  let saved = false;
  let saves = 0;
  let generations = 0;
  await page.route("**/api/v1/jobs?matching_profile=true", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/resumes/versions", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/resumes/tailor", route => {
    generations += 1;
    return route.fulfill({ status: 500, json: { detail: "Geração não autorizada neste teste" } });
  });
  await page.route("**/api/v1/resumes/sources", route => {
    expect(route.request().headers()["x-resume-token"]).toBeTruthy();
    if (route.request().method() === "POST") {
      saves += 1;
      saved = true;
      return route.fulfill({ status: 201, json: source });
    }
    return route.fulfill({ json: saved ? [source] : [] });
  });
  await page.route(`**/api/v1/resumes/sources/${source.id}`, route => {
    expect(route.request().method()).toBe("DELETE");
    saved = false;
    return route.fulfill({ status: 204 });
  });
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Guardar PDF para o Telegram" })).toBeDisabled();
  await page.getByLabel("Selecionar currículo PDF").setInputFiles({ name: source.filename,
    mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 synthetic in-memory fixture") });
  await expect(page.getByRole("button", { name: "Guardar PDF para o Telegram" })).toBeEnabled();
  expect(saves).toBe(0);
  await page.getByRole("button", { name: "Guardar PDF para o Telegram" }).click();
  await expect(page.getByText(/PDF guardado neste PC/)).toBeVisible();
  expect(saves).toBe(1);
  expect(generations).toBe(0);
  await page.reload();
  await page.getByRole("button", { name: "Consultar PDF guardado" }).click();
  await expect(page.getByText("synthetic.pdf", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Excluir PDF guardado" }).click();
  await expect(page.getByText(/PDF original excluído/)).toBeVisible();
  expect(saved).toBe(false);
  expect(generations).toBe(0);
});
