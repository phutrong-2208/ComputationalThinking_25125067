# Requirements Analysis

## Confirmed Facts
- The requirement document is titled "Payment Retry Policy".
- Failed payment attempts shall be retried automatically.
- The system should stop retrying after a reasonable number of attempts.
- Customers must be notified if their payment ultimately fails.
- Certain failures should not be retried at all.
- The system shall record the outcome of each attempt.

## Ambiguities
- **"Failed payment attempts shall be retried automatically."**
  Reason: It does not define the trigger, execution context, or whether retries are synchronous, asynchronous, or scheduled.
  Resolved by: A decision on when retries start and what component orchestrates them.
  Edge case: A payment could be retried immediately in a tight loop, causing duplicate provider calls or request storms.
- **"Retries must be spaced out sensibly to avoid overwhelming the payment provider."**
  Reason: "sensibly" is subjective and does not specify backoff algorithm, timing, or jitter.
  Resolved by: Exact retry intervals, backoff strategy, and any rate-limiting requirements.
  Edge case: A fixed short interval could trigger provider throttling and widespread payment delays.
- **"The system should stop retrying after a reasonable number of attempts."**
  Reason: "reasonable" is not quantified and leaves the maximum retry count undefined.
  Resolved by: The exact maximum number of attempts or conditions that terminate retries.
  Edge case: Too many retries could repeatedly charge or lock a payment method; too few could cause avoidable payment failures.
- **"Customers must be notified if their payment ultimately fails."**
  Reason: It does not specify notification channel, timing, content, localization, or delivery guarantees.
  Resolved by: The required notification methods and when the notification must be sent.
  Edge case: A customer may never learn that a payment failed if email delivery is delayed or missing.
- **"Certain failures should not be retried at all."**
  Reason: It does not identify which failure classes are non-retryable or how they are detected.
  Resolved by: The list of non-retryable error codes or failure categories and their classification rules.
  Edge case: The system may keep retrying a permanently invalid card or a hard decline, wasting resources and confusing customers.
- **"The system shall record the outcome of each attempt."**
  Reason: It does not define what data must be recorded, where it is stored, or retention/access expectations.
  Resolved by: The audit schema, storage location, and retention policy for attempt records.
  Edge case: Insufficient logs could prevent support teams from diagnosing why retries failed.

## Clarification Questions
- What exact retry schedule should be used, including initial delay, backoff pattern, maximum delay, and jitter?
- How many total retry attempts are allowed before the payment is considered failed?
- Which payment failures must never be retried?
- What customer notification channel(s) should be used when retries are exhausted?
- What should be recorded for each attempt, and how long must those records be retained?

## Assumptions
- Retries are handled asynchronously by a background job or queue rather than blocking the original payment request.
- A product or engineering decision will define a concrete backoff policy and retry limit if one is not already documented elsewhere.
- Non-retryable failures will be identified by provider error codes or an equivalent classification rule.
- Customer notification will be sent through the application's existing customer communication channel unless otherwise specified.
- Attempt records will be stored in the system's existing application datastore or audit log.

## Summary
The document defines a payment retry policy with automatic retries, a cap on retry attempts, customer notification on ultimate failure, and recording of each attempt's outcome. However, the exact retry timing, retry limit, failure classifications, notification details, and logging requirements are not specified and need clarification before implementation.

