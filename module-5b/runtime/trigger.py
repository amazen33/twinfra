#!/usr/bin/env python3
"""Tekton's baked trigger client; feature flag checked before TLS/file/network I/O."""
import json
import os
from pathlib import Path
import ssl
import urllib.request


def dispatch(request, enabled, transport):
    if enabled != 'true':
        if enabled != 'false':
            raise ValueError('Invalid feature flag')
        return {'status': 'disabled', 'offload_enabled': False}
    return transport(request)


def main():
    def send(body):
        from server import NoRedirect
        context = ssl.create_default_context(cafile='/var/run/vcloud/trigger/ca.crt')
        context.load_cert_chain('/var/run/vcloud/trigger/tls.crt', '/var/run/vcloud/trigger/tls.key')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(), urllib.request.HTTPSHandler(context=context))
        request = urllib.request.Request('https://vcloud-spinifex-bridge.hpc-compute.svc.cluster.local:8443/hooks/capacity',
            data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
        with opener.open(request, timeout=30) as response:
            return json.loads(response.read(65536))
    payload = json.loads(os.environ['CAPACITY_REQUEST_JSON'])
    result = dispatch(payload, os.environ.get('SPINIFEX_OFFLOAD_ENABLED', 'false'), send)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
