"use client";

import { useRef, useState } from "react";
import { requestJson, sourcesResponse, type SavedSource } from "@/lib/api";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function ResumeSourceControls({ file, token }: { file: File | null; token: string }) {
  const [source, setSource] = useState<SavedSource | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const active = useRef(false);

  async function execute(action: "save" | "load" | "delete") {
    if (active.current || !token || (action === "save" && !file)) return;
    active.current = true;
    setBusy(true);
    setMessage("");
    try {
      const headers = { "X-Resume-Token": token };
      if (action === "save") {
        const body = new FormData();
        body.append("resume_file", file!);
        const saved = sourcesResponse([await requestJson(`${API}/api/v1/resumes/sources`, {
          method: "POST", headers, body,
        })])[0];
        setSource(saved);
        setMessage("PDF guardado neste PC. Agora você pode pedir um currículo para uma vaga escolhida no seu Telegram.");
      } else if (action === "delete" && source) {
        await requestJson(`${API}/api/v1/resumes/sources/${source.id}`, { method: "DELETE", headers });
        setSource(null);
        setMessage("PDF original excluído. As versões adaptadas continuam no histórico.");
      } else {
        const saved = sourcesResponse(await requestJson(`${API}/api/v1/resumes/sources`, { headers }));
        setSource(saved[0] || null);
        setMessage(saved.length ? "PDF disponível para pedidos pelo Telegram." : "Este navegador não tem PDF guardado.");
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Não foi possível acessar o PDF guardado.");
    } finally {
      active.current = false;
      setBusy(false);
    }
  }

  return <section aria-label="PDF para o Telegram" className="mb-8 rounded-xl border border-white/10 p-5 text-xs leading-6 text-zinc-400">
    <h2 className="font-semibold text-zinc-200">PDF original para o Telegram · opcional</h2>
    <p>Ao clicar em guardar, uma cópia protegida ficará neste PC para gerar currículos quando você escolher uma vaga no seu bot privado. Guardar não chama a IA. Você pode excluir o original aqui.</p>
    <div className="mt-3 flex flex-wrap gap-3">
      <button disabled={busy || !token || !file} onClick={() => execute("save")} className="rounded border border-lime-300/40 px-3 py-2 text-lime-300 disabled:opacity-35">Guardar PDF para o Telegram</button>
      <button disabled={busy || !token} onClick={() => execute("load")} className="rounded border border-white/20 px-3 py-2 disabled:opacity-35">Consultar PDF guardado</button>
      {source && <button disabled={busy} onClick={() => execute("delete")} className="rounded border border-white/20 px-3 py-2 disabled:opacity-35">Excluir PDF guardado</button>}
    </div>
    {source && <p className="mt-3">Original disponível: <span className="text-zinc-200">{source.filename}</span></p>}
    {message && <p role="status" className="mt-3 text-zinc-300">{message}</p>}
  </section>;
}
