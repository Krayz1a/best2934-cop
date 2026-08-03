# ספר הפרומפטים — Prompt Engineering Log

**Project** `best2934-cop` · **Guidelines** §8.3 · **Version** 1.00

How this project was built with an AI coding assistant: the prompts that mattered,
what came back, where the first answer was wrong, and what we would do
differently. The entries are ordered as the work happened.

A note on honesty: several entries below record the assistant producing something
plausible and wrong. Those are the useful entries. A prompt log that only shows
successes teaches nothing about working with a model.

---

## 1. Working method

| Practice | Why it earned its place |
|---|---|
| Give the model the source of truth, not a summary of it | We downloaded the booklet and the grading guidelines and pointed the model at the files. Summarised requirements produced confidently wrong parameter values |
| Ask for the *reasoning* in the code, not just the code | Every module docstring explains why, not what. This is what made ADR-004 and ADR-005 findable later |
| Make the model test its own claim | "Prove the lie detector works" found a bug that "write a lie detector" had produced and hidden |
| Measure alternatives instead of arguing about them | The heading reader was chosen by running three implementations against ground truth, not by reasoning about which sounded better |
| Re-run the gates every time | `pytest` + `ruff` + the file-size checker after each change, so a regression is attributable to one edit |
| Never hand the model a credential | It writes the OAuth code and the setup guide; a human runs the consent flow |

---

## 2. Prompt log

### P-1 · Establish ground truth

> **Context** Starting the project. The course booklet and the software
> guidelines are PDFs behind a Moodle login.
>
> **Prompt** *"Find and download the grading guidelines for the final project.
> Grading is explicitly based on that file — I don't want to work from my
> memory of it."*
>
> **Outcome** The direct file URL was not in the page HTML; an in-page
> credentialed fetch of `/mod/resource/view.php?id=…&redirect=1` returned the
> PDF bytes. Extracted to text and read in full.
>
> **Lesson** Worth the detour. Working from the actual document produced the
> 150-line file limit, the 85% coverage gate and the uv-only requirement — three
> hard constraints that would each have caused a late rewrite if discovered
> after the code was written.

### P-2 · Model the game before coding it

> **Prompt** *"Before any code: model this as a Dec-POMDP. Give me the tuple
> ⟨I, S, {Aᵢ}, T, R, {Ωᵢ}, O, h⟩ filled in with this project's actual values,
> and say explicitly which parts each agent can and cannot observe."*
>
> **Outcome** The formalisation in [PRD.md](PRD.md) §1.3. Its real value was the
> observation row: writing out Ωᵢ made it obvious that the four channels differ
> in forgeability, which is the distinction the whole belief design rests on.
>
> **Lesson** Asking for a formalism first is cheap and it constrains everything
> downstream. The "what can each agent NOT see" clause did more work than the
> rest of the prompt combined.

### P-3 · Enforce the epistemic constraint structurally

> **Prompt** *"Build `OwnState`. Hard requirement: there must be no attribute
> anywhere holding the opponent's true position. Not private, not underscore —
> absent. If a later feature seems to need it, that feature is wrong."*
>
> **Outcome** `OwnState` has `position`, `belief`, `my_scent`, `opponent_scent`
> — and no opponent position. Rules 8 and 9 are then satisfied by construction:
> there is no code path through which an objective board could reach a renderer,
> because no renderer accepts one.
>
> **Lesson** "Make it impossible" beats "remember not to". Phrasing a constraint
> as an absent attribute rather than a rule to follow made every later feature
> automatically compliant.

### P-4 · Reproduce a printed figure exactly

> **Prompt** *"The booklet prints a 5×5 pheromone kernel in Figure 4. Implement
> it, and separately implement a Gaussian that approximates it. Tell me exactly
> where they differ — I don't want 'close enough'."*
>
> **Outcome** σ² = 4/3 reproduces the table except on four cells
> `{(1,1),(1,3),(3,1),(3,3)}`, where it reads 0.43 against 0.42.
>
> **Iteration** The first test used `abs(diff) < 0.01` and failed at
> `0.010000000000000009` — floating point. Rather than widen the tolerance we
> rewrote the test to pin the exact differing cells and the exact gap, which is
> a strictly stronger claim and cannot drift.
>
> **Lesson** A failing tolerance test is often an invitation to make a sharper
> assertion, not a looser one.

### P-5 · Restructure for the guidelines

> **Prompt** *"Bring the whole tree into compliance with the guidelines: every
> file ≤150 code lines, an SDK layer nothing bypasses, uv only, zero ruff
> violations. Write the file-size checker as a tool so it's a gate, not a
> promise."*
>
> **Outcome** 71 files, largest 148 code lines; `P2PChaseSDK` as the single entry
> point; `tools/check_file_size.py` excluding blanks, comments and docstrings.
>
> **Iteration** 55 ruff violations on the first pass — single-letter module
> aliases (`K`, `C`, `A`), exceptions not ending in `Error`, `(str, Enum)`
> instead of `StrEnum`. All mechanical. One was not: `geometry.delta("NE")`
> raised a bare `KeyError`, a genuine bug the linter surfaced by accident. Fixed
> to raise `IllegalMoveError` naming the permanent move set.
>
> **Lesson** The 150-line limit felt arbitrary and turned out to be the single
> most useful constraint in the project. It forced `smell.py`, `belief.py` and
> `gatekeeper.py` apart into modules that each do one thing, and made the later
> deception fix a change to three small files rather than surgery on a large one.

### P-6 · Make the model challenge itself

> **Prompt** *"Write an integration test that forces the cop's trust in a lying
> thief to collapse. If it doesn't collapse, don't adjust the test — find out
> why."*
>
> **Outcome** It didn't collapse. Trust sat at 0.9 — the ceiling — with
> `hints_contradicted == 0` while the thief lied on every single turn.
>
> The cause: `play_half_turn` cross-examined the opponent's revealed **move**.
> The move is sealed in the commitment and therefore always truthful, so the
> check could only ever confirm honesty. The `intent = lie` flag marked the hint
> as misleading and nothing ever read the hint. The verbal channel was
> decoration, and every test had passed.
>
> **Lesson** This is the single most valuable prompt in the log. "Write a lie
> detector" produced code that looked right. "Prove the lie detector works, and
> if it doesn't, debug the code not the test" produced the truth. The second
> instruction — don't adjust the test — is what stopped the easy wrong fix.

### P-7 · Measure instead of reasoning

> **Prompt** *"The claim needs something physical to check against. Don't pick a
> method — implement the candidates, run them against ground truth in a real
> match, and show me the agreement rates."*
>
> **Outcome** A throwaway probe script printed, per turn, the true heading beside
> each candidate reader's answer:
>
> | Reader | Agreement (moving turns) |
> |---|---|
> | Half-plane scent mass around the peak | ~50%, sometimes outvoted by the wrong direction |
> | Peak-cell displacement | Integer jumps: "nothing" for turns, then "impossible" |
> | Sub-cell centroid drift | **~80%** |
>
> **Lesson** The centroid reader was not the one we would have argued for — it
> looked like the noisiest. Fifteen minutes of measurement beat an hour of
> reasoning. The rejected alternatives are now ADR-006, which is more useful
> documentation than a bare statement of what we chose.

### P-8 · Follow the bug to its root

> **Prompt** *"Now that the hint is decoded, the liar still isn't punished
> enough. Check whether `update_from_hint` actually does anything."*
>
> **Outcome** It did not. It built the set of cells "consistent with north" and
> boosted them while damping the rest — but after a few turns of diffusion almost
> every cell has a northern neighbour, so the claimed set covered the board and
> the boost and damp cancelled out.
>
> Replaced with *transport*: with trust `t`, a fraction `t` of every cell's mass
> steps in the claimed direction and `1 − t` stays. A directional claim is
> evidence about how the cloud moved, not about which cell is occupied.
>
> **Lesson** Two independent no-ops, stacked. Neither was visible in unit tests
> because each was individually "correct" — the bug was in what they *meant*
> together. Integration tests that assert an outcome, not a call, are what found
> it.

### P-9 · Fix the diagnostic that couldn't diagnose

> **Prompt** *"Write a CLI test where `check-config` is given an illegal
> Appendix F value."*
>
> **Outcome** It crashed with a traceback instead of reporting the problem: the
> loader is strict by default, so it raised before `check_config` could print the
> diagnosis it exists to produce. Fixed to load non-strictly — every other
> command still refuses to start on an illegal config.
>
> **Lesson** Writing the test surfaced a UX bug nobody would have found by
> reading the code, because the code was individually reasonable at every line.

### P-10 · Ask for the honest limitation

> **Prompt** *"The honest opponent only reaches 0.59 trust, not the 0.9 ceiling.
> Is that a bug or a property? Don't tune it away until you can tell me which."*
>
> **Outcome** A property. The drift reader is ~80% accurate, so an honest
> opponent is falsely contradicted ~20% of the time and trust converges near
> 0.6. Tuning the learning rate to hide this would have made the estimator
> overconfident about a measurement that genuinely is noisy.
>
> Documented as a limitation in [PRD_belief_map.md](PRD_belief_map.md) §5 rather
> than papered over.
>
> **Lesson** "Is this a bug or a property, and how do you know?" is a better
> prompt than "fix this number". The number was right; our expectation was wrong.

---

## 3. Prompt patterns that worked

| Pattern | Example |
|---|---|
| **Falsify, don't confirm** | "Write a test that forces X to fail. If it doesn't fail, debug the code." |
| **Forbid the escape hatch** | "Don't adjust the test." / "Don't tune it away until you can tell me which." |
| **Measure the alternatives** | "Implement the candidates and show me the agreement rates." |
| **Constrain structurally** | "There must be no attribute holding that value. Not private — absent." |
| **Demand the source** | "Find the actual grading document. I don't want to work from memory." |
| **Ask for the limitation** | "What's the honest weakness here?" |

## 4. Prompt patterns that failed

| Anti-pattern | What went wrong |
|---|---|
| "Implement the lie detection mechanism" | Produced plausible code that provably did nothing. Passed every test |
| "Make the tolerance pass" | Would have hidden a floating-point artifact behind a looser assertion |
| "Just make the tests green" | Twice this would have meant editing a test that was correctly failing |
| Describing the rules from memory | Produced wrong Appendix F values; fixed only after fetching the real document |
| Asking for a large module in one prompt | Fought the 150-line limit. Asking per-responsibility produced files that were naturally small |

---

## 5. What we would do differently

1. **Fetch the grading document before writing a line.** We did it second. Doing
   it first would have avoided one full restructuring pass.
2. **Write the falsification test alongside each mechanism, not after.** The
   deception bug survived several commits because the test that could catch it
   was written last.
3. **Probe before choosing.** The measurement in P-7 took fifteen minutes and
   overturned the intuitive choice. It should have been the default habit, not a
   step we reached after being burned.
4. **Treat "all tests pass" as weak evidence.** Two of the three real bugs in
   this project were found by tests that did not exist yet, and were invisible to
   every test that did.
