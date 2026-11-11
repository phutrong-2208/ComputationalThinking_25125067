# Proposal

## Summary signal

`/v1_live/summary.json` shows first-attempt pass rates of 5/5 for completeness but only 1/5 for both clarity and depth. The low-performing criteria are the required `Resolved by:` and `Edge case:` lines under each Ambiguities bullet.

## Pattern found

The agent's initial ambiguity format follows the current AGENTS.md instruction exactly: quote the clause and provide only `Reason:`. Because AGENTS.md does not ask for `Resolved by:` or `Edge case:`, the agent repeatedly omits both labels.

This appears across all five initial outputs. Four runs were explicitly rejected for it; the remaining run's initial analysis also omitted the labels even though the grader marked it satisfied.

## Evidence

- Run 01 grader: "The Ambiguities bullets lack the required indented \"Resolved by:\" and \"Edge case:\" lines"
- Run 01 gap: "The Ambiguities bullets at lines 11-18 only include \"Reason:\" lines; there are no indented \"Resolved by:\" lines anywhere under each bullet."
- Run 02 grader: "None of the Ambiguities bullets has an indented \"Resolved by:\" line, and none has an indented \"Edge case:\" line."
- Run 04 grader: "The Ambiguities section is missing the required indented 'Resolved by:' and 'Edge case:' lines for each ambiguity bullet."
- Run 05 grader: "The Ambiguities section contains only \"Reason:\" lines; it does not include any indented \"Resolved by:\" lines for the bullets."
- Run 03 initial analysis also shows the same format: "- **\"Retries must be spaced out sensibly to avoid overwhelming the payment provider.\"**\n  Reason: \"sensibly\" is subjective and does not define a retry schedule, backoff strategy, or upper bounds."

## Fit with current instructions

AGENTS.md currently says under `### Ambiguities`: "Quote the exact clause, then give the reason it is under-specified." The procedure's example likewise only includes `Reason:`. The proposed addition belongs under `### Ambiguities` and adds the two missing rubric-required labeled lines without changing other sections.

## Proposed addition

```markdown
Every ambiguity bullet must include exactly three indented labeled lines after the quoted clause:

```
  Reason: why it is under-specified
  Resolved by: the specific fact or decision that would settle the ambiguity
  Edge case: a concrete production failure this ambiguity could cause
```
```

## Rejected observations

- Duplicated empty section headers were mentioned in run 01, but this was not the recurring rubric failure across the batch. Runs 02 and 03 encountered intermediate edit collisions but repaired them before grading, so this is not the main first-attempt criterion pattern.
