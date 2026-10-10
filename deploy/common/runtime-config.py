"""Run inside a restricted init container; private config stays on tmpfs."""
import json
from pathlib import Path
import sys
from urllib.parse import quote

import os


def configure(mode, root=Path('/')):
    def p(value):
        return root / value.lstrip('/')
    password=p('/auth/password').read_text().strip()
    if not password or any(c in password for c in '\r\n'):raise ValueError('Invalid credential format')
    host=os.environ.get('POSTGRES_HOST','twinfra-postgres-rw.twinfra-platform-services.svc.cluster.local')
    if mode=='openbao':
        url=f'postgresql://openbao:{quote(password,safe="")}@{host}:5432/openbao?sslmode=verify-full&sslrootcert=/pg-ca/ca.crt'
        text=('ui = true\ndisable_mlock = true\napi_addr = "https://twinfra-openbao.twinfra-platform-services.svc.cluster.local:8200"\n'
              'storage "postgresql" {\n connection_url = '+json.dumps(url)+'\n max_parallel = "4"\n}\n'
              'listener "tcp" {\n address = "0.0.0.0:8200"\n cluster_address = "127.0.0.1:8202"\n tls_cert_file = "/tls/tls.crt"\n tls_key_file = "/tls/tls.key"\n}\n'
              '# This listener is reachable only inside the Pod network namespace.\n'
              '# kubectl port-forward binds the operator endpoint to host loopback.\n'
              'listener "tcp" {\n address = "127.0.0.1:8201"\n cluster_address = "127.0.0.1:8203"\n tls_disable = true\n}\n')
        target=p('/runtime/openbao.hcl')
    elif mode=='keycloak':
        # The PostgreSQL JDBC driver verifies the CNPG public CA and service name.
        url=f'jdbc:postgresql://{host}:5432/keycloak?sslmode=verify-full&sslrootcert=/pg-ca/ca.crt'
        text=('db=postgres\ndb-username=keycloak\ndb-password='+password+'\ndb-url='+url+'\n'
              'http-enabled=false\nhttps-certificate-file=/tls/tls.crt\nhttps-certificate-key-file=/tls/tls.key\n'
              # Keep the browser issuer stable; allow TLS-verified Service backchannels.
              'hostname='+os.environ.get('KEYCLOAK_ORIGIN','https://auth.dev.cairo-1.twinfra.example.com:18443')+'\nhostname-backchannel-dynamic=true\nhealth-enabled=true\nmetrics-enabled=true\ncache=local\n')
        text += 'bootstrap-admin-username='+p('/admin/username').read_text().strip()+'\nbootstrap-admin-password='+p('/admin/password').read_text().strip()+'\n'
        realm=json.loads(p('/realm-source/twinfra-realm.json').read_text())
        realm['clients'][0]['secret']=p('/oidc/client_secret').read_text().strip()
        import_dir=p('/import');import_dir.mkdir(exist_ok=True)
        imported=import_dir/'twinfra-realm.json';imported.write_text(json.dumps(realm));imported.chmod(0o600)
        target=p('/runtime/keycloak.conf')
    else:raise ValueError('Unknown runtime')
    target.write_text(text);target.chmod(0o600)


if __name__ == '__main__':
    configure(sys.argv[1])
