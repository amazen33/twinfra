#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Owner-only temporary restore LV. Never operates on the production PostgreSQL LV."""
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import uuid

VG='ubuntu-vg'
NAME='twinfra-restore-drill'
DEVICE='/dev/'+VG+'/'+NAME
MOUNT=Path('/var/lib/twinfra/local-pv/restore-drill')
RECEIPT=Path('/var/lib/twinfra/restore-storage.json')
SIZE=20*1024**3


def command(args, optional=False):
    result=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    if result.returncode and not optional:raise ValueError(args[0]+' failed; no automatic recovery/deletion')
    return result.stdout if result.returncode==0 else ''


def record():
    if not RECEIPT.exists():return None
    info=RECEIPT.lstat()
    if stat.S_ISLNK(info.st_mode) or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o600:
        raise ValueError('Unsafe restore ownership receipt')
    value=json.loads(RECEIPT.read_text())
    if value.get('owner')!='WO-09' or value.get('device')!=DEVICE or value.get('mount')!=str(MOUNT):
        raise ValueError('Unrecognized restore ownership')
    if not re.fullmatch(r'[a-f0-9]{32}',value.get('nonce','')):raise ValueError('Invalid restore ownership nonce')
    return value


def save(value):
    RECEIPT.parent.mkdir(parents=True,exist_ok=True)
    pending=RECEIPT.with_suffix('.tmp')
    with pending.open('x') as stream:json.dump(value,stream)
    os.chmod(pending,0o600);pending.replace(RECEIPT)


def inspect():
    data=json.loads(command(['lvs','--reportformat','json','--units','b','--nosuffix','-o','lv_name,vg_name,lv_uuid,lv_size,lv_tags']))
    rows=[v for section in data['report'] for v in section['lv'] if v['lv_name']==NAME and v['vg_name']==VG]
    if len(rows)>1:raise ValueError('Duplicate restore LVs')
    vgs=json.loads(command(['vgs',VG,'--reportformat','json','--units','b','--nosuffix','-o','vg_free']))
    free=int(float(vgs['report'][0]['vg'][0]['vg_free']))
    mounts=json.loads(command(['findmnt','--json','--output','SOURCE,TARGET,UUID,OPTIONS']))
    return {'lv':rows[0] if rows else None,'free':free,'receipt':record(),'mounts':mounts.get('filesystems',[])}


def validate(state, mode):
    owned=state['receipt'];lv=state['lv']
    def walk(rows):
        for row in rows:
            yield row
            yield from walk(row.get('children',[]))
    for row in walk(state['mounts']):
        if row.get('target')==str(MOUNT) and row.get('source') not in (
                DEVICE,'/dev/mapper/ubuntu--vg-twinfra--restore--drill'):
            raise ValueError('Foreign filesystem occupies the restore mountpoint')
    if lv:
        if not owned or 'twinfra-restore-'+owned['nonce'] not in lv['lv_tags'].split(','):
            raise ValueError('Existing restore LV is not owned; refusing adoption')
        if int(float(lv['lv_size']))!=SIZE or owned.get('lvUuid',lv['lv_uuid'])!=lv['lv_uuid']:
            raise ValueError('Restore LV UUID/size changed')
    elif owned and owned.get('lvUuid'):raise ValueError('Owned restore LV disappeared; manual inspection required')
    if not lv and state['free']<SIZE+20*1024**3:raise ValueError('Restore LV must preserve 20 GiB free VG reserve')
    if mode=='remove' and (not lv or not owned):raise ValueError('No owned restore LV to remove')
    return {'status':'planned','device':DEVICE,'mount':str(MOUNT),'bytes':SIZE,'existing':bool(lv),'mode':mode}


def paths_safe():
    if MOUNT.is_symlink():raise ValueError('Linked restore mountpoint forbidden')
    for path in (*MOUNT.parents,RECEIPT.parent):
        if path.is_symlink():raise ValueError('Linked restore path forbidden')
        if path.exists() and (path.stat().st_uid!=0 or path.stat().st_mode&0o022):
            raise ValueError('Untrusted restore parent/path')


def mounts_for_device(rows):
    result=[]
    for row in rows:
        if row.get('source') in (DEVICE,'/dev/mapper/ubuntu--vg-twinfra--restore--drill'):
            result.append(row)
        result+=mounts_for_device(row.get('children',[]))
    return result


def remove(state):
    # API failures must block cleanup; only an empty successful response means absent.
    cli=['kubectl','--kubeconfig=/etc/kubernetes/admin.conf','get']
    for kind in ('namespace','pv'):
        if command(cli+[kind,NAME,'--ignore-not-found','-o','json']).strip():
            raise ValueError('Delete the restore namespace and its PV before removing the LV')
    owned=state['receipt']
    if (not owned.get('filesystemUuid') or
            command(['blkid','-s','UUID','-o','value',DEVICE]).strip()!=owned['filesystemUuid'] or
            command(['blkid','-s','TYPE','-o','value',DEVICE]).strip()!='ext4' or
            command(['blkid','-s','LABEL','-o','value',DEVICE]).strip()!='twinfra-restore'):
        raise ValueError('Restore filesystem identity changed; refusing deletion')
    used=mounts_for_device(state['mounts'])
    if any(v['target']!=str(MOUNT) for v in used):raise ValueError('Restore LV has a foreign mount')
    if used:command(['umount',str(MOUNT)])
    current=inspect();validate(current,'remove')
    if mounts_for_device(current['mounts']):raise ValueError('Restore LV remains mounted')
    command(['lvremove','--yes',DEVICE]);RECEIPT.unlink()
    if MOUNT.exists():MOUNT.rmdir()
    return {'status':'passed','removed':DEVICE}


def apply(state):
    owned=state['receipt']
    if not owned:
        if MOUNT.exists() and any(MOUNT.iterdir()):raise ValueError('Unowned restore directory is not empty')
        owned={'owner':'WO-09','device':DEVICE,'mount':str(MOUNT),'nonce':uuid.uuid4().hex}
        save(owned)
    if not state['lv']:
        command(['lvcreate','--yes','--size','20G','--name',NAME,'--addtag','twinfra-restore-'+owned['nonce'],VG])
        state=inspect();validate(state,'apply');owned['lvUuid']=state['lv']['lv_uuid'];save(owned)
    existing_uuid=command(['blkid','-s','UUID','-o','value',DEVICE],optional=True).strip()
    if existing_uuid:
        filesystem=command(['blkid','-s','TYPE','-o','value',DEVICE]).strip()
        label=command(['blkid','-s','LABEL','-o','value',DEVICE]).strip()
        if filesystem!='ext4' or label!='twinfra-restore':raise ValueError('Unrecognized restore filesystem')
    if not existing_uuid:
        if owned.get('filesystemUuid'):raise ValueError('Owned restore filesystem disappeared')
        command(['mkfs.ext4','-L','twinfra-restore',DEVICE])
        existing_uuid=command(['blkid','-s','UUID','-o','value',DEVICE]).strip()
    if owned.get('filesystemUuid',existing_uuid)!=existing_uuid:raise ValueError('Restore filesystem UUID changed')
    owned['filesystemUuid']=existing_uuid;save(owned)
    current=inspect();validate(current,'apply')
    used=mounts_for_device(current['mounts'])
    if any(v['target']!=str(MOUNT) for v in used):raise ValueError('Foreign mount of restore LV')
    if any(not {'nosuid','nodev','noexec','noatime'}.issubset(set(v.get('options','').split(','))) for v in used):
        raise ValueError('Restore mount options changed')
    if not used:
        MOUNT.mkdir(parents=True,exist_ok=True)
        if any(MOUNT.iterdir()):raise ValueError('Restore mountpoint hides existing files')
        command(['mount','-t','ext4','-o','nosuid,nodev,noexec,noatime',DEVICE,str(MOUNT)])
    os.chown(MOUNT,26,26);os.chmod(MOUNT,0o700)
    return {'status':'passed','device':DEVICE,'mount':str(MOUNT),'filesystemUuid':existing_uuid,'temporary':True}


def main():
    try:
        if os.geteuid()!=0:raise ValueError('Restore LV operations require the owner sudo boundary')
        request=json.loads(sys.argv[1])
        if request.get('context')!='twinfra-dev-cairo-1':raise ValueError('Wrong restore context')
        mode=request.get('mode')
        if mode not in ('plan','apply','remove'):raise ValueError('Unknown restore storage mode')
        import fcntl
        os.umask(0o077)
        with open('/run/twinfra-restore-storage.lock','a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            paths_safe();state=inspect();result=validate(state,mode)
            if mode=='apply':result=apply(state)
            if mode=='remove':result=remove(state)
        print(json.dumps(result));return 0
    except (ValueError,OSError,KeyError) as error:
        print(json.dumps({'status':'failed','reason':str(error)}));return 1


if __name__=='__main__':sys.exit(main())
