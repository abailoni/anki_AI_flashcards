"""Phase 1 pipeline entrypoint. Re-run after each handoff/response.json update."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dutch_cards.data import load_examples, load_words, known_set
from dutch_cards.nlp import check_coverage
from dutch_cards.pipeline import (
    MAX_ROUNDS,
    REQUEST_PATH,
    RESPONSE_PATH,
    Outcome,
    load_state,
    read_response,
    resolve_by_retrieval,
    save_state,
    write_request,
)
from dutch_cards.report import write_report

WORDS_PATH = Path("data/fixtures/words_partial.csv")
EXAMPLES_PATH = Path("data/fixtures/examples_partial.csv")


def main() -> None:
    words = load_words(WORDS_PATH)
    examples = load_examples(EXAMPLES_PATH)
    known = known_set(words)
    by_id = {w.id: w for w in words}

    state = load_state()
    outcomes: dict[str, Outcome] = {
        wid: Outcome(**o) for wid, o in state.get("outcomes", {}).items()
    }

    if not outcomes:
        resolved, pending = resolve_by_retrieval(words, examples, known)
        outcomes.update(resolved)
        state["round"] = 0
        state["pending_ids"] = [w.id for w in pending]
    else:
        pending = [by_id[wid] for wid in state.get("pending_ids", [])]

    if not pending:
        write_report(outcomes, len(words))
        save_state({"round": state["round"], "outcomes": {}, "pending_ids": []})
        print(f"Phase 1 pipeline complete. Report: reports/phase1_coverage_report.md")
        return

    if RESPONSE_PATH.exists():
        responses = read_response()
        still_pending = []
        feedback: dict[str, list[str]] = {}
        for w in pending:
            sentence = responses.get(w.id)
            if sentence is None:
                still_pending.append(w)
                continue
            passed, offending = check_coverage(sentence, known, w.lemma)
            if passed:
                outcomes[w.id] = Outcome(w.id, w.lemma, "llm_generated", sentence, "pass")
            elif state["round"] + 1 >= MAX_ROUNDS:
                outcomes[w.id] = Outcome(w.id, w.lemma, "failed", sentence, "failed_exhausted")
            else:
                still_pending.append(w)
                feedback[w.id] = offending
        pending = still_pending
        RESPONSE_PATH.unlink()

        if pending:
            state["round"] += 1
            state["pending_ids"] = [w.id for w in pending]
            write_request(pending, known, feedback)
        else:
            state["pending_ids"] = []

    else:
        write_request(pending, known)

    state["outcomes"] = {wid: vars(o) for wid, o in outcomes.items()}
    save_state(state)

    if pending:
        print(
            f"{len(pending)} word(s) need LLM-generated sentences (round {state['round']}).\n"
            f"Hand {REQUEST_PATH} to Claude Code, ask it to write {RESPONSE_PATH}, "
            f"then re-run this script."
        )
    else:
        write_report(outcomes, len(words))
        print(f"Phase 1 pipeline complete. Report: reports/phase1_coverage_report.md")


if __name__ == "__main__":
    main()
