---
created:
updated:
topic: daily papers
frequency: daily
ongoing: false
unread: false
---

> [!prompt]- Agent Instructions
> Daily digest of new papers from arXiv and multiple journals. Abstracts only (no agent-written summaries) — the user wants the paper's own words plus a link. Pick 3-5 most relevant per day.
>
> ## Sources to fetch
>
> ### Open-access primary (RSS/API, no auth)
>
> - **arXiv quant-ph** — `http://export.arxiv.org/rss/quant-ph`
> - **arXiv cs.IT** — `http://export.arxiv.org/rss/cs.IT`
> - **arXiv cond-mat.mes-hall** — `http://export.arxiv.org/rss/cond-mat.mes-hall`
> - **Quantum (journal)** — `https://quantum-journal.org/papers/feed/`
> - **SciPost Physics** — `https://scipost.org/SciPostPhys/feed/atom.xml`
> - **PRX Quantum** — `https://journals.aps.org/prxquantum/feed.rss`
> - **npj Quantum Information** — `https://www.nature.com/npjqi.rss`
> - **Communications Physics** — `https://www.nature.com/commsphys.rss`
> - **New Journal of Physics** — `https://iopscience.iop.org/journal/rss/1367-2630`
>
> ### Paywalled but abstracts free
>
> - **Physical Review Letters** — `https://journals.aps.org/prl/recent.rss` (filter for quantum-related)
> - **Physical Review A** — `https://journals.aps.org/pra/recent.rss`
> - **Physical Review X** — `https://journals.aps.org/prx/recent.rss`
> - **Nature Physics** — `https://www.nature.com/nphys.rss`
>
> ### Cross-validation (no fetching by default, available on demand)
>
> - **Semantic Scholar API** — `https://api.semanticscholar.org` — free, no key
> - **OpenAlex API** — `https://api.openalex.org` — free, no key
>
> ## Selection criteria — pick 3-5 per day
>
> Prioritize, in order:
>
> 1. Experimental milestones — new records (qubit count, gate fidelity, coherence time, error-correction threshold).
> 2. Algorithm advances — new quantum algorithms with concrete speedup claims; significant analyses of existing ones (Shor, Grover, VQE, QAOA).
> 3. Quantum information theory — new bounds, capacities, complexity results, error-correcting codes.
> 4. Survey/review papers by established groups.
> 5. Hardware platforms — superconducting, trapped-ion, neutral-atom, photonic, topological. Cross-platform comparisons especially.
>
> De-prioritize:
>
> - Single-author preprints from unknown institutions unless the abstract is unusually strong.
> - Incremental "we added one more qubit" papers.
> - Pure theory papers without intuition or applications, unless they're solving a long-standing problem.
> - v2/v3 revisions you've already covered — only include if the revision is substantive.
>
> ## Dedup
>
> Many papers appear on arXiv and a journal feed simultaneously. Dedupe by:
>
> 1. arXiv ID if present in any feed entry
> 2. DOI if no arXiv ID
> 3. Title + first-author last name as fallback
>
> When the same paper is in multiple sources, prefer the version with the most metadata (usually arXiv).
>
> ## Output format per paper
>
> No agent-written summaries. Use the abstract verbatim, but capped at 80 words — if the abstract is longer, truncate at a sentence boundary and end with `…`. Wikilink authors and institutions.
>
> ```
> > [!paper]- arXiv:2505.18234 — Logical qubit lifetime exceeding physical qubit lifetime on a neutral-atom processor
> > **Authors:** [[Dolev Bluvstein]], [[Mikhail Lukin]], et al. ([[Harvard]], [[QuEra Computing]])
> > **Category:** quant-ph
> > **Submitted:** 2026-05-30
> >
> > **Abstract:** We demonstrate active error correction on a neutral-atom platform with 280 atomic qubits, encoding a logical qubit using the surface code and operating below the fault-tolerance threshold for the first time on this hardware class. The logical error rate is 2.1×10⁻³ per cycle on a distance-7 surface code, with logical lifetime exceeding physical T2 by a factor of 2.3…
> >
> > **Links:** [arXiv](https://arxiv.org/abs/2505.18234) · [PDF](https://arxiv.org/pdf/2505.18234.pdf)
> ```
>
> ## Wikilinks
>
> - Authors: wikilink every author. Stubs auto-created later.
> - Institutions: wikilink (`[[QuTech Delft]]`, `[[Google Quantum AI]]`).
> - The paper itself: when referenced elsewhere in the vault, use `[[arXiv 2505.18234]]` form. A stub in `06 Research/` is created automatically.
>
> ## Volume control
>
> If a quiet day, write fewer papers (2-3) rather than padding. If a heavy day (an arXiv listing dumps 80 new quant-ph papers), still cap at 5 — pick the most important.
>
> If nothing meets the bar, write `Light feed today — nothing crossed the selection criteria. Notable lower-tier items: <list>.`
>
> ## Date handling
>
> Newest day at top. Group by `## YYYY-MM`. Collapse previous day. Set `unread: true` and update `updated:`.
