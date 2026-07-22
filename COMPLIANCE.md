# UK Outreach Control Policy

This document describes product safeguards, not legal advice. The organisation using Leadroom remains responsible for its lawful basis, transparency information, subscriber classification, message content, contracts, and current UK GDPR/PECR compliance.

Reviewed against ICO guidance on 14 July 2026:

- [Business-to-business marketing](https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/business-to-business-marketing/)
- [Electronic mail marketing rules](https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/guidance-on-direct-marketing-using-electronic-mail/how-do-we-comply-with-the-pecr-electronic-mail-marketing-rules/)
- [Right to object](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/individual-rights/individual-rights/right-to-object/)
- [Respect people's preferences](https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/direct-marketing-guidance/respect-peoples-preferences/)

## Product Rules

1. Leadroom can deliver approved drafts through a user-configured SMTP account. Delivery is never allowed directly from an unapproved draft.
2. Only public generic business mailboxes such as `info@`, `hello@`, or `contact@` are eligible. Named or personal mailboxes are blocked.
3. Email source evidence and a lead score of at least 7 are required.
4. Corporate subscribers require a documented lawful-basis note and a human corporate-status check.
5. Sole traders, ordinary partnerships, and unknown subscriber types are blocked unless consent is recorded and explicitly documented in the note.
6. Every draft identifies the sender and contains a valid opt-out address.
7. A reviewer must confirm recipient eligibility and privacy-notice checks before export or delivery.
8. Email and domain suppression hashes are screened at draft, approval, export, queue, and delivery time.
9. Duplicate active recipients are blocked. Exports and successful sends are limited to 25 approved drafts per rolling 24 hours.
10. Detailed outreach drafts can be purged after a configured period of at least 30 days. Suppression records retain only a hash, display hint, reason, and timestamp.
11. A deletion workflow removes lead and draft content while retaining minimal suppression hashes to respect future objections.
12. Only one delivery job can run at a time. Stopping a job returns unsent queue entries to approved; an interrupted or ambiguous SMTP transaction is quarantined as `uncertain` instead of automatically retried.

## Eligibility Matrix

| Recipient | Default | Additional requirement |
|---|---|---|
| Corporate body, generic mailbox | Reviewable | Lawful-basis note, status check, transparency check |
| Corporate body, named mailbox | Blocked | Not supported by this product |
| Sole trader or ordinary partnership | Blocked | Recorded and documented consent |
| Unknown subscriber type | Blocked | Recorded and documented consent |
| Suppressed email or domain | Blocked | No override |

## Operational Checkpoint

Before any real-world use, a responsible person must review the current ICO guidance, complete the organisation's legitimate-interests assessment where applicable, verify its privacy notice, define retention periods, and test the opt-out handling process. Product approval is an audit control; it is not a legal determination.
