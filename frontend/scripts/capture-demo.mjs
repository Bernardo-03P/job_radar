import { chromium } from '@playwright/test';
import { spawn, spawnSync } from 'node:child_process';
import { Buffer } from 'node:buffer';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { setTimeout as pause } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';

// Demonstração isolada: nenhum backend, currículo real, Telegram ou provedor de IA.
const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const assets = path.resolve(frontend, '../docs/assets');
const address = 'http://127.0.0.1:3100';
try {
  await fetch(address, { signal: AbortSignal.timeout(1000) });
  throw new Error('A porta 3100 está ocupada; encerre a instância de teste antes de capturar.');
} catch (error) {
  if (error.message.includes('ocupada')) throw error;
}
const server = spawn(process.execPath, [path.join(frontend, 'node_modules/next/dist/bin/next'),
  'start', '--hostname', '127.0.0.1', '--port', '3100'], { cwd: frontend, stdio: 'ignore', windowsHide: true });
let browser;
try {
  let ready = false;
  for (let i = 0; i < 80; i++) {
    try {
      if ((await fetch(address, { signal: AbortSignal.timeout(1000) })).ok) { ready = true; break; }
    } catch { /* aguarda somente o servidor criado por este processo */ }
    await pause(250);
  }
  if (!ready) throw new Error('Build indisponível. Execute npm run build antes da captura.');
  browser = await chromium.launch({ headless: true, ...(process.platform === 'win32' ? { channel: 'msedge' } : {}) });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1120 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  await page.route('**/api/v1/**', route => {
    const url = new URL(route.request().url());
    if (url.pathname === '/api/v1/jobs') return route.fulfill({ json: [
      { id: 1, title: 'Estágio em Dados · demonstração', company: 'Empresa Fictícia', location: 'Remoto, Brasil · 13h às 19h',
        description: 'Exemplo fictício de estágio em dados com Python e SQL. Jornada das 13h às 19h.',
        source_url: 'https://example.org/vagas/dados', skills: ['Python', 'SQL', 'PostgreSQL'], schedule_status: 'confirmed' },
      { id: 2, title: 'Estágio em Suporte N1 · demonstração', company: 'Empresa Exemplo', location: 'Florianópolis · Trindade',
        description: 'Exemplo fictício de suporte técnico. Horário a confirmar.', source_url: 'https://example.org/vagas/suporte',
        skills: ['Suporte', 'Sistemas'], schedule_status: 'unconfirmed' },
    ] });
    if (url.pathname === '/api/v1/resumes/tailor') return route.fulfill({ json: { status: 'success', data: {
      match_score: 80, summary_of_changes: ['Conteúdo fictício reorganizado para demonstração.'], missing_critical_skills: [],
      adapted_resume_markdown: '## Ana Exemplo\n\nEstudante de Sistemas · dados fictícios\n\n### Projetos\n\n**Análise de dados com Python e SQL**\n\nOrganização de tabelas, consultas SQL e exploração de dados em projetos acadêmicos.\n\n### Tecnologias\n\nPython · SQL · PostgreSQL · Git\n\n*Prévia de demonstração. Nenhuma inferência real foi executada.*',
    } } });
    return route.fulfill({ json: [] });
  });
  await page.goto(address);
  await page.getByLabel('Selecionar currículo PDF').setInputFiles({ name: 'curriculo-ficticio.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4 demonstracao sintetica') });
  await page.getByRole('button').filter({ has: page.getByRole('heading', { name: 'Estágio em Dados · demonstração', exact: true }) }).click();
  await page.getByRole('button', { name: 'Adaptar meu currículo', exact: true }).click();
  await page.getByRole('heading', { name: 'Ana Exemplo', exact: true }).waitFor();
  await mkdir(assets, { recursive: true });
  await page.screenshot({ path: path.join(assets, 'job-radar-demo.png'), fullPage: true, animations: 'disabled' });
} finally {
  if (browser) await browser.close();
  if (server.exitCode === null && server.pid) {
    if (process.platform === 'win32') spawnSync(path.join(process.env.SystemRoot || 'C:/Windows', 'System32/taskkill.exe'),
      ['/PID', String(server.pid), '/T', '/F'], { stdio: 'ignore', windowsHide: true });
    else server.kill('SIGTERM');
  }
}
