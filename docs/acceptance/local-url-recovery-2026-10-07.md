# Local URL recovery — 2026-10-07

The operator reported LocalStack port 4566 unavailable, supplied a working
Keycloak discovery document, and observed OpenBao `{"initialized":false}`.

## Root cause and repair

LocalStack's Pod was 1/1 Ready, while
`vcloud-wsl-localstack-access.service` was inactive with no listener. Its journal
showed API connection refusal and `ServiceUnavailable` during a temporary K3s
outage, then repeated immediate restarts and `Start request repeated too quickly`.
This was a failed port-forward service, not an image pull or Cilium policy fault.

The scoped helper waits for backend rollout, starts only its existing named
loopback unit, sets `Restart=on-failure`, `RestartSec=3` and
`StartLimitIntervalSec=0`, and reports success only after all four configured
LocalStack services return `running` from the health API. It still refuses an
unknown occupied port. No Pod, K3s, Cilium, firewall or Windows trust-store change
was required.

## Executed acceptance

| Check | Result |
|---|---|
| Windows `http://127.0.0.1:4566/` | HTTP 200 |
| Windows `http://127.0.0.1:4566/_localstack/health` | HTTP 200; S3/EC2/IAM/DynamoDB running, Community 4.14.0 |
| Forward retry configuration | `RestartUSec=3s`, `Restart=on-failure`, `StartLimitIntervalUSec=0` |
| Scoped failure recovery | Terminated only the verified owned forward's main process; a new PID and healthy listener returned within the bounded retry test. No cluster or Pod restart. |
| Keycloak discovery, Windows and WSL | HTTP 200 with its public certificate and `localhost` hostname verified; issuer `https://localhost:18443/realms/vcloud` |
| Operator's Keycloak browser response | Supplied valid discovery JSON; this API is working |
| OpenBao initialization status | HTTP 200, `initialized:false`; initialization/unseal remain gated |
| LocalStack regression suite | 8 tests passed; revised access helper ShellCheck passed |

The initial Windows `curl.exe` Keycloak test failed in Schannel before HTTP
(`SEC_E_NO_CREDENTIALS`). Independent Python TLS verification and the operator's
browser result confirmed server discovery; no insecure certificate bypass was
used. Only the public certificate was exported to the ignored `.build` directory;
the Windows trust store was not altered.

Keycloak's GUI is `https://localhost:18443/admin/`. Successful discovery does not
establish administrator login or the new console client's authentication. The
current discovery scopes do not advertise `profile`, so the gated console
reference requests only `openid`. Its proposed external issuer, confidential
client Secret, DNS/CA trust and authenticated browser acceptance remain open.

The unified console, Spinifex and OpenBao reference integrations retain the
gates documented in the [console runbook](../../lab/wsl/console/README.md).
The [service-access page](../service-access.md) distinguishes GUI/API URLs and
expected initialization status.
