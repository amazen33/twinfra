#!/usr/bin/env python3
"""Embed the exact bootstrap source as a YAML literal, with no third-party dependency."""
from pathlib import Path
import argparse
import hashlib
import gzip
import sys
import textwrap
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def rendered(artifact_url=None) -> str:
    script = (ROOT / "00-setup-ubuntu-host.sh").read_text(encoding="utf-8")
    template = (ROOT / "cloud-init.template.yaml").read_text(encoding="utf-8")
    host_env = (ROOT / "host.env.example").read_text(encoding="utf-8")
    assert template.count('@@HOST_ENV@@') == 1
    template = template.replace('@@HOST_ENV@@', textwrap.indent(host_env.rstrip('\n'), '      '))
    digest = hashlib.sha256(script.encode()).hexdigest()
    if artifact_url:
        parts = urlsplit(artifact_url)
        if parts.scheme != "https" or not parts.netloc or any(c in artifact_url for c in "\n\r'\"$"):
            raise ValueError("Artifact URL must be a simple HTTPS URL")
        script = textwrap.dedent(f'''\
            #!/usr/bin/env bash
            # Small-provider bootstrap: host the exact companion script at this URL first.
            set -Eeuo pipefail
            expected='{digest}'
            url='{artifact_url}'
            target=/usr/local/sbin/00-setup-ubuntu-host.sh
            if [[ -f $target ]] && [[ $(sha256sum "$target" | cut -d' ' -f1) == "$expected" ]]; then exit 0; fi
            candidate=$(mktemp /var/tmp/vcloud-bootstrap.XXXXXX)
            trap 'rm -f -- "$candidate"' EXIT
            curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 --retry 4 \\
                --connect-timeout 15 --max-time 300 "$url" -o "$candidate"
            printf '%s  %s\\n' "$expected" "$candidate" | sha256sum -c -
            install -m 0755 -o root -g root "$candidate" "$target"
            ''')
        template = template.replace("# The generated user-data.yaml embeds the complete script; it requires no script URL.", "# Remote variant for small user-data limits: publish the script at the HTTPS URL below.")
        template = template.replace("path: /usr/local/sbin/00-setup-ubuntu-host.sh", "path: /usr/local/sbin/vcloud-fetch-host.sh", 1)
        template = template.replace("'/usr/local/sbin/00-setup-ubuntu-host.sh --apply;", "'/usr/local/sbin/vcloud-fetch-host.sh && /usr/local/sbin/00-setup-ubuntu-host.sh --apply;")
    content = "\n".join("      " + line if line else "" for line in script.rstrip("\n").split("\n"))
    assert template.count("@@BOOTSTRAP_SCRIPT@@") == 1
    return template.replace("# Source template.", f"# Generated; script SHA256={digest}.\n# Source template.").replace("@@BOOTSTRAP_SCRIPT@@", content)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if user-data.yaml is stale")
    parser.add_argument("--artifact-url", default="https://artifacts.example.com/vcloud/00-setup-ubuntu-host.sh", help="HTTPS publication URL for user-data-remote.yaml; example URL must be replaced")
    args = parser.parse_args()
    result = rendered()
    remote = rendered(args.artifact_url)
    output = ROOT / "user-data.yaml"
    remote_output = ROOT / "user-data-remote.yaml"
    if args.check:
        if not output.exists() or output.read_text(encoding="utf-8") != result or not remote_output.exists() or remote_output.read_text(encoding="utf-8") != remote:
            print("user-data.yaml is stale; run tools/render_cloud_init.py", file=sys.stderr)
            return 1
        print("Cloud-Init embeds the current script exactly")
    else:
        output.write_text(result, encoding="utf-8", newline="\n")
        (ROOT / "user-data.yaml.gz").write_bytes(gzip.compress(result.encode(), mtime=0))
        remote_output.write_text(remote, encoding="utf-8", newline="\n")
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
