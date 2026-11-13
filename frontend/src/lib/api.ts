export type Job = { id: number; title: string; company: string; location: string; description: string; skills: string[]; source_url: string };
export type Result = { match_score: number; summary_of_changes: string[]; missing_critical_skills: string[]; adapted_resume_markdown: string };
export type SavedVersion = { id: string; job_id: number | null; job_title: string; company: string;
  job_description: string; source_fingerprint: string; created_at: string; data: Result };
export type SavedSource = { id: string; filename: string; fingerprint: string; created_at: string };

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(item => typeof item === "string");
}
function result(value: unknown): value is Result {
  return object(value) && Number.isInteger(value.match_score) && Number(value.match_score) >= 0
    && Number(value.match_score) <= 100 && strings(value.summary_of_changes)
    && strings(value.missing_critical_skills) && typeof value.adapted_resume_markdown === "string"
    && value.adapted_resume_markdown.trim().length > 0;
}
function version(value: unknown): value is SavedVersion {
  return object(value) && typeof value.id === "string" && /^[0-9a-f-]{36}$/i.test(value.id)
    && (value.job_id === null || (Number.isInteger(value.job_id) && Number(value.job_id) > 0))
    && [value.job_title, value.company, value.job_description, value.source_fingerprint, value.created_at]
      .every(item => typeof item === "string") && Number.isFinite(Date.parse(String(value.created_at)))
    && /^[a-f0-9]{64}$/.test(String(value.source_fingerprint)) && result(value.data);
}
export function jobsResponse(value: unknown): Job[] {
  if (!Array.isArray(value) || !value.every(item => object(item) && Number.isInteger(item.id)
    && Number(item.id) > 0 && [item.title, item.company, item.location, item.description, item.source_url]
      .every(field => typeof field === "string") && strings(item.skills))) {
    throw new Error("O servidor retornou uma lista de vagas inválida. Tente atualizar.");
  }
  return value as Job[];
}
export function versionsResponse(value: unknown): SavedVersion[] {
  if (!Array.isArray(value) || !value.every(version)) {
    throw new Error("O servidor retornou um histórico inválido. Tente atualizar.");
  }
  return value;
}
export function sourcesResponse(value: unknown): SavedSource[] {
  if (!Array.isArray(value) || !value.every(item => object(item)
    && typeof item.id === "string" && /^[0-9a-f-]{36}$/i.test(item.id)
    && typeof item.filename === "string" && typeof item.fingerprint === "string"
    && /^[0-9a-f]{64}$/.test(item.fingerprint) && typeof item.created_at === "string"
    && Number.isFinite(Date.parse(item.created_at)))) {
    throw new Error("O servidor retornou dados inválidos do PDF guardado.");
  }
  return value as SavedSource[];
}
export function tailorResponse(value: unknown): { data: Result; version?: SavedVersion | null } {
  if (!object(value) || value.status !== "success" || !result(value.data)
    || (value.version != null && !version(value.version))) {
    throw new Error("O servidor retornou uma adaptação inválida. Tente novamente.");
  }
  return { data: value.data, version: value.version as SavedVersion | null | undefined };
}

export async function requestJson(url: string, init?: RequestInit): Promise<unknown> {
  let response: Response;
  const timeout = AbortSignal.timeout(150000);
  const signal = init?.signal ? AbortSignal.any([init.signal, timeout]) : timeout;
  try { response = await fetch(url, { ...init, signal }); }
  catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw error;
    if (error instanceof Error && error.name === "TimeoutError") {
      throw new Error("A operação demorou demais. Confira o histórico antes de solicitar outra geração.");
    }
    throw new Error("Não foi possível conectar ao backend. Confira se o serviço está ligado.");
  }
  let body: unknown;
  if (response.status === 204) return null;
  try { body = await response.json(); }
  catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw error;
    throw new Error("O servidor retornou uma resposta inesperada. Tente novamente.");
  }
  if (!response.ok) {
    throw new Error(object(body) && typeof body.detail === "string"
      ? body.detail : "Confira os dados enviados e tente novamente.");
  }
  return body;
}
