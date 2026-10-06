#!/usr/bin/env bash
# Vetted, finite 4-GiB local PV. Root formats/mounts only this new owned lab image.
# Existing/unowned files, data directories and symlinks are never adopted.
set -euo pipefail
umask 077
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
ACTION=${1:---check}
[[ $ACTION == --check || $ACTION == --apply ]] || exit 2
[[ $EUID == 0 ]] && [[ $(uname -r) == *microsoft* ]] && [[ -f /var/lib/vcloud-wsl/owner.json ]] || { printf 'Owned WSL lab required\n' >&2; exit 1; }
IMAGE=/var/lib/vcloud-wsl/volumes/postgres-1.ext4
DIRECTORY=/var/lib/vcloud-wsl/storage/postgres-1
MARKER=/var/lib/vcloud-wsl/storage-owner.json
[[ ! -L $IMAGE && ! -L $DIRECTORY && ! -L /var/lib/vcloud-wsl/volumes && ! -L /var/lib/vcloud-wsl/storage ]] || exit 1
if [[ $ACTION == --apply ]]; then
    if [[ ! -f $MARKER ]]; then
        [[ ! -e $IMAGE && ! -e $DIRECTORY ]] || { printf 'Refusing unowned storage adoption\n' >&2; exit 1; }
        install -d -m 0700 /var/lib/vcloud-wsl/volumes /var/lib/vcloud-wsl/storage
        printf '{"path":"%s","image":"%s","bytes":4294967296,"scope":"user-authorized local database"}\n' "$DIRECTORY" "$IMAGE" > "$MARKER"
    fi
    python3 - "$MARKER" <<'PY'
import json,sys
v=json.load(open(sys.argv[1]))
assert v['path']=='/var/lib/vcloud-wsl/storage/postgres-1' and v['image']=='/var/lib/vcloud-wsl/volumes/postgres-1.ext4' and v['bytes']==4294967296
PY
    if [[ ! -e $IMAGE ]]; then
        fallocate -l 4G "$IMAGE"
        chmod 0600 "$IMAGE"
        mkfs.ext4 -q -m 0 -L vcloud-wsl-pg "$IMAGE"
    fi
    [[ $(stat -c %s "$IMAGE") == 4294967296 && $(blkid -o value -s TYPE "$IMAGE") == ext4 ]] || exit 1
    install -d -m 0700 "$DIRECTORY"
    UNIT=$(systemd-escape --path --suffix=mount "$DIRECTORY")
    cat > "/etc/systemd/system/$UNIT" <<UNIT
[Unit]
Description=Vetted vCloud WSL PostgreSQL local PV
Before=k3s.service
[Mount]
What=$IMAGE
Where=$DIRECTORY
Type=ext4
Options=loop,noatime,nodev,nosuid,noexec
[Install]
WantedBy=multi-user.target
UNIT
    install -d -m 0755 /etc/systemd/system/k3s.service.d
    printf '[Unit]\nRequiresMountsFor=%s\n' "$DIRECTORY" > /etc/systemd/system/k3s.service.d/local-storage.conf
    systemctl daemon-reload
    systemctl enable --now "$UNIT"
    chown 26:26 "$DIRECTORY"
    chmod 0700 "$DIRECTORY"
fi
mountpoint -q "$DIRECTORY" || { printf 'Dedicated filesystem missing\n' >&2; exit 1; }
[[ $(findmnt -n -M "$DIRECTORY" -o FSTYPE) == ext4 && $(stat -c %u:%g "$DIRECTORY") == 26:26 && $(stat -c %a "$DIRECTORY") == 700 ]] || exit 1
mkdir -p "$ROOT/.build/wsl-platform"
python3 - "$DIRECTORY" "$IMAGE" "$ROOT/.build/wsl-platform/storage-vetting.json" <<'PY'
from datetime import datetime,timezone
import json,os,pathlib,subprocess,sys
directory,image,output=sys.argv[1:]
fs=os.statvfs(directory)
v={'status':'passed','timestampUTC':datetime.now(timezone.utc).isoformat(),'node':'vcloud-wsl-local',
 'path':directory,'backingImage':image,'backingBytes':os.stat(image).st_size,'filesystem':'ext4',
 'filesystemBytes':fs.f_blocks*fs.f_frsize,'availableBytes':fs.f_bavail*fs.f_frsize,
 'uid':26,'gid':26,'mode':'0700','reclaimPolicy':'Retain','expansionEnabled':False,
 'mountOptions':subprocess.check_output(['findmnt','-n','-M',directory,'-o','OPTIONS'],text=True).strip()}
if v['backingBytes']!=4294967296:raise SystemExit('Storage size differs')
pathlib.Path(output).write_text(json.dumps(v,indent=2)+'\n')
print('Local storage vetted: finite 4 GiB ext4 image, UID/GID 26, Retain')
PY
