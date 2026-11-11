# Loop Engineering with LangChain Deep Agents

**Student ID:** 25125067  
**Course:** DeepLearning.AI — Loop Engineering with LangChain Deep Agents  
**Working date:** 11 November 2026

These notes cover the code labs and the concepts used to explain their results.
The videos were skipped at the student's request. Running a lab is recorded
separately from the platform's graded assignments and certificate status.

## 1. Overview: what each loop controls

| Loop | Repeated operation | Feedback | Stopping condition |
| --- | --- | --- | --- |
| Agent | Model selects a tool, tool executes, result returns to model | Tool result or error | No next tool call, or model-call limit |
| Verification | Produce report, grade against rubric, revise failed parts | Explicit criteria and grader explanation | Rubric passes, or revision limit |
| Event-driven | An external event starts a fresh analysis | Ticket/page state and the event payload | That event's run ends; wait for another event |
| Learning / hill-climbing | Inspect a batch, propose an instruction change, rerun the same batch | Recurring failures and before/after measurements | Accept a measured improvement or reject the proposal |

An agent loop completes a task. The other loops decide whether the result is
good enough, when to start another task, or how to improve future runs.

## 2. L2 — Deep Agent Primer

`FilesystemBackend(root_dir=..., virtual_mode=True)` gives the agent a virtual
filesystem rooted at the course workspace. The path `/poems/haiku.md` refers to
a file inside that workspace. This confines the built-in file tools; it should
not be described as an operating-system sandbox for arbitrary Python code.

The three instruction mechanisms serve different purposes:

| Mechanism | Loaded when | Example |
| --- | --- | --- |
| `system_prompt` | Each model run | Point to the poet's instructions |
| `memory=["/memories/AGENTS.md"]` | At the beginning of a run | Always-applicable role and rules |
| `skills=["/skills/"]` | Short descriptions first; full skill when read | Haiku, limerick, sonnet, acrostic |

This is progressive disclosure: a large skill library does not need to place
every full instruction in the initial prompt. The trace reveals which files
the agent actually read.

**Observed run:** the poet read the four `SKILL.md` files, then wrote separate
haiku, limerick, sonnet, and BOSTON acrostic files. The completed notebook stores
the tool-call list and rendered poems. Its five code cells executed without a
notebook error. `ModelCallLimitMiddleware` caps the run at 30 model calls.

Useful extensions are to request only one form, change one form's rules, or add
a new skill and rebuild the agent. These are optional experiments; their code
must not be mistaken for an experiment that was actually run.

## 3. L3 — Agent Loop

The requirement is deliberately incomplete: users can upload files to their
profile; files should be stored securely; common file types should be supported.
The agent has to distinguish stated facts from questions and assumptions.

The instruction file specifies a procedure: fetch the ticket, write the report
skeleton, then fill Ambiguities, Clarification Questions, Assumptions, and
Summary. Narrow tools make each operation easier to inspect. The prompt asks
for this order, but an instruction alone does not enforce it; check the trace.

**Observed run:** the live execution used `openai:gpt-5.4-mini` in the course
environment and took 9 model turns / 17 trace steps. The report contained:

| Section | Result |
| --- | --- |
| Confirmed Facts | 4 bullets |
| Ambiguities | 3 bullets |
| Clarification Questions | 4 bullets |
| Assumptions | 3 bullets |
| Summary | 35 words |

An `edit_file` call failed because the string for the Assumptions heading matched
twice. The agent read the file and made a more specific edit, then completed the
report. This illustrates why feedback must return to the model. Blindly
retrying a permanent argument error is different from retrying a transient
network error.

The report asks for file-size/count limits, an explicit type allowlist, permitted
user roles, and concrete storage-security requirements. These are clarifying
questions, not facts supplied by the requirement.

Reducing `MAX_TURNS` to 4 is a useful budget experiment: it can stop the run
before the six-stage report is complete. A bounded run is not necessarily a
successful run.

## 4. L4 — Verification Loop

A model saying it is done does not establish report quality. The verification
loop gives a grader the report, read-only file access, and a rubric. The grader
reports which criteria pass and gives actionable feedback for failed criteria.
The worker revises, then the report is graded again.

Separate the worker's task from the grader's role. The roles can use the same
model ID, but they have different instructions and inputs. This separation
helps reviewability; it does not guarantee the grader is independent or correct.

Keep the rubric concrete. For example, an ambiguity should quote the original
clause and explain what decision cannot be implemented without clarification.
More bullets are not automatically better analysis. A stricter rubric adds
model calls and may require more revisions.

The notebook caps rubric iterations at three and model turns at forty. If those
limits are reached, retain the failure status instead of describing the report
as verified.

**Observed run:** all seven code cells completed with live calls. The report
reached `satisfied` after one grading pass. This run did not need a revision;
the three-pass limit is a maximum, not the number of passes observed.

## 5. L5 — Event-Driven Loop

The supplied Flask application simulates Jira and Confluence; it does not need
an Atlassian account. A ticket or a change to its linked requirement triggers
the same review-and-verification process from L3/L4.

The requirement page remains the source of truth. The agent writes a separate
analysis page, with version history linking it to the ticket and requirement
version. Comparing reports should include both the text diff and verification
status: two reports can have equal bullet counts but different content.

The automation can mark analysis ready, but a human decides whether the ticket
is Done. For a production integration, also consider event deduplication,
idempotency, obsolete requirement versions, failure handling, and retry limits.
The course's local simulation is not a deployed Jira/Confluence integration.

**Observed run:** `event_practice.py` sent two events through Flask's test
client: an initial review of `REQ-104`, then a requirement edit adding a 20 MB
file-size limit. The edit automatically triggered a new analysis. Requirement
versions and report versions were both `[1, 2]`; both reports were `satisfied`.
The final ticket remained `Analysis Ready`, with `human_marked_done=false`.
The completed practice notebook has three executed code cells and no errors.

## 6. L6 — Learning / Hill-Climbing Loop

Verification repairs one report. The learning loop looks across several reports
to discover a recurring problem, proposes one change to the shared instructions,
and compares the same five requirement documents before and after the change.

The analyst can read the evidence and write a proposal, but cannot rewrite its
own evidence. The deterministic `apply_change` function applies the proposed
text outside the reviewer. Save the exact instruction snapshot used for each
batch so that the comparison is reproducible.

**Correction made to the runner:** the original live rerun points at the bundled
`run_history/v2/AGENTS.md`. That can measure the instructor's pre-existing v2
instead of the proposal just produced in the current run. The runner saves
`improved` to `run_history/v2_live/AGENTS.md` and passes that exact file into the
new batch. The completed L6 notebook contains the correction too.

The bundled v1/v2 history is reference evidence from the course. Its apparent
improvement is not a measurement from this student's new run. Results from new
live runs are stored under the `v1_live` and `v2_live` labels and reported
separately.

Five documents are a small sample. Reusing the same documents is useful for a
controlled comparison, but it is not a held-out generalization test. Improving
rubric scores also does not establish that the rubric covers every real need.

**Observed live comparison (five documents per batch):**

| First-attempt criterion | v1_live | v2_live |
| --- | --- | --- |
| Completeness | 5/5 (100%) | 5/5 (100%) |
| Clarity | 1/5 (20%) | 5/5 (100%) |
| Depth | 1/5 (20%) | 5/5 (100%) |
| Reports needing revision | 4 | 0 |

The proposed change required each ambiguity to include `Reason:`,
`Resolved by:`, and `Edge case:` lines. The analyst used
`openai:gpt-5.5`; the worker used `openai:gpt-5.4-mini`. L6's twelve code cells
completed without notebook errors. The JSON receipt and `run_history/*_live`
files retain the underlying measurements, proposals, and reports.

## 7. Sources

- [Course and lesson workspace](https://learn.deeplearning.ai/courses/loop-engineering-with-langchain-deep-agents/lesson/mosoyz/deep-agent-primer)
- The downloaded course notebooks, Python helpers, instruction files, rubrics,
  and reference trace files in `02_Source_Code`.
