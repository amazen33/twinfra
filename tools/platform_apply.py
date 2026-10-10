"""Apply a reviewed YAML stream using an explicitly supplied transport. MIT."""
import yaml

def apply(values, transport, manager="twinfra-console-bootstrap"):
    raw=yaml.safe_dump_all(values).encode()
    flags=["--server-side","--field-manager="+manager,"--force-conflicts","-f","-"]
    transport(["apply","--dry-run=server"]+flags,raw)
    transport(["apply"]+flags,raw)
