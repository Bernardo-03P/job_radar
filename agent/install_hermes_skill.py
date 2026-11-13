"""Instala a skill local no Hermes existente; não altera tokens, modelo ou gateway."""
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def main():
    values = dotenv_values(ROOT / ".env")
    home = Path(str(values.get("JOB_RADAR_HERMES_HOME") or "")).resolve()
    if not (home / "config.yaml").is_file():
        raise SystemExit("Defina JOB_RADAR_HERMES_HOME para a instalação existente do Hermes.")
    skill = (home / "skills" / "job-radar" / "SKILL.md").resolve()
    if home not in skill.parents:
        raise SystemExit("Destino inválido para instalação da skill.")
    content = (ROOT / "agent/hermes_skill/SKILL.md").read_text(encoding="utf-8")
    content = content.replace("{{WORKSPACE}}", ROOT.as_posix())
    if skill.exists() and "# Job Radar — vagas e currículos por vaga" not in skill.read_text(encoding="utf-8"):
        raise SystemExit("Já existe outra skill com esse nome; ela não foi sobrescrita.")
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text(content, encoding="utf-8")
    print("Skill job-radar instalada no Hermes existente. Nenhum token foi exibido ou alterado.")


if __name__ == "__main__":
    main()
