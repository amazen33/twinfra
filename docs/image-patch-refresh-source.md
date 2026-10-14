# WO-34 source reachability and P2 net improvement

Static evidence from [CI run](https://github.com/amazen33/twinfra/actions/runs/38630364025). No application binary was built or executed; live/tester acceptance remains Pending.

**Promotion stopped for Argo CD, CoreDNS and etcd: source mode reports reachable GO-2026-6612.** Amendment 2 requires an owner decision; no risk acceptance, exception transfer, lock change or expiry extension is made.

| Image | Critical with fix | Critical without fix | High with fix | High without fix |
| --- | ---: | ---: | ---: | ---: |
| argocd-before | 22 | 0 | 141 | 0 |
| argocd-after | 22 | 0 | 133 | 0 |
| coredns-before | 11 | 0 | 48 | 0 |
| coredns-after | 3 | 0 | 20 | 0 |
| etcd-before | 11 | 0 | 43 | 0 |
| etcd-after | 3 | 0 | 13 | 0 |

All three candidates are net improvements with no new Critical/High identities in the same database. Argo CD 3.5.5 remains age-ineligible before **2026-10-26**. Net improvement does not override the reachable-source stop.

## Call-stack evidence

Argo CD 3.5.5 still carries GO-2026-6612 in **golang.org/x/net v0.59.0** (fixed v0.60.0), not its updated Go 1.26.9 stdlib. CoreDNS and etcd retain affected x/net and stdlib. Selected source configurations match the published binary toolchains; bundled Argo auxiliary binaries remain separately affected binary findings.

### argocd: usr/local/bin/argocd

`GOTOOLCHAIN=go1.26.9`, 44 source findings for GO-2026-6612. Classification: **reachable**.

Module `golang.org/x/net v0.59.0`; representative caller-to-vulnerable-function path:

```text
github.com/argoproj/argo-cd/v3/cmd..main (cmd/main.go:87)
github.com/spf13/cobra.*Command.Execute (command.go:1071)
github.com/spf13/cobra.*Command.ExecuteC (command.go:1148)
github.com/spf13/cobra.*Command.execute (command.go:1015)
github.com/argoproj/argo-cd/v3/cmd/argocd-commit-server/commands..NewCommand$1 (cmd/argocd-commit-server/commands/argocd_commit_server.go:102)
google.golang.org/grpc.*Server.Serve (server.go:991)
google.golang.org/grpc..Serve$3 (server.go:992)
google.golang.org/grpc.*Server.handleRawConn (server.go:1008)
google.golang.org/grpc.*Server.newHTTP2Transport (server.go:1051)
google.golang.org/grpc/internal/transport..NewServerTransport (internal/transport/http2_server.go:334)
golang.org/x/net/http2.*Framer.ReadFrame (http2/frame.go:571)
```

### coredns: coredns

`GOTOOLCHAIN=go1.26.6`, 235 source findings for GO-2026-6612. Classification: **reachable**.

Module `golang.org/x/net v0.57.0`; representative caller-to-vulnerable-function path:

```text
github.com/coredns/coredns..main (coredns.go:12)
github.com/coredns/coredns/coremain..Run (coremain/run.go:73)
github.com/coredns/caddy..Start (caddy.go:474)
github.com/coredns/caddy..startWithListenerFds (caddy.go:544)
github.com/coredns/caddy..startServers (caddy.go:818)
github.com/coredns/caddy..startServers$1 (caddy.go:803)
github.com/coredns/caddy..startServers$1$1 (caddy.go:808)
github.com/coredns/coredns/core/dnsserver.*ServergRPC.Serve (core/dnsserver/server_grpc.go:129)
google.golang.org/grpc.*Server.Serve (server.go:973)
google.golang.org/grpc..Serve$3 (server.go:974)
google.golang.org/grpc.*Server.handleRawConn (server.go:990)
google.golang.org/grpc.*Server.newHTTP2Transport (server.go:1033)
google.golang.org/grpc/internal/transport..NewServerTransport (internal/transport/http2_server.go:334)
golang.org/x/net/http2.*Framer.ReadFrame (http2/frame.go:571)
```

Module `stdlib v1.26.6`; representative caller-to-vulnerable-function path:

```text
github.com/coredns/coredns..main (coredns.go:12)
github.com/coredns/coredns/coremain..Run (coremain/run.go:57)
fmt..Println (src/fmt/print.go:315)
fmt..Fprintln (src/fmt/print.go:306)
net/http.*response.Write (src/net/http/server.go:1610)
```

### etcd: usr/local/bin/etcd

`GOTOOLCHAIN=go1.26.8`, 214 source findings for GO-2026-6612. Classification: **reachable**.

Module `golang.org/x/net v0.58.0`; representative caller-to-vulnerable-function path:

```text
go.etcd.io/etcd/server/v3..main (main.go:31)
go.etcd.io/etcd/server/v3/etcdmain..Main (etcdmain/main.go:32)
github.com/spf13/cobra.*Command.Execute (command.go:1071)
github.com/spf13/cobra.*Command.ExecuteC (command.go:1148)
github.com/spf13/cobra.*Command.execute (command.go:1019)
go.etcd.io/etcd/server/v3/etcdmain..startGRPCProxy (etcdmain/grpc_proxy.go:268)
go.etcd.io/etcd/server/v3/etcdmain..startServe (etcdmain/grpc_proxy.go:628)
go.etcd.io/etcd/server/v3/etcdmain..startServe$1 (etcdmain/grpc_proxy.go:628)
go.etcd.io/etcd/server/v3/etcdmain..startGRPCProxy$2 (etcdmain/grpc_proxy.go:268)
google.golang.org/grpc.*Server.Serve (server.go:973)
google.golang.org/grpc..Serve$3 (server.go:974)
google.golang.org/grpc.*Server.handleRawConn (server.go:990)
google.golang.org/grpc.*Server.newHTTP2Transport (server.go:1033)
google.golang.org/grpc/internal/transport..NewServerTransport (internal/transport/http2_server.go:334)
golang.org/x/net/http2.*Framer.ReadFrame (http2/frame.go:571)
```

Module `stdlib v1.26.8`; representative caller-to-vulnerable-function path:

```text
go.etcd.io/etcd/server/v3..main (main.go:31)
go.etcd.io/etcd/server/v3/etcdmain..Main (etcdmain/main.go:40)
go.etcd.io/etcd/server/v3/etcdmain..startEtcdOrProxyV2 (etcdmain/etcd.go:170)
net/http.http2StreamError.Error (src/net/http/h2_bundle.go:1410)
```

### etcd: usr/local/bin/etcdctl

`GOTOOLCHAIN=go1.26.8`, 135 source findings for GO-2026-6612. Classification: **reachable**.

Module `golang.org/x/net v0.58.0`; representative caller-to-vulnerable-function path:

```text
go.etcd.io/etcd/etcdctl/v3..init (main.go:19)
go.etcd.io/etcd/etcdctl/v3/ctlv3..init (ctlv3/ctl.go:25)
go.etcd.io/etcd/etcdctl/v3/ctlv3/command..init (ctlv3/command/util.go:23)
net/http..init (src/net/http/client.go:10)
net/http..init#2 (src/net/http/servemux121.go:34)
internal/godebug.*Setting.IncNonDefault (src/internal/godebug/godebug.go:122)
sync.*Once.Do (src/sync/once.go:69)
sync.*Once.doSlow (src/sync/once.go:78)
sync..OnceFunc$1$1 (src/sync/oncefunc.go:33)
google.golang.org/grpc/balancer/pickfirst.*pickfirstBalancer.ExitIdle (balancer/pickfirst/pickfirst.go:394)
google.golang.org/grpc/balancer/pickfirst.*pickfirstBalancer.startFirstPassLocked (balancer/pickfirst/pickfirst.go:405)
google.golang.org/grpc/balancer/pickfirst.*pickfirstBalancer.requestConnectionLocked (balancer/pickfirst/pickfirst.go:563)
google.golang.org/grpc.*acBalancerWrapper.Connect (balancer_wrapper.go:350)
google.golang.org/grpc.*addrConn.connect (clientconn.go:997)
google.golang.org/grpc.*addrConn.resetTransportAndUnlock (clientconn.go:1354)
google.golang.org/grpc.*addrConn.tryAllAddrs (clientconn.go:1471)
google.golang.org/grpc.*addrConn.createTransport (clientconn.go:1525)
google.golang.org/grpc/internal/transport..NewHTTP2Client (internal/transport/http2_client.go:420)
google.golang.org/grpc/internal/transport.*http2Client.reader (internal/transport/http2_client.go:1707)
google.golang.org/grpc/internal/transport.*framer.readFrame (internal/transport/http_util.go:493)
golang.org/x/net/http2.*Framer.ReadFrameHeader (http2/frame.go:511)
```

Module `stdlib v1.26.8`; representative caller-to-vulnerable-function path:

```text
go.etcd.io/etcd/etcdctl/v3..main (main.go:23)
go.etcd.io/etcd/etcdctl/v3/ctlv3..MustStart (ctlv3/ctl.go:116)
go.etcd.io/etcd/etcdctl/v3/ctlv3..Start (ctlv3/ctl.go:112)
github.com/spf13/cobra.*Command.Execute (command.go:1071)
github.com/spf13/cobra.*Command.ExecuteC (command.go:1160)
net/http.transportReadFromServerError.Error (src/net/http/transport.go:1040)
```

### etcd: usr/local/bin/etcdutl

`GOTOOLCHAIN=go1.26.8`, 99 source findings for GO-2026-6612. Classification: **reachable**.

Module `golang.org/x/net v0.58.0`; representative caller-to-vulnerable-function path:

```text
go.etcd.io/etcd/etcdutl/v3..init (ctl.go:21)
go.etcd.io/etcd/etcdutl/v3/etcdutl..init (etcdutl/common.go:26)
go.etcd.io/etcd/server/v3/etcdserver/api/snap..init (etcdserver/api/snap/snapshotter.go:45)
hash/crc32..MakeTable (src/hash/crc32/crc32.go:125)
sync..OnceFunc$1 (src/sync/oncefunc.go:22)
sync.*Once.Do (src/sync/once.go:69)
sync.*Once.doSlow (src/sync/once.go:78)
sync..OnceFunc$1$1 (src/sync/oncefunc.go:33)
google.golang.org/grpc/balancer/pickfirst.*pickfirstBalancer.ExitIdle (balancer/pickfirst/pickfirst.go:394)
google.golang.org/grpc/balancer/pickfirst.*pickfirstBalancer.startFirstPassLocked (balancer/pickfirst/pickfirst.go:405)
google.golang.org/grpc/balancer/pickfirst.*pickfirstBalancer.requestConnectionLocked (balancer/pickfirst/pickfirst.go:563)
google.golang.org/grpc.*acBalancerWrapper.Connect (balancer_wrapper.go:350)
google.golang.org/grpc.*addrConn.connect (clientconn.go:997)
google.golang.org/grpc.*addrConn.resetTransportAndUnlock (clientconn.go:1354)
google.golang.org/grpc.*addrConn.tryAllAddrs (clientconn.go:1471)
google.golang.org/grpc.*addrConn.createTransport (clientconn.go:1525)
google.golang.org/grpc/internal/transport..NewHTTP2Client (internal/transport/http2_client.go:420)
google.golang.org/grpc/internal/transport.*http2Client.reader (internal/transport/http2_client.go:1695)
google.golang.org/grpc/internal/transport.*http2Client.readServerPreface (internal/transport/http2_client.go:1671)
golang.org/x/net/http2.*Framer.ReadFrame (http2/frame.go:571)
```

Module `stdlib v1.26.8`; representative caller-to-vulnerable-function path:

```text
go.etcd.io/etcd/etcdutl/v3..main (main.go:23)
go.etcd.io/etcd/etcdutl/v3..Start (ctl.go:54)
github.com/spf13/cobra.*Command.Execute (command.go:1071)
github.com/spf13/cobra.*Command.ExecuteC (command.go:1160)
net/http.http2duplicatePseudoHeaderError.Error (src/net/http/h2_bundle.go:1450)
```

The receipt preserves positions, pins, SDK checksums and public artifact hashes. Full traces are in the CI artifacts. Govulncheck conservatively analyzes interfaces/function pointers and cannot establish actual exposure or universal runtime exploitability; these are source call paths, not a live exploit test.

## Owner decision and deadline watch

The owner chooses documented time-boxed risk acceptance with existing tunnel-only/owner-repository controls, or waits for a fixed eligible patch. No self-built application binaries, minor upgrades or expedite.

**76 current Critical exceptions expire 2026-11-12.** They have no not-reachable clearance established here; this is the early notice required **by 2026-11-05**. Source-reachable candidates cannot be promoted using a not-reachable exception. No expiry is extended.

Receipt: [source/P2 evidence](acceptance/wo34-source-2026-10-14.json).
