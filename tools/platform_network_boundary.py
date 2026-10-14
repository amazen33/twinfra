#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""WO-31 Amendment 10: offline dev exposure and ingress-isolation contract."""
from manifest_contract import flatten, podspec


# These are the pinned Helm node agents, not a label-based or namespace waiver.
# platform_validate also verifies their source names and frozen node projections.
CILIUM_NODE_EXCEPTIONS=frozenset({
    ('DaemonSet','kube-system','cilium'),
    ('DaemonSet','kube-system','cilium-envoy'),
    ('Deployment','kube-system','cilium-operator'),
})


def audit_boundary(objects,required_namespaces=()):
    objects=list(flatten(objects))
    namespaces=set(required_namespaces)
    for obj in objects:
        meta=obj.get('metadata',{});name=meta.get('name','')
        namespace=name if obj.get('kind')=='Namespace' else meta.get('namespace','')
        if namespace.startswith('twinfra-'):
            namespaces.add(namespace)
        # Environment/region labels also decorate upstream-owned Namespaces.
        # They are not an ownership marker (for example cilium-secrets).
        if obj.get('kind')=='Namespace' and (meta.get('labels',{}).get('app.kubernetes.io/part-of')=='twinfra' or
                meta.get('labels',{}).get('twinfra.io/managed')=='true'):
            namespaces.add(name)
    denied=set();violations=[];accepted=set()
    for obj in objects:
        kind=obj.get('kind');meta=obj.get('metadata',{});namespace=meta.get('namespace','')
        key=(kind,namespace,meta.get('name'));label='/'.join(str(v) for v in key)
        if namespace not in namespaces and namespace!='kube-system':continue
        spec=obj.get('spec',{})
        if kind=='Service':
            if spec.get('type','ClusterIP') in ('NodePort','LoadBalancer'):
                violations.append(label+': node-exposed Service type forbidden')
            if spec.get('externalIPs'):
                violations.append(label+': externalIPs forbidden')
            if any('nodePort' in port for port in spec.get('ports',[])):
                violations.append(label+': explicit nodePort forbidden')
        pod=podspec(obj)
        if pod is not None:
            host_ports=any('hostPort' in port for category in ('containers','initContainers','ephemeralContainers')
                for container in pod.get(category,[]) for port in container.get('ports',[]))
            if pod.get('hostNetwork',False) or host_ports:
                if key in CILIUM_NODE_EXCEPTIONS:accepted.add(label)
                else:violations.append(label+': hostNetwork/hostPort outside named Cilium node scope')
        # A namespace-wide Kubernetes policy establishes default isolation;
        # separate Cilium/Kubernetes allow policies admit the declared edges.
        if (kind=='NetworkPolicy' and obj.get('apiVersion')=='networking.k8s.io/v1' and
                spec.get('podSelector')=={} and 'Ingress' in spec.get('policyTypes',[]) and
                spec.get('ingress',[])==[]):
            denied.add(namespace)
    for namespace in sorted(namespaces-denied):
        violations.append(namespace+': namespace-wide ingress default-deny missing')
    return dict(status='failed' if violations else 'passed',violations=violations,
        namespaces=sorted(namespaces),ingressDefaultDeny=sorted(namespaces & denied),
        namedNodeExceptions=sorted(accepted))
