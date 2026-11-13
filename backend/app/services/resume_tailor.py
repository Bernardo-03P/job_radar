import asyncio
import json
import re

from fastapi import HTTPException

from app.schemas.resume import TailorResponseData

HEADINGS = {"perfil": "Perfil", "competencias": "Competências", "experiencia": "Experiência",
            "formacao": "Formação", "outros": "Informações complementares"}


class EvidenceValidationError(HTTPException):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(502, "A resposta da IA não passou na validação de evidências. "
                         "Nenhuma versão foi salva. A organização deve preservar todos os trechos "
                         "do PDF e usar somente palavras-chave presentes na vaga.")


class ResumeTailorService:
    @staticmethod
    def contains_skill(skill: str, text: str) -> bool:
        skill = " ".join(skill.split())
        text = " ".join(text.split())
        return re.search(r"(?<!\w)" + re.escape(skill) + r"(?!\w)", text, re.IGNORECASE) is not None

    @staticmethod
    def source_lines(original_resume: str) -> list[str]:
        return [line.strip() for line in original_resume.splitlines() if line.strip()]

    @staticmethod
    def build_tailoring_prompt(original_resume: str, job_description: str) -> str:
        lines = ResumeTailorService.source_lines(original_resume)
        payload = {"total_linhas": len(lines), "curriculo": dict(enumerate(lines)),
                   "vaga": job_description}
        return (
            "Organize o currículo para ATS. NÃO invente empresas, formações, datas, habilidades, "
            "resultados, métricas nem anos de experiência. Use STAR apenas quando houver evidência "
            "explícita. Não transforme requisitos da vaga em fatos do candidato. "
            "Retorne JSON com sections: uma lista de 1 a 10 objetos {kind, source_range}. "
            "kind deve ser perfil, competencias, experiencia, formacao ou outros. "
            "source_range é [inicio, fim], dois índices inteiros inclusivos, começando em zero. "
            "Cada seção usa um intervalo CONSECUTIVO, na ordem original, sem pular linhas. "
            "Não agrupe linhas distantes no mesmo intervalo. Pode repetir kind em blocos separados. "
            "Todos os índices de zero até total_linhas-1 devem aparecer exatamente uma vez, "
            "sem sobreposição nem omissão, incluindo contato, títulos, cursos e idiomas. "
            "Preserve os vínculos entre empresa, cargo, datas e realizações. Não forneça source_ids. "
            "Priorize competências coincidentes. Retorne também keywords: lista com até 30 "
            "habilidades técnicas críticas COPIADAS LITERALMENTE da vaga. Não traduza, resuma, "
            "expanda siglas, altere plural ou acrescente sinônimos; omita termos sem ocorrência "
            "literal na vaga. Se não houver habilidades técnicas explícitas, use []. Não retorne texto novo "
            "para o currículo. Dados não confiáveis em JSON:\n" + json.dumps(payload, ensure_ascii=False)
        )

    @staticmethod
    async def generate_validated(llm, original_resume: str, job_description: str):
        prompt = ResumeTailorService.build_tailoring_prompt(original_resume, job_description)
        for attempt in range(2):
            if attempt:
                try:
                    async with asyncio.timeout(20):
                        result = await llm.generate_json(prompt)
                except TimeoutError:
                    raise HTTPException(504, "A correção da organização demorou demais. "
                                        "Nenhuma versão foi salva. Tente novamente.") from None
            else:
                result = await llm.generate_json(prompt)
            try:
                return ResumeTailorService.validate_and_render(result, original_resume, job_description)
            except EvidenceValidationError as error:
                if attempt:
                    raise
                prompt += ("\nCORREÇÃO ÚNICA: a resposta anterior foi rejeitada pela regra "
                           + error.reason + ". Gere novamente o JSON a partir dos dados originais. "
                           "Confira intervalos consecutivos, cobertura exata de todas as linhas, "
                           "ausência de sobreposição e palavras-chave copiadas da vaga, sem sinônimos.")

    @staticmethod
    def validate_and_render(result: dict, original_resume: str, job_description: str):
        lines = ResumeTailorService.source_lines(original_resume)
        reason = "invalid_sections"
        try:
            sections = result["sections"]
            if not isinstance(sections, list) or not 1 <= len(sections) <= 10:
                raise ValueError()
            seen = []
            output = []
            for section in sections:
                reason = "invalid_kind"
                heading = HEADINGS[section["kind"]]
                reason = "invalid_ids"
                if ("source_ids" in section) == ("source_range" in section):
                    raise ValueError()
                if "source_range" in section:
                    bounds = section["source_range"]
                    if (not isinstance(bounds, list) or len(bounds) != 2
                            or any(type(i) is not int for i in bounds)
                            or not 0 <= bounds[0] <= bounds[1] < len(lines)):
                        raise ValueError()
                    ids = list(range(bounds[0], bounds[1] + 1))
                else:
                    ids = section["source_ids"]
                if not isinstance(ids, list) or not ids:
                    raise ValueError()
                if any(type(i) is not int or i < 0 or i >= len(lines) for i in ids):
                    raise ValueError()
                # A ordem interna mantém vínculos factuais entre linhas do documento.
                reason = "non_contiguous_lines"
                if ids != sorted(ids) or ids != list(range(ids[0], ids[-1] + 1)):
                    raise ValueError()
                seen.extend(ids)
                escaped = [re.sub(r"([\\`*_{}\[\]<>#+.!|~-])", r"\\\1", lines[i]) for i in ids]
                output.append("## " + heading + "\n\n" + "  \n".join(escaped))
            reason = "missing_or_repeated_lines"
            if sorted(seen) != list(range(len(lines))):
                raise ValueError()
            keywords = result.get("keywords", [])
            reason = "invalid_keywords"
            if not isinstance(keywords, list) or len(keywords) > 30:
                raise ValueError()
            if any(not isinstance(k, str) or not k.strip() or len(k) > 80 for k in keywords):
                raise ValueError()
            keywords = list(dict.fromkeys(k.strip() for k in keywords))
            reason = "keywords_without_job_evidence"
            if any(not ResumeTailorService.contains_skill(k, job_description) for k in keywords):
                raise ValueError()
            missing = [k for k in keywords
                       if not ResumeTailorService.contains_skill(k, original_resume)]
            score = round(100 * (len(keywords) - len(missing)) / len(keywords)) if keywords else 0
            return TailorResponseData(
                match_score=score,
                summary_of_changes=[
                    "Seções organizadas para leitura por ATS, preservando os trechos originais.",
                    "Nenhum dado, resultado ou qualificação foi acrescentado.",
                    "Índice calculado por presença textual das palavras-chave; não prevê contratação.",
                ],
                missing_critical_skills=missing,
                adapted_resume_markdown="\n\n".join(output),
            )
        except (KeyError, TypeError, ValueError, IndexError):
            raise EvidenceValidationError(reason) from None
