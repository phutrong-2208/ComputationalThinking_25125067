# AI Usage Declaration

**Student ID:** 25125067  
**Submission:** 25125067_W04_01  
**Project:** ASTRA - AI Exam Generation and Verification Pipeline  
**Date:** 6 November 2026

## 1. Declaration and scope

I used AI assistance extensively during this week's work. This included iterative
"vibe coding," prompt-based development, detailed code review and debugging, and
support for writing the development report and correcting English grammar.

AI assistance was substantive: it contributed to implementation and report drafting,
not only spelling correction or code completion. This declaration was also drafted
with AI assistance.

## 2. Tools and purposes

| Tool or model | Purpose |
| --- | --- |
| Codex (OpenAI coding assistant) | Discuss requirements, plan the pipeline, generate and revise code, review implementation details, investigate failures, and assist with documentation and report writing. |
| Gemini API | Serve as the language-model provider used by the implemented exam-generation agents. A successful live workflow used Gemini 3.1 Flash-Lite, with some completed responses reused from saved checkpoints during debugging. |

The development assistant and the models called by the application had different
roles. Using Gemini inside ASTRA does not mean that Gemini authored all of the
submitted source code or report.

## 3. Prompt-based development and vibe coding

I provided requirements and constraints through prompts, inspected intermediate
outputs, and requested revisions when the behavior did not match the intended design.
The workflow followed repeated specification, implementation, review, and correction.

AI contributed substantially to the following work:

- Extending the single-agent baseline into Composer, Illustrator, Solver, and Reviewer agents.
- Implementing Python orchestration, typed data contracts, validation, and stage-specific data views.
- Generating native TikZ/PGFPlots figures and merging them with question content into LaTeX.
- Keeping Solver input separate from Composer's proposed answers and private reference material.
- Enforcing at most one Reviewer-to-Composer feedback, followed by human visual inspection.
- Writing tests, replay fixtures, benchmark utilities, and diagnostic reporting.
- Investigating provider errors and correcting schema, question-count, and formatting problems.

### Representative prompts

The examples below are English paraphrases of the requests used during development,
not verbatim conversation transcripts.

1. "Extend the baseline into a Composer -> Illustrator -> Solver -> Reviewer pipeline, with an orchestrator coordinating the agents."
2. "Make Illustrator generate editable TikZ/PGFPlots code instead of embedding a PNG as hexadecimal data in the LaTeX source."
3. "Let Solver solve the questions independently without receiving Composer's answer key."
4. "Reviewer may send feedback to Composer only once. After the correction, stop and let the user inspect the exam visually."
5. "Prepare a 30-question exam and validate its question-type and difficulty distributions."
6. "Review the implementation in detail, investigate the API and validation errors, and preserve useful diagnostics without exposing credentials."
7. "Help structure and draft the development report, and improve its English grammar, clarity, and consistency."

## 4. Detailed AI-assisted review

AI was used to review both code structure and observed behavior. The review covered
input validation, question counts, type and difficulty distributions, point totals,
figure references, and LaTeX formatting. It also examined artifact revisions and
hashes, information passed between agents, provider error reporting, call budgets,
and the single-feedback stopping rule.

Review and debugging led to concrete revisions, including more informative HTTP
errors, clearer count-validation feedback, code-managed identity/hash binding,
restrictions on unrequested illustrations, and support for requesting a correction
when Reviewer finds a minor formatting issue.

Verification used automated tests, mock/replay runs, and selected live API runs.
Replay results validate software behavior and scoring logic; they are not evidence
of real-model answer accuracy. A resumed live run is identified as such rather than
presented as an entirely fresh sequence of model calls.

## 5. Report writing and language assistance

AI helped organize and draft sections of the development report, explain the
architecture and development process, and improve English wording. It was also used
to correct grammar, rephrase unclear sentences, and maintain consistent technical
terminology.

Language editing does not establish factual correctness. Technical claims, test
results, screenshots, and references must remain consistent with the actual project
and its available evidence. Unmeasured quality targets must not be presented as
completed experiments or verified results.

## 6. Human responsibility and remaining review

I remain responsible for the final submission, including understanding the code,
checking the report, and deciding whether AI suggestions should be accepted. AI
output is not treated as an authoritative source or as a substitute for my review.

Generated exams require human inspection of mathematical correctness, answer keys,
rendered figures, labels, and page layout. Successful compilation, valid JSON, or
agreement between agents does not by itself prove that an exam is correct.

API keys and private configuration are not reproduced in this declaration and
should not be included in the submitted materials.
