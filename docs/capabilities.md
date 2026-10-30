# Twinfra capability statement

As of 2026-10-30. v0.1.0 is a dev acceptance candidate, not a published release.
Twinfra implements an **AWS-compatible API subset**, not AWS
service parity. The deployed MiniStack profile is an emulator with persistence
disabled (`MINISTACK_PERSIST=0`); an emulated EC2 response does not create a VM.
Rows below cover the AWS catalog in [ADR-0029](adr/0029-aws-compatible-enterprise-simulator.md)
and the platform building blocks. Unlisted AWS services are not claimed.

Platform-only **Dev-verified** rows below are limited to their Accepted receipts;
they do not establish any AWS service as Real.

Status meanings: **Emulated by MiniStack** identifies only an emulator-backed
API subset; **Planned** includes implemented code awaiting current acceptance;
**Real** requires persistent infrastructure and Accepted live tester evidence;
**Parity-tested** additionally requires an operation-level AWS comparison under
[ADR-0033](adr/0033-aws-sandbox-and-parity-testing.md). No current row is Real or
Parity-tested. A Pending receipt, static test or historical WSL receipt cannot
support either claim. Foundation 1.0 and the current ADR status register are
governed by [ADR-0052](adr/0052-evidence-first-foundation-1-0.md).

Work orders named without a link are planned work not yet copied into this
repository; they are dependencies, not implementation or deployment authority.

## AWS API subset

The emulator rows describe the read paths implemented by the console, not
complete upstream service coverage. All other catalog entries remain Planned.
Real S3/EC2 implementation waits for Foundation 1.0 and WO-22; every parity claim
also needs ADR-0033's scorecard and tester acceptance.

| AWS service | Status | Evidence / limits | Work order changing it |
| --- | --- | --- | --- |
| S3 | Emulated by MiniStack | [Signed bucket/object list implementation](../console/server.py); [emulator profile](../tools/platform_dev.py), no durable backend | WO-22 (real SeaweedFS backend); parity ADR-0033 |
| EC2 | Emulated by MiniStack | [DescribeInstances implementation](../console/server.py); [emulator profile](../tools/platform_dev.py), no KubeVirt VM provisioning | WO-22 (real compute backend); parity ADR-0033 |
| DynamoDB | Emulated by MiniStack | [Signed table-list implementation](../console/server.py); [emulator profile](../tools/platform_dev.py), no production database claim | Wave 2; parity ADR-0033 |
| IAM | Planned | [Account/policy design](adr/0053-tenancy-model-accounts-and-iam.md); emulator health display is not IAM policy enforcement | WO-22 / Wave 2; ADR-0033 |
| STS | Planned | [AssumeRole/federation proposal](adr/0053-tenancy-model-accounts-and-iam.md) | WO-22 / Wave 2; ADR-0033 |
| Accounts | Planned | [Two-account denial matrix proposal](adr/0053-tenancy-model-accounts-and-iam.md); no multi-tenancy claim | WO-22 / Wave 2; ADR-0033 |
| CloudWatch metrics | Planned | [Catalog](adr/0029-aws-compatible-enterprise-simulator.md); Prometheus is not CloudWatch API parity | Wave 2; ADR-0033 |
| CloudWatch alarms | Planned | [Catalog](adr/0029-aws-compatible-enterprise-simulator.md) | Wave 2; ADR-0033 |
| CloudWatch logs | Planned | [Catalog](adr/0029-aws-compatible-enterprise-simulator.md) | Wave 2; ADR-0033 |
| KMS | Planned | [Catalog](adr/0029-aws-compatible-enterprise-simulator.md) | Wave 2; ADR-0033 |
| Secrets Manager | Planned | [Catalog](adr/0029-aws-compatible-enterprise-simulator.md); OpenBao is not this API | Wave 2; ADR-0033 |
| SSM | Planned | [Catalog](adr/0029-aws-compatible-enterprise-simulator.md) | Wave 2; ADR-0033 |
| CloudTrail | Planned | [Catalog](adr/0029-aws-compatible-enterprise-simulator.md) | Wave 2; ADR-0033 |
| EBS | Planned | [EC2 storage catalog](adr/0029-aws-compatible-enterprise-simulator.md) | WO-22 / Wave 2; ADR-0033 |
| AMIs | Planned | [EC2 image catalog](adr/0029-aws-compatible-enterprise-simulator.md) | WO-22 / Wave 2; ADR-0033 |
| EC2 key pairs | Planned | [EC2 catalog](adr/0029-aws-compatible-enterprise-simulator.md) | WO-22 / Wave 2; ADR-0033 |
| EC2 user data | Planned | [EC2 catalog](adr/0029-aws-compatible-enterprise-simulator.md) | WO-22 / Wave 2; ADR-0033 |
| IMDSv2 | Planned | [Role credential design](adr/0029-aws-compatible-enterprise-simulator.md) | WO-22 / Wave 2; ADR-0033 |
| VPC / security groups | Planned | [Network catalog](adr/0029-aws-compatible-enterprise-simulator.md) | WO-22 / Wave 2; ADR-0033 |
| Elastic Load Balancing | Planned | [Catalog](adr/0029-aws-compatible-enterprise-simulator.md) | Wave 2; ADR-0033 |
| Auto Scaling | Planned | [Catalog](adr/0029-aws-compatible-enterprise-simulator.md) | Wave 2; ADR-0033 |
| Lambda | Planned | [Catalog](adr/0029-aws-compatible-enterprise-simulator.md); Knative references are not Lambda parity | Wave 2; ADR-0033 |
| RDS for PostgreSQL | Planned | [Per-account CNPG proposal](adr/0053-tenancy-model-accounts-and-iam.md); internal PostgreSQL is not RDS | Wave 2; ADR-0033 |
| ECR | Planned | [Catalog](adr/0029-aws-compatible-enterprise-simulator.md); OCI image staging is not ECR API parity | Wave 2; ADR-0033 |
| CloudFormation / CDK templates | Planned | [Catalog](adr/0029-aws-compatible-enterprise-simulator.md) | Wave 2; ADR-0033 |
| EKS | Planned | [Catalog](adr/0029-aws-compatible-enterprise-simulator.md); kubeadm is not EKS API parity | Wave 2; ADR-0033 |
| SQS | Planned | [Tier 2 catalog](adr/0029-aws-compatible-enterprise-simulator.md) | Wave 2; ADR-0033 |
| SNS | Planned | [Tier 2 catalog](adr/0029-aws-compatible-enterprise-simulator.md) | Wave 2; ADR-0033 |
| EventBridge | Planned | [Tier 2 catalog](adr/0029-aws-compatible-enterprise-simulator.md) | Wave 2; ADR-0033 |
| ElastiCache | Planned | [Tier 2 catalog](adr/0029-aws-compatible-enterprise-simulator.md); Argo CD's Valkey cache is not this API | Wave 2; ADR-0033 |
| Route 53 | Planned | [Tier 2 catalog](adr/0029-aws-compatible-enterprise-simulator.md); owner DNS records are not Route 53 parity | Wave 2; ADR-0033 |
| Organizations | Planned | [Explicitly outside current tenancy scope](adr/0053-tenancy-model-accounts-and-iam.md) | New owner work order; ADR-0033 |
| Service Quotas | Planned | [Tier 2 catalog](adr/0029-aws-compatible-enterprise-simulator.md) | Wave 2; ADR-0033 |
| Billing simulation | Planned | [Outside current tenancy scope](adr/0053-tenancy-model-accounts-and-iam.md) | New owner work order; ADR-0033 |

## Platform capabilities

For this table, Planned means **acceptance pending**, even where code and
owner-reported running services already exist. Dev-verified rows are restricted
to the signed WO-04, WO-06, WO-25, WO-31, WO-34 P2 and WO-36/36a scope.
The consolidated rc receipt remains Pending. Historical observations do not
advance current status, and a signed host receipt does not accept every
security, storage, identity or observability feature on that host.

| Platform capability | Status | Evidence / current implementation and missing acceptance | Work order changing it |
| --- | --- | --- | --- |
| Ubuntu / kubeadm single-node host | Dev-verified | [Accepted WO-31](acceptance/dev-environment-2026-10-13.md): bootstrap, host checks, manifest contract, two acceptance passes and the owner-approved 12-hour dev soak; the owner confirmed on 2026-10-18 that the later 09:53–09:59 UTC eno1 flaps came from a power problem at the network equipment, with no host change needed; the signed receipt is unchanged | [WO-31](work-orders/WO-31-bare-metal-cairo-1.md); production/HA not claimed |
| Static address / router-loss resilience | Dev-verified | [Accepted WO-36](acceptance/host-network-2026-10-15.md): `.3` retained during a 40 s router outage; zero DHCP lease loss or post-boot pod/control-plane restarts | [WO-36](work-orders/WO-36-host-network-and-staging-safety.md) |
| Static-netplan transaction qualification | Dev-verified | [Accepted WO-36a](acceptance/host-network-fix-2026-10-15.md) and [Accepted cairo-1 current-profile check](acceptance/host-network-2026-10-15.md): real Ubuntu VM apply/refusal/rollback, gap 0.245504 s; owned current profile adopted on cairo-1; no new Dell rollback claim | [WO-36 Amendment 1](work-orders/WO-36-host-network-and-staging-safety.md) |
| Host firewall / image-staging failure recovery | Planned | [WO-31 firewall observations](acceptance/dev-environment-2026-10-13.md), [WO-36 remaining gates](acceptance/host-network-2026-10-15.md); broader signed acceptance still Pending | [WO-31](work-orders/WO-31-bare-metal-cairo-1.md), [WO-36](work-orders/WO-36-host-network-and-staging-safety.md) |
| Cilium native eBPF / default deny / PSS | Planned | [Bootstrap/policy observations](acceptance/dev-environment-2026-10-13.md); current signed enforcement acceptance Pending | [WO-31](work-orders/WO-31-bare-metal-cairo-1.md), [WO-05](work-orders/WO-05-admission-policies.md) |
| Local storage / CNPG / pgvector | Planned | [Accepted WO-31 host/platform baseline](acceptance/dev-environment-2026-10-13.md) includes a 20 GiB PG LV and healthy database observations; it does not accept PITR, growth or the pgvector SQL extension separately | [WO-09](work-orders/WO-09-backups-and-restore-drill.md), WO-33 |
| Argo CD reconciliation / Valkey cache | Dev-verified | [Accepted WO-25](acceptance/valkey-2026-10-09.md): NOAUTH/PONG, measured cache hits, three clients reconnect after the authorized restart and fresh healthy reconciliation; no upstream Valkey support claim | [WO-25](work-orders/WO-25-redis-to-valkey.md) |
| APISIX / HTTPS console / Keycloak OIDC | Dev-verified | [Accepted WO-04 browser witness](acceptance/console-token-verification-2026-10-10.md): trusted HTTPS, TOTP sign-in/out and role denial; complete RBAC, CSRF and audit acceptance remains separate | [WO-11](work-orders/WO-11-console-roles-csrf-audit.md) |
| Signed token / console role verification | Dev-verified | [Accepted WO-04](acceptance/console-token-verification-2026-10-10.md): missing/unsigned/duplicate headers return 401; roleless BFF token returns 403; manual browser witness recorded | [WO-04](work-orders/WO-04-console-token-verification.md), [WO-11](work-orders/WO-11-console-roles-csrf-audit.md) |
| LocalStack removal / MiniStack read views | Dev-verified | [Accepted WO-06](acceptance/localstack-removal-2026-10-10.md): no LocalStack resources/images, sole MiniStack emulator, health and S3/EC2/DynamoDB read views; no Real AWS capability | [WO-06](work-orders/WO-06-remove-localstack.md) |
| CoreDNS / etcd maintenance | Dev-verified | [Accepted WO-34 P2 live receipt](acceptance/wo34-p2-2026-10-15.json) and [Accepted WO-31 runtime checks](acceptance/dev-environment-2026-10-13.md): CoreDNS 1.14.7 / etcd 3.6.15 and locked digests; no backup/DR claim | [WO-34](work-orders/WO-34-image-patch-refresh.md), [WO-40c](work-orders/WO-40c-control-plane-maintenance.md) |
| OpenBao / dynamic secrets / certificate automation | Planned | [Running/transport observations](acceptance/dev-environment-2026-10-13.md) do not establish initialization, unseal or leases | [WO-08](work-orders/WO-08-openbao-eso-cert-manager.md), [Module 4a reference](../module-4a/README.md) |
| Knative CPU serving | Planned | [Historical (retired environment)](acceptance/wsl-2026-10-07.md); no current cairo-1 acceptance | ADR-0052 evidence work |
| Prometheus metrics | Planned | [Historical (retired environment)](acceptance/wsl-2026-10-07.md); durable metrics acceptance Pending | [WO-10](work-orders/WO-10-observability-stack-v1.md) |
| OpenTelemetry / durable logs and traces | Planned | [Historical (retired environment)](acceptance/wsl-2026-10-07.md); debug spans are not a durable backend | [WO-10](work-orders/WO-10-observability-stack-v1.md) |
| Perses dashboards / delivered alerts | Planned | [Ported dashboard data](../deploy/observability/dashboards/README.md), no Perses deployment or delivered-alert acceptance | [WO-10 Amendment 1](work-orders/WO-10-observability-stack-v1.md) |
| CI licence and vulnerability gates | Planned | [WO-32 static evidence](acceptance/supply-chain-2026-10-14.md), [CI definitions](github-actions-tests.md); live issue acceptance Pending | [WO-32](work-orders/WO-32-supply-chain-scanning.md), [WO-34](work-orders/WO-34-image-patch-refresh.md) |
| GitHub Actions / GHCR / verified provenance | Planned | [ADR-0052 decision 5](adr/0052-evidence-first-foundation-1-0.md); deployment signer/provenance verification not implemented | New supply-chain work order under ADR-0052 |
| Backups / PITR / disaster recovery | Planned | [Restore-drill work order](work-orders/WO-09-backups-and-restore-drill.md), no completed live restore receipt | WO-09 / [WO-23](work-orders/WO-23-dr-drill.md) / [WO-24](work-orders/WO-24-second-host-warm-dr.md) |
| Multi-node readiness / HA | Planned | [ADR-0050](adr/0050-cairo-1-high-availability.md); one node today, HA only after three-node acceptance | WO-33 / WO-33b |
| Real DNS / publicly trusted certificates | Planned | [ADR-0051](adr/0051-real-dns-zone-twinfra-amazen33-dev.md); internal names and loopback tunnels remain current | Owner DNS / WO-33 Part D / future certificate work |
| Tenant isolation / IAM / cross-account denial | Planned | [ADR-0053](adr/0053-tenancy-model-accounts-and-iam.md) remains Proposed; no multi-tenant claim | WO-22 / Wave 2 after Foundation 1.0 |
| Platform API / Crossplane provisioning | Planned | [ADR-0031](adr/0031-crossplane-platform-api.md) is an accepted design; no current provisioning receipt | WO-22 / Wave 2 after Foundation 1.0 |
| AWS gateway SigV4 / audit / parity harness | Planned | [ADR-0029](adr/0029-aws-compatible-enterprise-simulator.md) gateway and [ADR-0033](adr/0033-aws-sandbox-and-parity-testing.md) scorecards are designs; emulator client signing is not a gateway authorization or parity test | WO-22 / Wave 2; ADR-0033 |
| Kafka / Strimzi | Planned | [Deferred ADR-0014](adr/0014-kafka.md) / [0015](adr/0015-strimzi.md), current status in [index](adr/README.md) | New owner decision required (ADR-0052) |
| GPU vLLM / LangChain RAG (Module 5a) | Planned | [Disabled reference](../module-5a/README.md); ADR-0016/0017 Deferred in [index](adr/README.md) | New owner decision required (ADR-0052) |
| DeepSeek / Spinifex HPC (Module 5b) | Planned | [Disabled reference](../module-5b/README.md); ADR-0023 Deferred in [index](adr/README.md) | New owner decision required (ADR-0052) |
| Multiple regions | Planned | [cairo-2 cold seed](dev-environment.md#part-2-cairo-2-cold-standby-on-hyper-v); no running second region or failover claim | [WO-23](work-orders/WO-23-dr-drill.md) / [WO-24](work-orders/WO-24-second-host-warm-dr.md) |

## Blocking evidence check

The owner's [post-R12 acceptance](release-notes/0.1.0.md#evidence-and-actual-running-versions)
on 2026-10-29 at `7cf2ba8` passed all 17 checks, including `valkeyRestart`,
with the promoted Argo CD 3.5.5, Keycloak 26.8.1 and MiniStack 1.5.33 images.
It supplements the dated Accepted scopes above; it creates no new capability
status or consolidated rc sign-off. Console development-dependency maintenance
is deferred to post-release WO-47 under WO-40 Amendment 10f.

`python tools/ci/check_capabilities.py` checks current ADR index statuses and
status-labelled rows in the README/docs, plus any ADR live-status header. Each
Dev-verified, Production-accepted, Real or Parity-tested claim needs an in-repo
Markdown receipt under `docs/acceptance/`, a named tester's `Result: Accepted`
in its Tester sign-off block and the matching live environment. Historical WSL
receipts never qualify. The required PR gate invokes this check through the
documentation gate; the pre-WO-37 historical revisions retain their old checks.
This check verifies evidence references and sign-off; the tester still assesses
the actual scope, parity scorecard and QoS results.
