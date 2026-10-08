# Keycloak administrator access in the owned WSL lab

For the new [portal](../console/README.md), use `vcloud-admin` in the **vcloud**
realm and `deploy/console/copy-password.ps1`. That account has `console.admin`
only, a separate temporary password and required password change/MFA. The
master account documented below retains separate full administration authority.

The local GUI is <https://localhost:18443/admin/>. Use the **master** realm and
username **vcloud-admin**. Working OIDC discovery establishes transport health;
it does not create an administrator. The original realm import deliberately had
no users and no bootstrap password, so the GUI initially had no usable account.

## First administrator bootstrap

Run only against the single owned `vcloud-wsl-local` node:

```bash
cd /mnt/e/vCloud
sudo python3 tools/wsl_keycloak_admin.py --check
sudo python3 tools/wsl_keycloak_admin.py
```

The helper checks restricted:v1.30 admission, stable K3s encryption at rest,
immutable images, ownership and master-realm users. It refuses unrelated
existing users, unowned credential references and pre-existing recovery Pods.
It never resets an existing administrator's password.

For a fresh account, it generates strong independent passwords in memory and
stores them in encrypted Kubernetes Secrets. It temporarily sets the existing
endpoint Application's `argocd.argoproj.io/skip-reconcile` annotation, stops only
Keycloak's single replica and runs the installed `bootstrap-admin user` command
with the same database/TLS configuration in a restricted, bounded Pod. An
echo-disabled terminal receives private input through stdin; no password is an
argument, environment variable, host file or log entry. Runtime configuration
stays on the existing memory-backed volumes. The offline Pod never becomes a
Ready Service endpoint. Cleanup checks its exact UID and restores the server
replica and prior Application annotation even if recovery fails.

After HTTPS access is restored, the helper authenticates the temporary account,
creates `vcloud-admin` in master, assigns the master realm `admin` role and
verifies both password authentication and authorized administration. It then
deletes the temporary account and its recovery Secret. The permanent account
is independent of startup environment variables and of the public vcloud realm
import. Re-running verifies and preserves its current initial password.

The procedure briefly interrupts Keycloak login only. It does not initialize
OpenBao, edit the realm's application clients, activate unified-console OIDC,
weaken network policies, or enable GPU/HPC workloads. Keycloak's upstream
[recovery procedure](https://www.keycloak.org/server/bootstrap-admin-recovery)
requires all server instances stopped. Argo CD documents the
[skip-reconcile annotation](https://argo-cd.readthedocs.io/en/latest/user-guide/skip_reconcile/).

## Retrieve the password privately

From a **local Windows PowerShell terminal**, run:

```powershell
cd E:\vCloud
& .\lab\wsl\endpoints\copy-keycloak-password.ps1
```

This reads only the administrator Secret through the private WSL kubeconfig,
verifies its ownership/username, and copies the password to the local clipboard.
It prints only the public username and a success message. Paste into the
Keycloak login page. Keep clipboard history/cloud synchronization disabled for
credential handling, and clear the clipboard after pasting:

```powershell
Set-Clipboard -Value ''
```

The credential reference is
`platform-services/vcloud-wsl-keycloak-admin`, keys `admin-user` and
`admin-password`. Do not decode it into chat, terminal output, Git, `.env`,
README files or a plaintext host file. Store your chosen permanent credential
in your operator password manager, enable OTP/WebAuthn after login, and manage
future password changes through Keycloak. The retained Secret is the **initial**
password; it is not automatically updated when you change the password in the
GUI. A subsequent helper login check will fail rather than overwrite it. After
MFA enrollment, password-only helper verification also requires separate operator
handling; this utility never removes MFA to make its check pass.

## Failure recovery

If interrupted before completion, inspect only public control state: Keycloak
replica/Ready status, endpoint Application skip annotation and the recovery
Pod's phase. Retained recovery credentials stay in
`vcloud-wsl-keycloak-recovery`; do not print them. The helper can resume a known
temporary account or a partially created permanent account using those owned
references. It refuses unknown master-realm users or unowned Secrets.

If an external termination prevented `finally` cleanup, restore the known
single Keycloak replica and the Application's prior annotation after verifying
the offline recovery Pod has stopped. Do not run the recovery CLI concurrently
with the server, delete the database, remove other users or rerun realm import
as a substitute for account recovery. Never use a TLS verification bypass.

Offline CI validates the restricted Pod fixture with strict kubeconform and
the existing conftest policy; synthetic regression tests cover credential
ownership/strength, stdin-only transfer, immutable images, denied privilege/
host-mount mutations and restoration after an injected failure. CI creates
neither accounts nor credentials.
