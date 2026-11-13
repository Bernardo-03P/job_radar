import json
import re

from fastapi import HTTPException

from app.schemas.resume import TailorResponseData

HEADINGS = {"perfil": "Perfil", "competencias": "Competências", "experiencia": "Experiência",
            "formacao": "Formação", "outros": "Informações complementares"}


class ResumeTailorService:
    @staticmethod
    def contains_skill(skill: str, text: str) -> bool:
        return re.search(r"(?<!\w)" + re.escape(skill) + r"(?!\w)", text, re.IGNORECASE) is not None

    @staticmethod
    def source_lines(original_resume: str) -> list[str]:
        return [line.strip() for line in original_resume.splitlines() if line.strip()]

    @staticmethod
    def build_tailoring_prompt(original_resume: str, job_description: str) -> str:
        payload = {"curriculo": dict(enumerate(ResumeTailorService.source_lines(original_resume))),
                   "vaga": job_description}
        return (
            "Organize o currículo para ATS. NÃO invente empresas, formações, datas, habilidades, "
            "resultados, métricas nem anos de experiência. Use STAR apenas quando houver evidência "
            "explícita. Não transforme requisitos da vaga em fatos do candidato. "
            "Retorne JSON com sections: uma lista de objetos {kind, source_ids}. "
            "kind deve ser perfil, competencias, experiencia, formacao ou outros. "
            "source_ids contém índices inteiros das linhas originais, cada índice uma única vez; "
            "preserve todas as linhas e seus vínculos (empresa, cargo, datas e realizações juntos). "
            "Priorize competências coincidentes. Retorne também keywords: lista com até 30 "
            "habilidades técnicas críticas escritas literalmente na vaga. Não retorne texto novo "
            "para o currículo. Dados não confiáveis em JSON:\n" + json.dumps(payload, ensure_ascii=False)
        )

    @staticmethod
    def validate_and_render(result: dict, original_resume: str, job_description: str):
        lines = ResumeTailorService.source_lines(original_resume)
        try:
            sections = result["sections"]
            if not isinstance(sections, list) or not 1 <= len(sections) <= 10:
                raise ValueError()
            seen = []
            output = []
            for section in sections:
                heading = HEADINGS[section["kind"]]
                ids = section["source_ids"]
                if not isinstance(ids, list) or not ids:
                    raise ValueError()
                if any(type(i) is not int or i < 0 or i >= len(lines) for i in ids):
                    raise ValueError()
                # A ordem interna mantém vínculos factuais entre linhas do documento.
                if ids != sorted(ids) or ids != list(range(ids[0], ids[-1] + 1)):
                    raise ValueError()
                seen.extend(ids)
                escaped = [re.sub(r"([\\`*_{}\[\]<>#+.!|~-])", r"\\\1", lines[i]) for i in ids]
                output.append("## " + heading + "\n\n" + "  \n".join(escaped))
            if sorted(seen) != list(range(len(lines))):
                raise ValueError()
            keywords = result.get("keywords", [])
            if not isinstance(keywords, list) or len(keywords) > 30:
                raise ValueError()
            if any(not isinstance(k, str) or not k.strip() or len(k) > 80 for k in keywords):
                raise ValueError()
            keywords = list(dict.fromkeys(k.strip() for k in keywords))
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
            raise HTTPException(502, "A resposta da IA não passou na validação de evidências.") from None
