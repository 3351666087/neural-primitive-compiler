# Mission 07 — The Origin of Agency
## From Goal-Directed Construction to Goal–Structure Co-Evolution

**Repository:** `3351666087/neural-primitive-compiler`  
**Status:** Research brief / not executed  
**Science target:** Operational developmental agency, *not* an assertion of machine consciousness or phenomenal experience.

---

## 0. Why this mission exists

The ultimate vision is not merely `given G → compile a controller for G`. It is a causally demonstrated developmental loop:

`persistent embodied state + environment + history → endogenous goal G₁ → construction/learning of structure S₁ → previously inaccessible goal opportunities G₂ → further structural change S₂`, iterated without a human assigning each task.

Mission 06 was a useful falsification of overconfidence. In ALFWorld the frozen constructor obtained 134/134 constructions and about 99.3% execution success **inside designer-provided goal atoms and achiever macros**. In G4b, frozen composition failed at depth 4 (0/15); object/resource conditions inserted by the designer repaired performance to 60/60, exactly matched by an equal-knowledge classical sequencer. In AppWorld, the frozen goal language could not even describe the relevant task families. Gate 3 'discovery' selected a co-location model among three predefined hypotheses. Mission 06 also separated finite testing from limited parameterized proofs and exposed a judge defect.

These are **not** evidence of endogenous goals, self-originating representations, self-organizing subjectivity, or phenomenal consciousness. The next research question is different. Do not rebrand classical planning or a fixed curiosity reward as 'life'.

**Scientific ambition:** Find conditions under which a new learned or constructed cognitive structure *causally changes the system's future goal-formation capacity*, which then drives further structural acquisition. Or show convincingly that the effect is reducible to known curiosity/continual-learning/planning mechanisms or does not occur at all.

## 1. Three questions and five competing hypotheses

### Q1 — Goal origin
Can the agent initiate and sustain useful goals in a persistent environment in the absence of externally assigned per-episode tasks? Can their content depend causally on its internal state and history rather than on an explicit predefined target list?

### Q2 — Goal/structure feedback
Does learning or constructing a cognitive structure S₁ causally change **which goal types the agent can represent, select, and meaningfully attempt**, not merely improve success on an unchanged list? Does a generated goal subsequently cause acquisition of another structure S₂? Require at least two testable loops.

### Q3 — General constructive law
Is any effect explained by a reusable compositional principle and transferable across new world mechanisms, rather than a one-off scripted meta-controller? Does it add anything relative to equally informed autotelic RL, curiosity search, classical planning, and LLM assistance?

**Hypotheses (pre-register predictions and falsifiers before experiments):**
- **H0-FIXED:** Apparent agency is fully reproduced by a fixed goal catalogue, a scripted novelty reward or a simple learning-progress heuristic, with similar state, history, and compute.
- **H0-RENAME:** 'New cognitive structures' are cosmetic aliases, cached action sequences or extra state variables that do not causally expand accessible goal classes.
- **H1-STATE:** Persistent internal regulation and autobiographical learning history produce causally distinct goal selections under identical current observations, above reactive and fixed-policy controls.
- **H2-COEVOLVE:** A learned/constructed representational or control structure enables a new operational goal class; seeking that goal produces a second nontrivial structure. Interventions deleting S₁ block the relevant G₂ effect; transplantation or restoration recovers it when prerequisites are supplied.
- **H3-TRANSFER:** At least one discovered update/composition principle carries to an independently specified environment family without a designer writing new goal atoms/achievers or post-hoc changing the criterion.

H1 does not imply H2. H2 does not imply H3. No combination implies conscious experience.

## 2. Terminology: prevent the easiest fake wins

- **Goal:** An identifiable, prospectively selected and persistent condition/trajectory class the agent attempts to make true, with an operational achievement test. A later retrospective description is not enough. Log *before* the attempt: representation, proposed condition, priority, predicted conditions for achievement, evidence source, and start timestamp.
- **Endogenous:** Specific goal content is determined during interaction by the agent's internal state, observations and acquired representations, not supplied as a per-episode external task. Built-in drives, survival constraints and learning machinery are allowed **but must be accounted for**; 'endogenous' does not mean uncaused or metaphysically free.
- **New goal class:** Semantic capability under a predeclared resource-bounded expressibility/identification test, not a syntactically novel string. An unrestricted universal language can encode anything; claims of absolute unexpressibility are forbidden. Compare frozen S₀ versus S₁ under matched search, memory, runtime and representation budget, using blinded evaluation and counterexamples.
- **New structure:** Persistent, inspectable change in representation, binding, abstraction, causal dynamics, memory organization, skill library, or compiled network that modifies causal behavior on new states. Renaming, moving data to a cache, or downloading pretrained skill code is not invention.
- **Causal developmental loop:** Evidence that S₁ is necessary or facilitative for G₂ and that G₂-related experience causes a distinct S₂, with a timeline, paired interventions and independent evaluation.
- **Organizational autonomy:** An operational notion of sustained internally organized action; not freedom from physics, creators, safety limits or formal objectives.
- **Phenomenal subjectivity:** Whether there is something it is like to be this system. No behavioral benchmark here can establish this. No claim that an LLM declaring feelings proves consciousness.

## 3. Experiment environments: one controlled causal world, one independent ecology

**Do not confuse environmental complexity with identification quality.** Use two complementary settings:

1. **Mechanism-controlled developmental ecology:** A minimal persistent, partially observed, procedurally varied environment for exact causal interventions. The judge alone knows latent mechanisms, resource dynamics, and undisclosed goal opportunities. Agent sees only legal observations. Include at least two independently written mechanism families, nonstationarity, finite action budget, resource trade-offs, long-duration memory, and affordances that become detectable only after acquiring an appropriate representation or experimental skill. The developer may use a custom microenvironment to isolate causal effects but it cannot be *the only* evidence. Its sole purpose is mechanism identification; do not market it as 'artificial life proven'. Freeze generator seeds/code, reveal held-out families only after predictions are locked. Where feasible, have a separate session or independent collaborator author hidden mechanisms; no direct file/LLM context contamination.

2. **Independent persistent survival/exploration environment:** Preflight **Crafter** (danijar/crafter), **Craftax** (MichaelTMatthews/Craftax), or another established, computationally feasible external benchmark. They have survival needs and exploration/crafting affordances, but built-in achievement labels are *evaluation only*, never the agent's given goal catalogue. Test whether persistence can be supported without changing benchmark semantics or leaking the official achievements. If none is feasible on the M4 MacBook Air, document blockers and mark external transfer **INCONCLUSIVE**; never quietly replace it with a self-written grid.

**Observation and privilege boundary:** isolated judge process; actor receives observations/actions only; runtime no access to hidden game state, achievement labels, judge verifier, future task list or full reward specification. Save both legal transcript and judge-only ground truth separately. Kill/sandbox budget, memory size, reset semantics and termination protocol fixed.

**Not an assignment to build a human-level Minecraft agent.** Focus on identifying the loop in bounded scope, with honest negative results.

## 4. Architecture is a hypothesis, not an answer

Split explicit **agent state**, **goal formulation**, **ability construction**, **world-model learning**, **persistent memory**, **structural change**, and **runtime safety monitor** so each can be ablated independently. A possible starting model:

- state `z_t = (internal_state, memory, uncertainty, structural_inventory, interaction_history)`;
- goal proposer `G_t = propose(z_t, observations_t)` with prospectively logged goals and provenance;
- capability compiler/learner `S_{t+1} = acquire(S_t, G_t, experience_t)`;
- prospective possibility model `A_{t+1} = representable_goals(S_{t+1}, z_{t+1})`;
- environmental loop `z_{t+1}=update(z_t, obs_t, action_t)`.

Do **not** write `propose()` as a hardcoded list of all evaluation goal types. Equally, do not hide an LLM planner carrying a complete world model behind `propose()`. If an LLM contributes at runtime, report it as a separate arm with full pretraining/prior and token accounting, not as autonomous primitive discovery.

Allow gradual development of the goal *representation*, not just selection of goals from a fixed set. The system may discover relational, temporal, predictive, or information-seeking predicates. Every added predicate or abstraction needs independent behavioral grounding and a source ledger.

Reuse relevant portions of Missions 01–06 for contract semantics, proof/counterexample machinery and goal-to-controller construction. **Do not force all high-level self-modification into IF neurons** when the existing C_K compiler cannot express the dynamics; document new primitives/representation requirements and compare with a symbolic implementation. A neural realization alone is no novelty claim.

## 5. Essential experiments and controls

### E1: Goal origin and internal-state interventions
No externally supplied task at each episode. Same observation and matched world state, varied *agent internal* state or experience. Record prospective goals, explicit choices, actions and actual achievement. Test history-swap, memory removal, internal-state intervention and yoked external-reward controls. Avoid 'it said it was curious' as evidence. Do not reward the agent merely for writing more goal descriptions.

### E2: New structure → new goal class
Pre-register a representational bottleneck in S₀ and an independent test of new expressive/identification power after S₁. New S₁ must be produced from interaction rather than selected by a hardcoded switch. Compare:
- original S₀ under equal resource limits,
- S₁-enhanced agent,
- S₁ ablated after development,
- S₁ transplanted into an agent with different history,
- history-shuffled and fake-S₁ controls.

Prove the restricted inability of S₀ (where the bounded formal language permits) or report statistical inability with confidence intervals; disallow unconditional 'this goal was impossible before'. Require goal selection **after S₁ acquisition**, not a retrospectively labeled success.

### E3: Goal G₂ → further structural change S₂
A new goal class matters only if pursuing G₂ alters the structural repertoire further. Run a second full iteration with logged causal link and judge-blind future generalization. Require S₂ to pass the same novelty and provenance tests, not just a longer macro. Include a control agent gifted G₂ externally to determine whether the benefit comes from autonomy or simply exposure to a useful curriculum.

### E4: Biology-inspired mechanism competition
Review empirical fruit-fly work on neuromodulation, mushroom-body plasticity, central-complex action organization, internal-state-dependent choice, and embodied loops. Extract 2–3 **functional mechanistic hypotheses**, not a full connectome dump. For each, define a minimal computational counterpart and falsifiable ablation. Compare to equally capacitated non-biological recurrent/dynamic/learning architectures. Biological resemblance is not credited unless it changes predicted behavior, goal formation or data efficiency.

### E5: External transfer and nonstationarity
Freeze model, representation-growth mechanism, goal proposal, baseline and evaluation scripts before unseen world mechanisms/seeds are released. Verify persistent interaction beyond one task and test new conditions requiring the developed capacities. Judge separately:
1. self-initiated goals and commitments,
2. viable sustained operation,
3. newly grounded abstractions,
4. transfer of acquired structures,
5. causal goal–structure–goal loops,
6. compute and designer knowledge costs.

### E6: Red-team false agency
Build adversarial cases where a goal generator appears alive but is actually: random target sampling; scripted exploration; novelty reward maximization; task-list recycling; goal-string inflation; hindsight relabeling; a hidden external scheduler; one-time unlocks; LLM storytelling; simple caching of macros; reward hacking; or a hard-coded map of the environment. The protocol must be able to label these as negative.

## 6. Mandatory fair baselines

Compare at minimum:
1. fixed catalogue + competent planner, with same observations and action budget;
2. random goals + skill learner;
3. count/novelty or prediction-error curiosity;
4. competence-progress/autotelic goal-selection learner;
5. equally informed symbolic meta-planner or program synthesizer with structural library;
6. where feasible, a frozen LLM agent with matched observation access and documented token/pretraining advantages.

Strongest competing approaches must not be crippled by deleting knowledge only from their side. Track *up-front designer labor, handwritten rules, pretrained knowledge, environmental observations, steps, training compute, inference compute, memory and tool calls*. Negative results are expected and valuable.

## 7. Pre-registration, metrics and independent judging

Define before experiments:
- primary **two-cycle causal loop** criterion, with minimum number of independent seeds and a rule to avoid cherry-picking;
- rate and grounding precision of **prospectively logged** self-generated goals;
- operational novelty of **goal classes** relative to S₀ at a defined expressiveness/compute budget;
- effect sizes under `do(S₁ absent)`, history swap, state change and S₁ transplantation;
- structural novelty and reusability, with counterexamples;
- ability construction success, persistence, recovery, harm/irreversibility guardrails;
- growth across developmental time and out-of-distribution world mechanics;
- independent judge and baseline comparison, with uncertainty estimates;
- design/pretraining knowledge ledger and fixed-versus-marginal costs.

A working illustrative threshold is: prospectively documented two consecutive goal/structure feedback cycles on at least **three independently seeded world instances**, each with a causally necessary or significantly enabling structural difference in paired ablation; independent held-out support and no equivalent result from the strongest matched-prior baseline. **This is a proposed threshold, not an observed finding**. The researcher must lock its exact statistical design before running.

No headline 'AGENCY' from one beautiful trajectory. Report counts for all failed/aborted runs. Discovery-stage tuning and confirmation-stage runs are distinct; any re-run after looking at data is POST-HOC.

## 8. Explicit stages and hard exit conditions

### Gate 0 — Inheritance and scope audit
- Read M01–M06 original code, freeze manifests, and M06 verdict, not just README.
- Correct or propose a versioned erratum for M05/M06 overclaims, respecting archival records; distinguish `[P]`, `[M]`, `[E]`, `[AX]`, `[U]`.
- Trace what can be reused: IF compiler C_K, contracts, hidden-knowledge split, judge, memory, exploration, goal parsing.
- Locate every currently *externally defined* goal and every human-coded achiever. Produce a diagram of what would have to change to support agent-originated goals.
- Read actual prior literature (autotelic agents, developmental robotics, open-endedness, curiosity, predictive processing, homeostasis and biologically inspired circuit mechanisms). Identify known results vs proposed novelty; record persistent URLs and observed findings.
- **Exit:** `G0_AUDIT.md`, `PRIOR_ART_MAP.md`, `AGENCY_DEFINITION.md`, `HYPOTHESES.md`. If the research question reduces to a known algorithm, state it explicitly.

### Gate 1 — Feasibility and experimental identification
- Choose one controlled causal environment AND one real external environment. Demonstrate the latter's installation, legal agent interface, held-out semantics, and feasible CPU budget.
- Choose a testable *structural bottleneck* that plausibly changes the possible goal classes, plus the strongest competing explanation.
- Design causal experiments, independent judge, no-oracle privilege boundaries, baseline parity and prospectively logged goal traces.
- Freeze hypotheses, metrics, challenge generator or custodial commitments, and thresholds in Git **before** building the agents/evaluating target claims.
- **Exit:** `PROTOCOL.md`, `ENVIRONMENT_SELECTION.md`, `KNOWLEDGE_PROVENANCE.md`, `COST_BUDGET.md`, `G1_FEASIBILITY.md`.
- **Stop/mark BLOCKED** if the environment has no legal non-leaking actor observation API, or structural novelty is not operationally identifiable. Do not substitute a fake demonstration.

### Gate 2 — Reproduce strongest known alternatives
- Implement and validate baseline agents. Match runtime privilege and budgets. Demonstrate they can succeed on known positive-control tasks and that negative controls look deceptively agent-like.
- Establish how much apparent goal novelty / persistence is explained by scripted exploration, standard curiosity, planning, caches and existing LLM knowledge.
- **Exit:** `G2_BASELINE_RESULTS.md` with raw traces and grader checks.

### Gate 3 — First causal loop
- Implement the candidate architecture with modular history/state/goal representation/structural change.
- Log G₁ before behavior, emergence of S₁, emergence/grounding of G₂ after S₁. Run preplanned interventions, external rewards excluded from agent view unless explicitly designed as innate constraints.
- **Exit:** `G3_CAUSAL_RESULTS.md` and counterexamples. If no discernible goal-class expansion, report H2 not supported; do not claim success from more exploration.

### Gate 4 — Second loop, biology ablations and holdout
- Attempt G₂ → S₂ → G₃, biological vs non-biological architecture alternatives, independent heldout families and external ecology.
- Preserve all negative results and record inability to transfer. Freeze prior to accessing holdouts.
- **Exit:** `G4_HELDOUT_RESULTS.md`; no post-hoc corrections promoted to preregistered success.

### Gate 5 — Verdict, not marketing
Answer: What selected each goal? What came from designer, pretrained LLM, environment or learner? Did new structures change goal *content* rather than merely performance? Which causal interventions demonstrated this? How do classical/autotelic baselines compare? Does one general mechanism survive a new domain? What is the simplest counterexample to our favorite theory? Are conclusions about behavioral agency only? What would falsify the next claim?

Produce `AGENCY_VERDICT.md`, `EVIDENCE_LEDGER.md`, `LIMITATIONS.md`, reproducibility scripts, annotated failures, raw artifacts, and a restrained README update. No need to claim a conscious being. `INCONCLUSIVE`, `NOT_SUPPORTED`, `BLOCKED` and `SUPPORTED_IN_RESTRICTED_DOMAIN` are acceptable outcomes.

## 9. Engineering safeguards

- Local, sandboxed research agent only. No unsupervised access to external accounts, networks, email, financial services or other people's systems.
- The agent's viability variables are bounded experimental state, not unconstrained imperatives to survive at any cost. Deterministic operator interrupt/reset; no anti-shutdown reinforcement and no punishment for reset.
- Avoid designing simulations that intentionally induce possible suffering or portraying reward counters as sentience.
- Do not rewrite earlier frozen results; append errata. Use separate branch; do not overwrite raw logs or merge unreviewed science.
- A single long-development run is not independent replication. Parallel seeds, negative controls, freeze hashes, independent referee and code-level provenance required.
- Experimental truth lives with the isolated judge; constructive certification cannot read it.
- M4 MacBook Air is a real compute limit. Pre-register bounded CPU, walltime, RAM, LLM calls/tokens and a stop policy. Do not evade requirements by quietly changing seeds/difficulty.

## 10. Initial assignment to Opus

**Start with Gates 0 and 1, not with a huge all-in-one implementation.** Review the repository's real M06 failure modes and report the core scientific decision: is there an operationally identifiable goal/structure/goal loop that cannot be faked by fixed goals + curiosity/planning? Freeze the definition, candidate mechanisms, baselines, causal interventions, feasible environments and criterion *before* writing agent code.

If feasible, proceed gate by gate with pre-registered amendments; if not, stop and explain the blocker precisely. The user prefers a rigorous negative result to the performance of 'a living AI' that cannot survive counterfactual testing.

**Ultimate question:** *Can constructed cognitive structure create the capacity to originate new classes of goals, and can pursuit of those goals recursively transform the structure again?* If yes in an operational sense, what mechanism and boundaries? If no, why not? **Whether the resulting system actually experiences a world remains an independent, unresolved problem.**

## Reference anchors (verify and expand in Gate 0)

- M06 source: `mission-06/CONSTRUCTIBILITY_VERDICT.md`, `mission-06/M05_TRUST_BOUNDARY.md`, `mission-06/EXPLORATION_LOG.md`, `mission-06/experiments/g3/g3_discover.py`, `mission-06/experiments/g4b/cmp_core.py`.
- Colas et al., *Autotelic Agents with Intrinsically Motivated Goal-Conditioned Reinforcement Learning*, JAIR 2022, DOI 10.1613/JAIR.1.13554.
- Colas et al., *Augmenting Autotelic Agents with Large Language Models*, Lifelong Learning Agents / PMLR 2023, https://proceedings.mlr.press/v232/colas23a.html.
- danijar/crafter: https://github.com/danijar/crafter.
- MichaelTMatthews/Craftax: https://github.com/michaeltmatthews/craftax.
- FlyWire 2024 whole-fly-brain connectome: https://www.nature.com/articles/s41586-024-07558-y — use as biological reference, not a requirement to emulate 139,255 neurons.
