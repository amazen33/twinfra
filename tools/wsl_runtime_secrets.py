#!/usr/bin/env python3
"""Create missing lab credentials/TLS with private bytes kept in memory only.

Requires verified K3s encryption at rest. Secrets are create-only, never rotated
or overwritten implicitly. Certificate keys do not touch argv/env/temp files.
"""
import base64
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import secrets
import subprocess
from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

ROOT=Path(__file__).resolve().parents[1]
K=['/usr/local/bin/k3s','kubectl','--kubeconfig=/etc/vcloud-wsl/kubeconfig.yaml','--context=vcloud-wsl-local','--request-timeout=30s','-n','platform-services']


def create(name,data,kind='Opaque'):
    found=subprocess.check_output(K+['get','secret',name,'--ignore-not-found','-o','name'])
    if found.strip():
        print('Preserved Secret/'+name);return
    obj={'apiVersion':'v1','kind':'Secret','type':kind,'metadata':{'name':name,'namespace':'platform-services',
         'labels':{'vcloud.io/environment':'local-validation'}},
         'data':{key:base64.b64encode(value if isinstance(value,bytes) else value.encode()).decode() for key,value in data.items()}}
    result=subprocess.run(K+['create','-f','-'],input=json.dumps(obj).encode(),capture_output=True,check=False)
    if result.returncode:raise RuntimeError('Secret creation failed; details withheld')
    print('Created Secret/'+name+' (values withheld)')


def main():
    subprocess.run(['bash',str(ROOT/'lab/wsl/enable-secret-encryption.sh'),'--check'],check=True)
    for role in ('openbao','keycloak'):
        create('vcloud-wsl-'+role+'-db',{'username':role,'password':secrets.token_urlsafe(48)},'kubernetes.io/basic-auth')
    create('vcloud-wsl-grafana-admin',{'admin-user':'vcloud-admin','admin-password':secrets.token_urlsafe(48)})
    for name,alt in [('openbao',['openbao','openbao.platform-services.svc','openbao.platform-services.svc.cluster.local','localhost']),
                     ('keycloak',['keycloak','keycloak.platform-services.svc','keycloak.platform-services.svc.cluster.local','localhost','auth.vcloud.example.com'])]:
        key=ec.generate_private_key(ec.SECP256R1());now=datetime.now(timezone.utc)
        subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,alt[2])])
        cert=(x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
              .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5))
              .not_valid_after(now+timedelta(days=90)).add_extension(x509.SubjectAlternativeName([x509.DNSName(a) for a in alt]),False)
              .add_extension(x509.BasicConstraints(ca=False,path_length=None),True).sign(key,hashes.SHA256()))
        create('vcloud-wsl-'+name+'-tls',{'tls.crt':cert.public_bytes(serialization.Encoding.PEM),
              'tls.key':key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())},'kubernetes.io/tls')
    print('PASS: runtime credentials created/preserved without plaintext host files or credential environment variables')


if __name__=='__main__':main()
