from pathlib import Path

from dutch_cards.pipeline import Outcome

REPORT_PATH = Path("reports/phase1_coverage_report.md")


def write_report(outcomes: dict[str, Outcome], total: int) -> None:
    by_source = {"dictionary_example": [], "llm_generated": [], "failed": []}
    for o in outcomes.values():
        by_source[o.source].append(o)

    lines = [
        "# Phase 1 coverage report",
        "",
        f"- Total words: {total}",
        f"- Resolved by dictionary retrieval: {len(by_source['dictionary_example'])}",
        f"- Resolved by LLM generation: {len(by_source['llm_generated'])}",
        f"- Failed (exhausted repair rounds): {len(by_source['failed'])}",
        "",
        "## Words",
        "",
        "| lemma | source | status | sentence |",
        "|---|---|---|---|",
    ]
    for o in sorted(outcomes.values(), key=lambda o: o.word_id):
        sentence = (o.sentence or "").replace("|", "\\|")
        lines.append(f"| {o.lemma} | {o.source} | {o.status} | {sentence} |")

    if by_source["failed"]:
        lines += ["", "## Failed / exhausted"]
        for o in by_source["failed"]:
            lines.append(f"- {o.lemma} ({o.word_id})")

    REPORT_PATH.parent.mkdir(exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
