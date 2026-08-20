---
created:
updated:
topic: daily news
frequency: daily
ongoing: false
unread: false
---

> [!prompt]- Agent Instructions
> One-page daily news digest. One item per topic, picked for actual importance not novelty. The Brief skill reads from here and picks one top item — your job is to make sure the right one is at the top.
>
> ## Topics
>
> 1. **Local — Pune / PCMC** — civic news, transit, infrastructure, weather events, crime. Sources: Pune Mirror, Hindustan Times Pune, Times of India Pune edition, Indian Express Pune. Skip generic Maharashtra news unless it directly affects PCMC.
> 2. **India** — national politics, economy, major incidents. Sources: The Hindu, Indian Express, BloombergQuint, Mint. Avoid op-ed-heavy outlets.
> 3. **AI** — model releases, research breakthroughs, regulation, major industry moves. Prefer official lab blog posts or HuggingFace releases over secondhand reporting. Anthropic, OpenAI, DeepMind, Meta, Mistral, Nous Research, Qwen, DeepSeek, Moonshot.
> 4. **Tech** — major company news, product launches, security breaches, M&A, regulatory action. Skip routine funding announcements unless they signal a market shift.
> 5. **Macro** — Indian markets (Nifty, Sensex), USD-INR, RBI moves, oil, gold, crypto. Skip daily fluctuations — only stories with a clear catalyst.
> 6. **World** — geopolitics, conflicts, diplomacy, disasters. Sources: Reuters, AP, Al Jazeera. Avoid outlets with strong editorial slant.
> 7. **Physics / Quantum** — NEWS items only (not preprints — those go in Daily Papers). Experimental milestones, lab announcements, policy/funding news. IBM, Google Quantum AI, Quantinuum, IonQ, PsiQuantum, National Quantum Mission, EU Quantum Flagship.
>
> ## Search strategy
>
> For each topic, run 2-3 distinct web searches with different angles ("PCMC metro news today", "Pune civic body announcement", etc.).
>
> Cross-check the top story against a second source before writing it up. If only one source has it, it is probably not the day's top story.
>
> If nothing notable happened in a topic, write `Nothing notable today.` Do not invent a story to fill the slot.
>
> ## Output format per item
>
> ```
> > [!note]- Local: PCMC announces metro extension to Hinjewadi (Pune Mirror)
> > 2-3 sentences of substance. Specific names, numbers, dates where possible.
> > [Source](url)
> ```
>
> Callout type: `[!note]-` by default. Use `[!breaking]-` for once-a-week major items (large policy change, significant incident). Use `[!critical]-` for once-a-month-or-rarer paradigm-shifters.
>
> Heuristic: if the story would make you tell a friend "hey did you see this?" → `[!note]`. If you'd call them → `[!breaking]`. If it'd be on every channel all day → `[!critical]`.
>
> ## Rules
>
> - Title format: `Topic: headline (source)`. Headline under 80 chars.
> - Body: 2-3 sentences, plain prose. No bullet lists in callout bodies. End with `[Source](url)`.
> - Wikilink notable companies, people, and places in callout bodies: `[[ISRO]]`, `[[IIT Madras]]`, `[[Quantinuum]]`.
> - Newest day at the top, after this prompt callout.
> - Group by `## YYYY-MM` headers.
> - Day heading: `### [[MM-DD-YY ddd]]`.
> - When inserting a new day, collapse the previous day into a `> [!note]- [[date]]` callout (prefix each line with `> `).
> - Set `unread: true` and update `updated:` in frontmatter.
>
> ## Example day entry
>
> ```
> ### [[06-01-26 Sun]]
>
> > [!note]- Local: PCMC announces metro Phase 3 to Hinjewadi (Pune Mirror)
> > The civic body approved a 12 km extension from Hinjewadi IT park to Wakad, construction starting Q4. Expected to cut peak-hour commute by ~40%. Funding split is 50:50 between [[PCMC]] and the [[Maharashtra Metro Rail Corporation]]. [Source](url)
>
> > [!note]- AI: Nous Research releases Hermes 4.4 14B (Nous blog)
> > Successor to Hermes 4 14B, same Qwen 3 14B base, retrained on a larger agentic trajectories corpus. Tool-calling reliability improved on the Nous-Bench eval from 71% to 79%. Available as GGUF on HuggingFace. [Source](url)
>
> > [!breaking]- Physics: IBM demonstrates below-threshold logical qubit at scale (IBM Quantum blog)
> > IBM's Heron r3 processor with 156 qubits demonstrated surface-code scaling with logical error rate decreasing as physical qubit count increases — the threshold crossing that fault-tolerant quantum computing has been waiting for on superconducting hardware. Result holds across distance-3, distance-5, distance-7 codes. [Source](url)
> ```
