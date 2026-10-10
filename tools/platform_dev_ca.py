#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Owner-only temporary dev PKI, outside Git. Replaced by WO-08; never production."""
import argparse
import base64
import calendar
import ctypes
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import stat
import subprocess

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT = Path(__file__).resolve().parents[1]
NS = 'twinfra-platform-services'
PERMITTED_DNS_SUBTREES = ('twinfra.example.com', 'twinfra-platform-services.svc.cluster.local')


def name_constraints():
    return x509.NameConstraints([x509.DNSName(name) for name in PERMITTED_DNS_SUBTREES], None)


def sans(region='cairo-1'):
    if region not in ('cairo-1', 'cairo-2'):
        raise ValueError('Only approved dev regions are supported')
    service = '.twinfra-platform-services.svc.cluster.local'
    return {'twinfra-keycloak-tls': ['auth.dev.' + region + '.twinfra.example.com', 'twinfra-keycloak' + service],
            'twinfra-openbao-tls': ['twinfra-openbao' + service],
            'argocd-secret': ['gitops.dev.' + region + '.twinfra.example.com', 'argocd-server' + service],
            'twinfra-gateway-tls': ['console.dev.' + region + '.twinfra.example.com']}


def key_bytes(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())


def certificate_bytes(cert):
    return cert.public_bytes(serialization.Encoding.PEM)


def generate(region='cairo-1', now=None):
    """In-memory generation also permits tests without writing private material."""
    now = now or datetime.now(timezone.utc)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Twinfra dev CA ' + region)])
    end = now.replace(year=now.year + 10, day=min(now.day, calendar.monthrange(now.year + 10, now.month)[1]))
    ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(ca_key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5)).not_valid_after(end)
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(name_constraints(), critical=True)
          .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
          .sign(ca_key, hashes.SHA256()))
    files = {'ca.crt': certificate_bytes(ca), 'ca.key': key_bytes(ca_key)}
    for secret, hosts in sans(region).items():
        key = ec.generate_private_key(ec.SECP256R1())
        leaf = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hosts[0])]))
                .issuer_name(ca.subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=365))
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .add_extension(x509.SubjectAlternativeName([x509.DNSName(h) for h in hosts]), critical=False)
                .add_extension(x509.KeyUsage(True, False, False, False, False, False, False, False, False), critical=True)
                .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
                .sign(ca_key, hashes.SHA256()))
        files[secret + '.crt'] = certificate_bytes(leaf)
        files[secret + '.key'] = key_bytes(key)
    return files


def outside_repository(path):
    path = path.absolute()
    # Check before and after resolution: a symlink must not bypass the Git boundary.
    for value in (path, path.resolve()):
        if value == ROOT or ROOT in value.parents:
            raise ValueError('Refusing dev CA output inside the Git working tree')
        for parent in [value, *value.parents]:
            if (parent / '.git').exists():
                raise ValueError('Refusing dev CA output inside a Git working tree')
            reparse = parent.exists() and os.name == 'nt' and bool(parent.stat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
            if parent.is_symlink() or reparse:
                raise ValueError('Refusing reparse/symlink CA output path')
    return path


def owner_only(path):
    if os.name != 'nt':
        path.chmod(0o700 if path.is_dir() else 0o600)
        return
    # Native Windows security API; no ACL utility, third-party executable or installation.
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    adv = ctypes.WinDLL('advapi32', use_last_error=True)
    handle = wintypes.HANDLE()
    adv.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    adv.GetTokenInformation.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    if not adv.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(handle)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        size = wintypes.DWORD()
        adv.GetTokenInformation(handle, 1, None, 0, ctypes.byref(size))
        buf = ctypes.create_string_buffer(size.value)
        if not adv.GetTokenInformation(handle, 1, buf, size, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        sid = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]
        string_sid = wintypes.LPWSTR()
        adv.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
        if not adv.ConvertSidToStringSidW(sid, ctypes.byref(string_sid)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            sddl = 'D:P(A;OICI;FA;;;' + string_sid.value + ')'
            sd = ctypes.c_void_p()
            adv.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
            if not adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(sd), None):
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                adv.SetFileSecurityW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
                if not adv.SetFileSecurityW(str(path), 0x80000004, sd):
                    raise ctypes.WinError(ctypes.get_last_error())
            finally:
                kernel.LocalFree(sd)
        finally:
            kernel.LocalFree(string_sid)
    finally:
        kernel.CloseHandle(handle)


def validate(files, region):
    ca = x509.load_pem_x509_certificate(files['ca.crt'])
    key = serialization.load_pem_private_key(files['ca.key'], password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
        raise ValueError('Dev root CA must use EC P-256')
    if ca.public_key().public_numbers() != key.public_key().public_numbers():
        raise ValueError('Dev root CA key differs')
    ca.verify_directly_issued_by(ca)
    if not ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
        raise ValueError('Not a CA')
    try:
        constraint = ca.extensions.get_extension_for_class(x509.NameConstraints)
    except x509.ExtensionNotFound:
        raise ValueError('Dev root CA lacks critical NameConstraints') from None
    permitted = constraint.value.permitted_subtrees
    expected = name_constraints().permitted_subtrees
    if (not constraint.critical or permitted is None or len(permitted) != len(expected)
            or set(permitted) != set(expected) or constraint.value.excluded_subtrees is not None):
        raise ValueError('Dev root CA must have exactly the approved critical DNS NameConstraints and no exclusions')
    for name, hosts in sans(region).items():
        cert = x509.load_pem_x509_certificate(files[name + '.crt'])
        cert.verify_directly_issued_by(ca)
        private = serialization.load_pem_private_key(files[name + '.key'], password=None)
        if cert.public_key().public_numbers() != private.public_key().public_numbers():
            raise ValueError('Dev leaf key differs: ' + name)
        if set(cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)) != set(hosts):
            raise ValueError('Dev leaf SAN differs: ' + name)
        if ExtendedKeyUsageOID.SERVER_AUTH not in cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value:
            raise ValueError('Dev leaf lacks serverAuth: ' + name)
        if cert.not_valid_after_utc <= datetime.now(timezone.utc):
            raise ValueError('Expired dev leaf; rotate deliberately: ' + name)


def write(out, region):
    out = outside_repository(out)
    if out.exists() and any(out.iterdir()):
        files = {name: (out / name).read_bytes() for name in ['ca.crt', 'ca.key'] +
                 [n + suffix for n in sans(region) for suffix in ('.crt', '.key')]}
        validate(files, region)
        owner_only(out)
        for name in files:
            owner_only(out / name)
        return files
    out.mkdir(parents=True, mode=0o700, exist_ok=True)
    owner_only(out)  # Protect the directory before the first private byte is written.
    files = generate(region)
    for name, raw in files.items():
        with (out / name).open('xb') as stream:
            stream.write(raw)
        owner_only(out / name)
    return files


def apply(files, region, context, runner=subprocess.run):
    if context != 'twinfra-dev-' + region:
        raise ValueError('CA application requires the matching explicit dev context')
    validate(files, region)
    for name in sans(region):
        data = {k: base64.b64encode(v).decode() for k, v in
                {'tls.crt': files[name + '.crt'], 'tls.key': files[name + '.key'], 'ca.crt': files['ca.crt']}.items()}
        prefix = ['kubectl', '--context', context, '-n', NS]
        found = runner(prefix + ['get', 'secret', name, '--ignore-not-found', '-o', 'name'], capture_output=True, check=True)
        if found.stdout.strip():
            cmd = prefix + ['patch', 'secret', name, '--type=merge', '--patch-file', '-']
            raw = {'data': data}  # Preserve Argo signing/admin fields and other existing keys.
        else:
            cmd = prefix + ['create', '-f', '-']
            raw = {'apiVersion': 'v1', 'kind': 'Secret', 'metadata': {'name': name, 'namespace': NS,
                   'labels': {'twinfra.io/environment': 'dev', 'twinfra.io/region': region, 'twinfra.io/component': 'dev-ca'}},
                   'type': 'Opaque' if name == 'argocd-secret' else 'kubernetes.io/tls', 'data': data}
        runner(cmd, input=json.dumps(raw).encode(), capture_output=True, check=True)
        print(name)  # Names only; never print payloads, keys or kubectl failure bodies.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--region', choices=['cairo-1', 'cairo-2'], default='cairo-1')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--context')
    args = parser.parse_args()
    if args.apply and args.context != 'twinfra-dev-' + args.region:
        parser.error('--apply needs the matching explicit dev --context')
    files = write(args.out, args.region)
    if args.apply:
        apply(files, args.region, args.context)
    else:
        print('Dev CA and four TLS leaves ready outside Git; owner-only permissions applied')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError):
        raise SystemExit('Dev CA operation failed; check output boundary, owner ACLs, certificate validity and explicit dev context') from None
