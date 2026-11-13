"use client";

import { useEffect, useRef, useState } from "react";
import { BriefcaseBusiness, Check, ChevronRight, Copy, Download, FileText, LoaderCircle, Radar, Search, ShieldCheck, Sparkles, Upload, X } from "lucide-react";
import Markdown from "react-markdown";
import Link from "next/link";
import { jobsResponse, requestJson, tailorResponse, versionsResponse, type Job, type Result, type SavedVersion } from "@/lib/api";

type CachedVersion = { data: Result; savedId?: string };
const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function versionsFor(records: SavedVersion[], fingerprint?: string) {
  const output: Record<string, CachedVersion> = {};
  for (const record of records) {
    const key = JSON.stringify([record.job_id ?? "manual", record.job_description]);
    if ((!fingerprint || record.source_fingerprint === fingerprint) && !output[key]) {
      output[key] = { data: record.data, savedId: record.id };
    }
  }
  return output;
}

export default function Home() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selected, setSelected] = useState<Job | null>(null);
  const [query, setQuery] = useState("");
  const [description, setDescription] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [versions, setVersions] = useState<Record<string, CachedVersion>>({});
  const [savedVersions, setSavedVersions] = useState<SavedVersion[]>([]);
  const [resumeToken, setResumeToken] = useState("");
  const [historyError, setHistoryError] = useState("");
  const [readingFile, setReadingFile] = useState(false);
  const [deletingIds, setDeletingIds] = useState<string[]>([]);
  const [historyHasMore, setHistoryHasMore] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [loading, setLoading] = useState(false);
  const [jobsLoading, setJobsLoading] = useState(true);
  const [error, setError] = useState("");
  const [jobsError, setJobsError] = useState("");
  const [copied, setCopied] = useState(false);
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const controller = useRef<AbortController | null>(null);
  const fileRead = useRef(0);
  const mutationRevision = useRef(0);
  const savedRef = useRef<SavedVersion[]>([]);
  const fingerprintRef = useRef<string | null>(null);
  const pendingDeletes = useRef(new Set<string>());
  const historyLoadingRef = useRef(false);
  const versionKey = JSON.stringify([selected?.id ?? "manual", description]);
  const result = versions[versionKey]?.data ?? null;
  const versionCount = Object.keys(versions).length;

  useEffect(() => {
    const abort = new AbortController();
    Promise.resolve().then(() => {
      if (abort.signal.aborted) return;
      try {
      let token = localStorage.getItem("job-radar-resume-token");
      if (!token || !/^[A-Za-z0-9_-]{32,160}$/.test(token)) {
        token = crypto.randomUUID();
        localStorage.setItem("job-radar-resume-token", token);
      }
      setResumeToken(token);
      const revision = mutationRevision.current;
      requestJson(`${API}/api/v1/resumes/versions`, { signal: abort.signal,
        headers: { "X-Resume-Token": token } }).then(body => {
        const records = versionsResponse(body);
        if (!abort.signal.aborted && revision === mutationRevision.current) {
          savedRef.current = records;
          setSavedVersions(records);
          setHistoryHasMore(records.length === 100);
          if (fileRead.current === 0) setVersions(versionsFor(records));
          else if (fingerprintRef.current) setVersions(versionsFor(records, fingerprintRef.current));
        }
      }).catch(err => { if (err.name !== "AbortError") setHistoryError(err.message); });
      } catch {
        setHistoryError("Permita o armazenamento local deste site para acessar seu histórico privado.");
      }
    });
    requestJson(`${API}/api/v1/jobs`, { signal: abort.signal }).then(body => {
      if (!abort.signal.aborted) setJobs(jobsResponse(body));
    }).catch(err => { if (err.name !== "AbortError") setJobsError("Não foi possível carregar as vagas. Verifique o backend e o banco de dados."); })
      .finally(() => setJobsLoading(false));
    return () => { abort.abort(); controller.current?.abort(); };
  }, []);

  function resetView() { controller.current?.abort(); controller.current = null; setLoading(false); setCopied(false); setError(""); }
  async function acceptFile(candidate?: File) {
    if (!candidate) return;
    if (!candidate.name.toLowerCase().endsWith(".pdf")) { setError("Selecione um arquivo PDF."); return; }
    if (candidate.size > 5 * 1024 * 1024) { setError("O PDF deve ter até 5 MB."); return; }
    resetView();
    setVersions({});
    fingerprintRef.current = null;
    const revision = ++fileRead.current;
    setReadingFile(true);
    setFile(candidate);
    try {
      const hash = await crypto.subtle.digest("SHA-256", await candidate.arrayBuffer());
      const fingerprint = Array.from(new Uint8Array(hash), byte => byte.toString(16).padStart(2, "0")).join("");
      if (revision === fileRead.current) {
        fingerprintRef.current = fingerprint;
        setVersions(versionsFor(savedRef.current, fingerprint));
      }
    } catch {
      if (revision === fileRead.current) setError("Não foi possível conferir o PDF selecionado. Tente novamente.");
    } finally {
      if (revision === fileRead.current) setReadingFile(false);
    }
  }
  async function tailor() {
    if (controller.current || result || readingFile) return;
    if (!resumeToken) { setError("Ative o armazenamento local para identificar seu histórico privado."); return; }
    if (!file || description.trim().length < 20) { setError("Adicione seu PDF e uma descrição de vaga com pelo menos 20 caracteres."); return; }
    const abort = new AbortController(); controller.current = abort;
    const requestKey = versionKey;
    setLoading(true); setError(""); setCopied(false);
    try {
      const form = new FormData(); form.append("resume_file", file); form.append("job_description", description);
      if (selected) form.append("job_id", String(selected.id));
      const body = tailorResponse(await requestJson(`${API}/api/v1/resumes/tailor`, { method: "POST", body: form,
        signal: abort.signal, headers: { "X-Resume-Token": resumeToken } }));
      if (!abort.signal.aborted && controller.current === abort) {
        setVersions(previous => ({ ...previous, [requestKey]: { data: body.data, savedId: body.version?.id } }));
        if (body.version) {
          const record = body.version;
          mutationRevision.current += 1;
          const next = [record, ...savedRef.current.filter(item => item.id !== record.id)];
          savedRef.current = next;
          setSavedVersions(next);
          setHistoryError("");
        }
      }
    } catch (err) { if (!abort.signal.aborted && controller.current === abort && err instanceof Error && err.name !== "AbortError") setError(err.message || "Falha na conexão."); }
    finally { if (controller.current === abort) { setLoading(false); controller.current = null; } }
  }
  function openSaved(record: SavedVersion) {
    resetView();
    fileRead.current += 1;
    setReadingFile(false);
    setFile(null);
    fingerprintRef.current = null;
    if (input.current) input.current.value = "";
    const job = jobs.find(item => item.id === record.job_id) ?? (record.job_id ? {
      id: record.job_id, title: record.job_title, company: record.company,
      description: record.job_description, location: "", skills: [], source_url: "",
    } : null);
    setSelected(job);
    setDescription(record.job_description);
    const key = JSON.stringify([record.job_id ?? "manual", record.job_description]);
    setVersions(previous => ({ ...previous, [key]: { data: record.data, savedId: record.id } }));
  }
  async function deleteSaved(record: SavedVersion) {
    if (pendingDeletes.current.has(record.id)) return;
    pendingDeletes.current.add(record.id);
    setDeletingIds([...pendingDeletes.current]);
    try {
      const response = await fetch(`${API}/api/v1/resumes/versions/${record.id}`, {
        method: "DELETE", headers: { "X-Resume-Token": resumeToken }, signal: AbortSignal.timeout(30000),
      });
      if (!response.ok) throw new Error("Não foi possível excluir essa versão.");
      const key = JSON.stringify([record.job_id ?? "manual", record.job_description]);
      mutationRevision.current += 1;
      const nextSaved = savedRef.current.filter(item => item.id !== record.id);
      savedRef.current = nextSaved;
      setSavedVersions(nextSaved);
      setVersions(previous => {
        if (previous[key]?.savedId !== record.id) return previous;
        const next = { ...previous }; delete next[key]; return next;
      });
      setHistoryError("");
    } catch (err) { setHistoryError(err instanceof Error ? err.message : "Falha ao excluir a versão."); }
    finally { pendingDeletes.current.delete(record.id); setDeletingIds([...pendingDeletes.current]); }
  }
  async function loadOlderVersions() {
    const last = savedRef.current.at(-1);
    if (!last || !resumeToken || historyLoadingRef.current) return;
    historyLoadingRef.current = true;
    setLoadingHistory(true);
    try {
      const records = versionsResponse(await requestJson(
        `${API}/api/v1/resumes/versions?before_id=${encodeURIComponent(last.id)}&limit=100`,
        { headers: { "X-Resume-Token": resumeToken } },
      ));
      const existing = new Set(savedRef.current.map(item => item.id));
      const next = [...savedRef.current, ...records.filter(item => !existing.has(item.id))];
      savedRef.current = next;
      setSavedVersions(next);
      setHistoryHasMore(records.length === 100);
      if (fileRead.current === 0 || fingerprintRef.current) {
        const older = versionsFor(records, fingerprintRef.current ?? undefined);
        setVersions(previous => ({ ...older, ...previous }));
      }
      setHistoryError("");
    } catch (err) {
      setHistoryError(err instanceof Error ? err.message : "Falha ao carregar versões anteriores.");
    } finally { historyLoadingRef.current = false; setLoadingHistory(false); }
  }
  async function copy() {
    try { await navigator.clipboard.writeText(result!.adapted_resume_markdown); setCopied(true); }
    catch { setError("Não foi possível copiar. Selecione o texto do currículo manualmente."); }
  }
  function download() {
    if (!result) return;
    const title = (selected?.title || "vaga-personalizada").normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "").replace(/[^a-zA-Z0-9_-]+/g, "-").slice(0, 80);
    const url = URL.createObjectURL(new Blob([result.adapted_resume_markdown], {
      type: "text/markdown;charset=utf-8",
    }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `curriculo-${title.toLowerCase()}.md`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const filtered = jobs.filter(j => `${j.title} ${j.company} ${j.skills.join(" ")}`.toLowerCase().includes(query.toLowerCase()));

  return <div className="min-h-screen bg-zinc-950 text-zinc-100">
    <header className="border-b border-white/10"><div className="mx-auto flex max-w-[1440px] items-center justify-between px-6 py-5 lg:px-10">
      <Link href="/" className="flex items-center gap-3 font-semibold tracking-tight"><span className="rounded-xl bg-lime-300 p-2 text-zinc-950"><Radar size={23}/></span>tech job radar<span className="hidden text-xs font-normal text-zinc-500 sm:inline">/ resume matcher</span></Link>
      <span className="flex items-center gap-2 text-xs text-zinc-400"><span className="h-1.5 w-1.5 rounded-full bg-lime-300"/>Ambiente local</span>
    </div></header>
    <main className="mx-auto max-w-[1440px] px-6 py-10 lg:px-10">
      <div className="mb-9 flex flex-wrap items-end justify-between gap-6"><div><p className="mb-3 text-xs font-medium uppercase tracking-[.2em] text-lime-300">Seu próximo passo em tech</p><h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Oportunidades certas.<br/><span className="text-zinc-500">Seu currículo, em sintonia.</span></h1><p className="mt-4 max-w-xl text-sm leading-6 text-zinc-400">Encontre uma vaga, adicione seu currículo e destaque o que você já sabe fazer.</p></div><div className="flex items-center gap-2 rounded-full border border-white/10 px-4 py-2 text-xs text-zinc-400"><ShieldCheck size={15} className="text-lime-300"/>PDF processado apenas em memória</div></div>
      <section className="mb-8 grid gap-5 rounded-2xl border border-white/10 bg-zinc-900/40 p-5 sm:grid-cols-[1fr_auto] sm:items-center">
        <div onDragOver={e => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); acceptFile(e.dataTransfer.files[0]); }} className={`flex items-center gap-4 rounded-xl border border-dashed p-4 ${dragging ? "border-lime-300 bg-lime-300/10" : "border-zinc-700"}`}>
          <Upload className="shrink-0 text-lime-300" size={23}/><div className="min-w-0 flex-1"><button type="button" onClick={() => input.current?.click()} className="max-w-full truncate text-left text-sm font-medium hover:text-lime-300">{file ? file.name : "Arraste seu currículo ou clique para selecionar"}</button><p className="mt-1 text-xs text-zinc-500">PDF com texto selecionável · até 5 MB · não armazenado</p></div>
          {file && <button aria-label="Remover currículo" onClick={() => { resetView(); fileRead.current += 1; fingerprintRef.current = null; setReadingFile(false); setVersions({}); setFile(null); if (input.current) input.current.value = ""; }}><X size={18}/></button>}
          <input ref={input} type="file" accept="application/pdf,.pdf" className="hidden" aria-label="Selecionar currículo PDF" onChange={e => acceptFile(e.target.files?.[0])}/>
        </div>
        <div className="max-w-xs text-xs leading-6 text-zinc-500"><span className="block font-medium text-zinc-300">Sua experiência é a fonte.</span>Ao adaptar, o texto é enviado ao provedor de IA configurado.</div>
      </section>
      <div className="grid items-start gap-6 lg:grid-cols-[.9fr_1.3fr]">
        <section className="rounded-2xl border border-white/10 bg-zinc-900/30"><div className="border-b border-white/10 p-5"><div className="mb-4 flex items-center justify-between"><h2 className="flex items-center gap-2 text-sm font-semibold"><BriefcaseBusiness size={17} className="text-zinc-400"/>Radar de vagas</h2><span className="text-xs text-zinc-500">{jobs.length} oportunidades</span></div><label className="flex items-center gap-2 rounded-lg border border-white/10 bg-zinc-950 px-3 py-2.5"><Search size={16} className="text-zinc-500"/><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Cargo, empresa ou tecnologia" aria-label="Buscar vagas" className="w-full bg-transparent text-sm outline-none placeholder:text-zinc-600"/></label></div>
          <div className="max-h-[420px] overflow-y-auto p-3">
            {jobsLoading ? <p className="p-5 text-sm text-zinc-500">Carregando vagas…</p>
              : jobsError ? <p role="alert" className="p-5 text-sm text-amber-200">{jobsError}</p>
              : filtered.length === 0 ? <div className="p-7 text-center">
                <Radar size={28} className="mx-auto mb-3 text-zinc-600"/>
                <p className="text-sm text-zinc-400">{jobs.length ? "Nenhuma vaga encontrada." : "Seu radar está pronto para receber vagas."}</p>
                <p className="mt-2 text-xs leading-5 text-zinc-600">Você também pode colar uma descrição abaixo.</p>
              </div> : filtered.map(job => <button key={job.id}
                onClick={() => { resetView(); setSelected(job); setDescription(job.description); }}
                className={`mb-2 w-full rounded-xl border p-4 text-left transition ${selected?.id === job.id ? "border-lime-300/50 bg-lime-300/5" : "border-transparent hover:bg-white/5"}`}>
                <div className="flex items-center justify-between gap-3"><span className="text-xs text-zinc-400">{job.company}</span>
                  <ChevronRight size={15} className={selected?.id === job.id ? "text-lime-300" : "text-zinc-600"}/></div>
                <h3 className="my-2 text-sm font-semibold">{job.title}</h3>
                <p className="text-xs text-zinc-500">{job.location}</p>
                <div className="mt-3 flex flex-wrap gap-1.5">{job.skills.map(skill => <span key={skill}
                  className="rounded bg-white/5 px-2 py-1 text-[10px] text-zinc-400">{skill}</span>)}</div>
                {versions[JSON.stringify([job.id, job.description])] && <span
                  className="mt-3 flex items-center gap-1 text-xs text-lime-300"><Check size={13}/>Currículo pronto</span>}
              </button>)}
          </div>
          <div className="border-t border-white/10 p-5">
            <label htmlFor="description" className="text-xs font-medium text-zinc-300">Descrição da vaga {selected && <span className="text-lime-300">{selected.description === description ? "· selecionada" : "· editada"}</span>}</label>
            <textarea id="description" value={description} maxLength={30000}
              onChange={e => { resetView(); setDescription(e.target.value); }} rows={5}
              placeholder="Selecione uma vaga acima ou cole a descrição aqui…"
              className="mt-3 w-full resize-y rounded-lg border border-white/10 bg-zinc-950 p-3 text-sm leading-6 outline-none focus:border-lime-300/50"/>
            <button onClick={tailor} disabled={loading || readingFile || !resumeToken || Boolean(result) || !file || description.trim().length < 20}
              className="mt-4 flex w-full items-center justify-center gap-2 rounded-lg bg-lime-300 px-4 py-3 text-sm font-semibold text-zinc-950 transition hover:bg-lime-200 disabled:cursor-not-allowed disabled:opacity-35">
              {loading ? <LoaderCircle size={17} className="animate-spin"/> : result ? <Check size={17}/> : <Sparkles size={17}/>}
              {loading ? "Organizando com evidências…" : readingFile ? "Conferindo PDF…" : result ? "Versão já gerada" : "Adaptar meu currículo"}
            </button>
            <p className="mt-3 text-xs leading-5 text-zinc-500">{versionCount} {versionCount === 1 ? "versão disponível" : "versões disponíveis"}. Volte às vagas marcadas para reutilizar sem gerar novamente. Outro PDF ou descrição exige uma versão compatível.</p>
          </div>
        </section>
        <section aria-live="polite" className="overflow-hidden rounded-2xl border border-white/10 bg-zinc-900/30">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-5 py-4">
            <h2 className="flex items-center gap-2 text-sm font-semibold"><FileText size={17} className="text-zinc-400"/>Seu currículo adaptado</h2>
            <div className="flex gap-2">
              <button onClick={download} disabled={!result} className="flex items-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-xs text-zinc-400 disabled:opacity-30"><Download size={14}/>Baixar Markdown</button>
              <button onClick={copy} disabled={!result} className="flex items-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-xs text-zinc-400 disabled:opacity-30">{copied ? <Check size={14}/> : <Copy size={14}/>} {copied ? "Copiado" : "Copiar Markdown"}</button>
            </div>
          </div>
          {result && <p className="px-5 pt-5 text-xs text-lime-300">Versão para {selected ? `${selected.title} · ${selected.company}` : "a descrição personalizada"}</p>}
          {error && <p role="alert" className="m-5 rounded-lg border border-red-400/20 bg-red-400/5 p-4 text-sm text-red-200">{error}</p>}
          {result ? <><div className="m-5 rounded-xl border border-lime-300/15 bg-lime-300/5 p-4"><div className="flex items-baseline gap-2"><strong className="text-3xl text-lime-300">{result.match_score}%</strong><span className="text-xs text-zinc-400">de coincidência textual com palavras-chave</span></div><p className="mt-2 text-xs text-zinc-500">Estimativa informativa; não representa avaliação de recrutadores.</p>{result.missing_critical_skills.length > 0 && <p className="mt-3 text-xs text-amber-200">Sem evidência no PDF: {result.missing_critical_skills.join(", ")}</p>}</div><article className="resume-preview min-h-[350px] p-6"><Markdown skipHtml urlTransform={() => ""}>{result.adapted_resume_markdown}</Markdown></article><div className="border-t border-white/10 p-5"><p className="mb-2 text-xs font-semibold text-zinc-300">O que mudou</p>{result.summary_of_changes.map(change => <p key={change} className="mt-2 text-xs leading-5 text-zinc-500">{change}</p>)}</div></> : <div className="flex min-h-[560px] flex-col items-center justify-center px-8 text-center"><div className={`mb-6 rounded-2xl border border-white/10 bg-zinc-900 p-5 ${loading ? "animate-pulse" : ""}`}><FileText size={34} strokeWidth={1} className="text-zinc-500"/></div><h3 className="text-lg font-medium">{loading ? "Conectando sua experiência à vaga" : "Sua próxima versão começa aqui"}</h3><p className="mt-3 max-w-xs text-sm leading-6 text-zinc-500">{loading ? "A IA organiza as seções. Cada trecho é conferido com o PDF original antes de aparecer aqui." : "Adicione um currículo e escolha uma oportunidade para visualizar uma versão organizada para ATS."}</p><div className="mt-9 flex items-center gap-3 text-[11px] text-zinc-600"><span>01 PDF</span><ChevronRight size={12}/><span>02 Vaga</span><ChevronRight size={12}/><span>03 Adaptação</span></div></div>}
        </section>
      </div>
      <section aria-label="Histórico de currículos" className="mt-6 rounded-2xl border border-white/10 bg-zinc-900/30 p-5">
        <div className="mb-3 flex items-center justify-between gap-3"><h2 className="text-sm font-semibold">Versões salvas por vaga</h2><span className="text-xs text-zinc-500">{savedVersions.length} versões</span></div>
        <p className="mb-4 text-xs leading-5 text-zinc-500">O texto adaptado fica no banco local e pode ser consultado pelo seu bot privado do Hermes. O PDF original não é armazenado. Este navegador mantém apenas a identificação privada do seu histórico.</p>
        {historyError && <p role="alert" className="mb-4 text-xs text-amber-200">{historyError}</p>}
        {savedVersions.length === 0 ? <p className="text-sm text-zinc-500">As versões aparecerão aqui após a primeira adaptação.</p>
          : <ul className="grid gap-3 sm:grid-cols-2">{savedVersions.map(record => <li key={record.id} className="rounded-xl border border-white/10 p-4">
            <p className="text-sm font-medium">{record.job_title}</p><p className="mt-1 text-xs text-zinc-500">{record.company || "Descrição personalizada"} · {new Date(record.created_at).toLocaleString("pt-BR")}</p>
            <div className="mt-3 flex gap-4"><button onClick={() => openSaved(record)} aria-label={`Abrir currículo de ${record.job_title}`} className="text-xs text-lime-300">Abrir versão</button>
              <button disabled={deletingIds.includes(record.id)} onClick={() => deleteSaved(record)} aria-label={`Excluir versão de ${record.job_title}`} className="text-xs text-zinc-500 hover:text-red-300">Excluir versão</button></div>
          </li>)}</ul>}
        {historyHasMore && <button onClick={loadOlderVersions} disabled={loadingHistory} className="mt-4 rounded-lg border border-white/10 px-4 py-2 text-xs text-zinc-300 disabled:opacity-40">{loadingHistory ? "Carregando…" : "Carregar versões anteriores"}</button>}
      </section>
      <footer className="mt-8 flex flex-wrap justify-between gap-3 border-t border-white/5 pt-5 text-[11px] text-zinc-600"><span>Tech Job Radar · Tailored Resume Matcher</span><span>Revise o resultado antes de enviar sua candidatura.</span></footer>
    </main>
  </div>;
}
