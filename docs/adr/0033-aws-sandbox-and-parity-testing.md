# ADR-0033: AWS sandbox account and parity testing

**Status:** Accepted (owner, 2026-10-08)
**Author:** Claude (platform architecture). **Decider:** vCloud owner. **Records:** D5.

## Decision

1. A dedicated AWS sandbox account with a budget alarm and an automatic spending cap.
   The owner creates and holds its credentials. They never enter Git, CI logs or an agent's environment.
   Access for test runs uses short-lived credentials issued by the owner's chosen mechanism.
2. A **parity harness** runs the same test suites against the sandbox and a vCloud region: the AWS SDK
   for Go v2, boto3, AWS CLI scripts, a CloudFormation template set and CDK sample apps. Every API
   operation is scored Match, Partial or Missing.
3. A service is labelled Real (ADR-0029) only when its scored operations match. The scorecard is
   published with each release's acceptance receipt.
4. Every run cleans up the resources it created. A leftover-resource check fails the run.

## Consequences

AWS spend is bounded and visible. Fidelity claims rest on evidence. Phase 4's "switch" exit
criteria are tested here.
