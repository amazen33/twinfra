"""Run inside a restricted init container; private config stays on tmpfs."""
import json
from pathlib import Path
import sys
from urllib.parse import quote

mode=sys.argv[1]
password=Path('/auth/password').read_text()
host='vcloud-wsl-postgres-rw.platform-services.svc.cluster.local'
if mode=='openbao':
    url=f'postgresql://openbao:{quote(password,safe="")}@{host}:5432/openbao?sslmode=verify-full&sslrootcert=/pg-ca/ca.crt'
    text=('ui = true\ndisable_mlock = true\napi_addr = "https://openbao.platform-services.svc.cluster.local:8200"\n'
          'storage "postgresql" {\n connection_url = '+json.dumps(url)+'\n max_parallel = "4"\n}\n'
          'listener "tcp" {\n address = "0.0.0.0:8200"\n cluster_address = "127.0.0.1:8202"\n tls_cert_file = "/tls/tls.crt"\n tls_key_file = "/tls/tls.key"\n}\n'
          '# This listener is reachable only inside the Pod network namespace.\n'
          '# kubectl port-forward binds the operator endpoint to host loopback.\n'
          'listener "tcp" {\n address = "127.0.0.1:8201"\n cluster_address = "127.0.0.1:8203"\n tls_disable = true\n}\n')
    target=Path('/runtime/openbao.hcl')
elif mode=='keycloak':
    # The PostgreSQL JDBC driver verifies the CNPG public CA and service name.
    url=f'jdbc:postgresql://{host}:5432/keycloak?sslmode=verify-full&sslrootcert=/pg-ca/ca.crt'
    text=('db=postgres\ndb-username=keycloak\ndb-password='+password+'\ndb-url='+url+'\n'
          'http-enabled=false\nhttps-certificate-file=/tls/tls.crt\nhttps-certificate-key-file=/tls/tls.key\n'
          'hostname=https://localhost:18443\nhealth-enabled=true\nmetrics-enabled=true\ncache=local\n')
    target=Path('/runtime/keycloak.conf')
else:raise ValueError('Unknown runtime')
target.write_text(text);target.chmod(0o600)
