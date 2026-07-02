# Dutch Vocabulary Learning System — Design Document

## 1. Goal

Automate creation and prioritization of Anki flashcards for Dutch vocabulary
acquisition, driven by a frequency dictionary (Routledge *Frequency
Dictionary of Dutch*, personal use only — do not redistribute derived data
publicly). The system should:

- Generate cards for high-frequency words first, working down the frequency list.
- Build example sentences (retrieved or generated) that stay within
  vocabulary the learner already knows or is currently learning.
- Attach natural-sounding Dutch audio.
- Read real study performance back from Anki and use it to reorder
  not-yet-seen cards and generate targeted reinforcement cards.
- Do all of this in a token-efficient way: numeric/lookup work happens in
  code, the LLM is only used for what it's actually good at (fluent
  sentence generation, judgment calls).

Not doing: rebuilding Anki's UI, scheduler, or sync. Anki + AnkiConnect +
genanki/AnkiConnect writes are the substrate; this system only decides
*what* goes in and *in what order new cards are introduced*.

---

## 2. Source data: the frequency dictionary

Raw format (per entry, plain text):

```
509 televisie noun de(f) television
• Hij zette de televisie aan om naar het nieuws te kijken.
16.55
```

Fields: `rank`, `headword` (lemma — all entries are already lemmatized:
verbs as infinitive, adjectives/adverbs collapsed to base form), `POS`,
`gender` (nouns only), `English gloss`, one or more `•` example sentences,
`occurrences per 100 documents`.

### 2.1 Parsing rules

- New entry starts on a line beginning with an integer followed by a word
  (not a bare float).
- POS is one of a fixed small vocabulary (noun, verb, adj, adv, prep,
  conj, pron, article, interj, number, noun pl) — split on POS first, then
  check whether the following token is a gender marker
  (`de`, `het`, `de/het`, `de(m)`, `de(f)`) to handle the variable field
  count between nouns and everything else.
- Lines starting with `•` are examples for the current entry; collect
  until the next rank-initial line.
- A bare float line closes the entry (frequency stat).
- Gender normalization: collapse `de(m)` / `de(f)` → `de` for the primary
  `gender` field (both take *de*, agree identically). Optionally keep the
  m/f distinction in a secondary `gender_note` column since it's
  disappearing in NL usage anyway and isn't pedagogically load-bearing.
- `noun pl` entries (e.g. *hersenen*) should be carded in plural form —
  singular doesn't exist/isn't the target.
- Multi-word glosses and POS values (e.g. "noun pl") should not break the
  splitter — parse POS as a whitelist match, not by token count.

### 2.2 Target schema (normalized, two tables)
words.csv

```
id
rank
list
lemma
variants
pos
gender
sense_count
gloss
freq
```

Column definitions

Column  Type  Notes
id  string  Unique identifier. Format: <list>_<6-digit rank> (e.g. core_000509). Never changes.
rank  integer Rank within the original frequency list.
list  string  Source list (e.g. core, spoken, general, …).
lemma string  Canonical dictionary form only.
variants  string  Alternative spellings/forms separated by |
pos string  One or more standardized parts of speech separated by |
gender  string  Only for nouns: de, het, de/het. Empty otherwise. (de(m) and de(f) are both normalized to de.)
sense_count integer Number of meanings/POS senses listed in the source. Usually 1, sometimes 2 or more.
gloss string  English meanings in source order, separated by |
freq  decimal Frequency per 100 documents.

⸻

examples.csv

id
example_order
example_nl

Column definitions

Column  Type  Notes
id  string  Foreign key referencing words.csv.
example_order integer 1, 2, 3… in source order.
example_nl  string  One example sentence per row, preserving the original text (including labels like a) or 1) when they are part of the source).

⸻

Example

words.csv

id,rank,list,lemma,variants,pos,gender,sense_count,gloss,freq
core_000009,9,core,voor,,prep,,2,for | in front of,99.61

examples.csv

id,example_order,example_nl
core_000009,1,"Ik vind het leuk om voor hem te koken."
core_000009,2,"We staan voor de deur van het hotel."


---

## 3. Core design principle: split by capability

- **Code** owns anything numeric or exact: frequency lookups, rank
  comparisons, coverage checks, band definitions, position math for Anki
  reordering. Never put the frequency list in a prompt.
- **LLM** owns anything requiring fluency/judgment: writing a natural
  sentence, deciding a repair when a sentence fails the coverage check,
  interpreting struggle patterns.
- A **verify-and-repair loop** connects them: LLM proposes, code checks
  against the lemma list, code sends back a short targeted correction if
  needed ("replace X, Y — too rare"), rather than re-explaining the whole
  task.

This keeps token cost low (small, batched prompts; no large data dumps)
and keeps the accuracy-critical parts (frequency membership, gender)
deterministic rather than model-guessed.

---

## 4. Sentence construction pipeline

### 4.1 Lemmatization requirement

Generated/candidate sentences arrive as **surface forms** (inflected:
*loopt*, *liep*, *fietsen*). The word list is **lemma-based**. Matching
must happen in lemma space, or the same word will appear at wildly
different "ranks" depending on which inflection was used, corrupting the
coverage metric.

- Use `spaCy` (`nl_core_news_sm`) or Stanza to tokenize + lemmatize each
  candidate sentence at check time.
- Match **lemma as primary key**; treat POS as a soft tiebreaker only
  (don't hard-require POS match — the dictionary merges some things a
  generic lemmatizer splits, e.g. adverbial use of adjectives like *mooi*
  filed under adjective; lexicalized participles like *beslist*,
  *geregeld* filed as their own adjective entries separate from the parent
  verb). Strict POS+lemma matching would cause false misses on common
  words.
- Known gap: separable verbs (*belt … op* → *opbellen*) need
  special-cased reconstruction; spaCy won't reliably merge these back into
  the dictionary's single infinitive entry. Handle as a follow-up
  refinement, not a v1 blocker.

### 4.2 "Known set" and bands

- **Known set** = lemmas the learner has already started studying in
  Anki, queryable live via AnkiConnect (`deck:Dutch -is:new`), unioned
  with the current frequency band being worked through.
- **Bands** pace *which words become targets* (e.g. exhaust rank 1–500 as
  targets before moving to 501–1000) — they do not police word ratios
  within a single sentence (percentage-per-sentence rules are brittle on
  short sentences).
- **Per-sentence constraint**: every content word in a carrier sentence
  must be in the known set, with the current target lemma as the one
  permitted exception (classic i+1 / comprehensible-input rule). Function
  words are lenient (see 4.4).
- Coverage check = count content-word lemmas outside the known set; accept
  if ≤ 1 (the target itself).

### 4.3 Sentence source: retrieval before generation

Because the dictionary already ships a real, level-appropriate example
sentence per lemma, prefer retrieval over generation:

1. For a given target lemma, pull its example(s) from `examples.csv`.
2. Run the coverage check on the dictionary sentence as-is.
3. If it passes (or passes with minor known-set gaps that are themselves
   soon-to-be-learned high-frequency words) — use it directly. Zero
   generation cost.
4. If no example passes (target is rare enough that its example sentence
   uses other rare words), fall back to LLM generation.

Fallback (Tatoeba corpus) can be considered later if dictionary examples
are insufficiently varied, but is not required for v1 given the
dictionary already provides curated examples.

### 4.4 Generation fallback (when retrieval fails)

- Batch requests: send the LLM ~15–20 target lemmas at once, ask for one
  simple Dutch sentence per lemma, JSON out. Batching amortizes prompt
  overhead across many cards — this is the single biggest token saving,
  larger than any per-sentence optimization.
- Code lemmatizes + checks each returned sentence against the known set.
- Failing sentences go back in a small follow-up batch with the specific
  offending words named ("sentence for X used lemma Y which is out of
  band — retry avoiding it"), not the full instructions again.
- Function words (prepositions, conjunctions, pronouns, articles) are not
  carded in isolation (a bare gloss is close to meaningless per the
  dictionary's own note that prepositions carry "the most common meaning"
  only) — they're absorbed naturally through carrier sentences instead of
  being frequency-gated targets themselves.

---

## 5. Card schema and POS-based routing

Route card construction by POS:

- **Noun**: headword + article (`de`/`het`/`de-het shown for duals`) +
  gloss + example. Plural-only entries carded in plural form.
- **Verb**: infinitive as headword + gloss + example; consider adding key
  conjugated forms for irregular/strong verbs as a secondary field later.
- **Adjective**: base form + gloss + example.
- **Adverb / interjection / number**: simple headword + gloss + example,
  smaller/separate frequency handling (not the main content-word queue).
- **Preposition / conjunction / pronoun / article**: generally *not*
  carded standalone — learned through recurring exposure in carrier
  sentences for content-word targets.

---

## 6. Audio

- Let's start first from a cheaper fallback / bootstrap option: Anki's built-in `{{tts nl_NL:Field}}`
  templates use the device's OS voice at review time — zero pipeline, can
  ship v1 with this and swap in pre-generated audio later without
  reworking the card schema.
- Do **not** automate via HyperTTS — it's GUI-only, no CLI/HTTP surface;
  keep it available for ad hoc manual batches only.
- Automated pipeline calls a cloud neural TTS provider directly (Azure
  Neural or Google Neural2, both have solid `nl-NL` voices; well within
  free/cheap tiers at this vocabulary volume) and attaches the resulting
  mp3 as Anki media.

---

## 7. Anki integration (AnkiConnect)

### 7.1 Reading state

- `cardsInfo` — per-card interval, ease, reps, lapses, due, queue, type.
- `getReviews` (per card) — full review log (button pressed, time,
  interval before/after) — best source for "struggling" signal.
- `findCards` — query, e.g. `deck:Dutch prop:lapses>1`.
- `getDeckStats` — high-level new/learning/review counts.
- **Scheduler caveat**: the collection uses FSRS (current Anki
  default), so the old `ease factor` field is largely vestigial — use
  lapses / again-rate / FSRS difficulty as the struggle signal, not ease
  factor.

### 7.2 Writing — the safe boundary

- **Never touch scheduling on cards already in learning/review.** All
  reordering operations are scoped to `is:new` only.
- For new cards, `due` **is** queue position. Reordering new cards =
  rewriting `due` via `setSpecificValueOfCard`.
- Design: each note carries an AI-computed `Priority` field (derived from
  frequency rank + observed struggle patterns on related/prerequisite
  words). Sort new cards by `Priority`, write resulting sequential
  positions to `due`.
- Precondition to check once: the deck's **new card sort order** option
  must be position-based, not random, or written positions get ignored.
- Reinforcement cards for struggled words are just new notes (`addNotes`
  + `storeMediaFile`) — no scheduling risk at all.
- Safety: back up (File → Export) before first automated write run.
  `setSpecificValueOfCard` bypasses normal UI safety, so keep all writes
  scoped and reversible via export.

### 7.3 Suggested loop

```
findCards / cardsInfo / getReviews
        → compute struggle scores + priority ordering (code)
        → LLM: decide/generate reinforcement targets if needed
        → addNotes (reinforcement) + setSpecificValueOfCard (reposition new queue)
        → sync
```

Consider using the existing community "AnkiConnect" skill for Claude Code
as a starting scaffold for the HTTP call plumbing rather than hand-rolling
it — it already wraps the action catalog and includes a
confirm-before-modifying safeguard, which is a reasonable default to keep
even once the pipeline is trusted.

---

## 8. Open items / follow-ups (not blocking v1)

- Separable verb reconstruction in the lemmatizer.
- Tatoeba fallback for retrieval if dictionary examples prove
  insufficient in variety.
- Conjugated-form secondary fields for irregular verbs.
- Whether to preserve m/f gender sub-marking or drop entirely.
- iOS vs Android target (AnkiMobile vs AnkiDroid) — affects audio format
  assumptions only marginally, otherwise pipeline is identical.

---

## 9. Non-goals

- No rebuild of Anki's review UI, scheduler, or sync — genanki /
  AnkiConnect / AnkiWeb handle all of that.
- No public redistribution of frequency-list-derived data (copyrighted
  source, personal use only).
- No LLM-side frequency judgment — all frequency/rank decisions are
  code-side, deterministic, CSV-driven.
