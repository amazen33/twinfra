#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Etcd snapshot CMS encryption and R2 upload; no private key or credential files."""
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys
import urllib.request

TOKEN=Path('/var/run/secrets/kubernetes.io/serviceaccount/token')
CA=TOKEN.parent/'ca.crt'
NS='twinfra-platform-services'
OPENSSL='/usr/bin/openssl'


def checked(args, data=None):
    result=subprocess.run(args,input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if result.returncode:raise ValueError('OpenSSL validation/encryption failed')
    return result.stdout


def api(path, method='GET', value=None):
    body=None if value is None else json.dumps(value).encode()
    request=urllib.request.Request('https://kubernetes.default.svc'+path,data=body,method=method,
        headers={'Authorization':'Bearer '+TOKEN.read_text().strip(),'Content-Type':'application/merge-patch+json'})
    with urllib.request.urlopen(request,context=ssl.create_default_context(cafile=str(CA)),timeout=15) as response:
        return json.load(response)


def configuration(path):
    site=json.loads(path.read_text())
    if site['namespace']!=NS or site['environment']!='twinfra-dev-cairo-1':raise ValueError('Wrong backup environment')
    if not re.fullmatch(r'https://[a-z0-9.-]+\.r2\.cloudflarestorage\.com',site['endpointURL']):raise ValueError('Unapproved R2 endpoint')
    if site['bucket']!='twinfra-dev-cairo-1-backups' or site['etcdPrefix']!='etcd/twinfra-dev-cairo-1':raise ValueError('Unapproved bucket/prefix')
    if site['credentialSecret']!='twinfra-backup-s3' or site['retentionDays']!=7:raise ValueError('Unapproved credential/retention scope')
    return site


def credentials(site):
    value=api('/api/v1/namespaces/'+NS+'/secrets/'+site['credentialSecret'])['data']
    return {key:base64.b64decode(value[key],validate=True) for key in
            ('ACCESS_KEY_ID','ACCESS_SECRET_KEY')}


def public_certificate(path):
    raw=path.read_bytes()
    if len(raw)>65536 or b'PRIVATE KEY' in raw or not raw.startswith(b'-----BEGIN CERTIFICATE-----'):
        raise ValueError('Only a public CMS recipient certificate is permitted')
    checked([OPENSSL,'x509','-in',str(path),'-noout','-checkend','0'])
    public=checked([OPENSSL,'x509','-in',str(path),'-pubkey','-noout'])
    text=checked([OPENSSL,'pkey','-pubin','-text','-noout'],public).decode()
    rsa=re.search(r'Public-Key: \((\d+) bit\)',text)
    if not (rsa and int(rsa[1])>=4096 or 'ASN1 OID: prime256v1' in text):
        raise ValueError('CMS requires RSA >=4096 bits or ECDH P-256')


def encryption_mode(certificate):
    # Probe CMS, not just the generic cipher catalogue. Invalid certificates or
    # generic errors never trigger an automatic downgrade.
    result=subprocess.run([OPENSSL,'cms','-encrypt','-binary','-outform','DER',
                           '-aes-256-gcm',str(certificate)],input=b'CMS capability probe',
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if result.returncode==0:return 'AES-256-GCM'
    message=result.stderr.decode(errors='replace').lower()
    unsupported=('unknown cipher','unsupported cipher','cipher not supported','unsupported content encryption')
    if not any(part in message for part in unsupported):raise ValueError('CMS GCM capability probe failed')
    return 'AES-256-CBC'


def checksum(path):
    result=hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda:stream.read(1024*1024),b''):result.update(part)
    return result.hexdigest()


def encrypt(plain, certificate, destination):
    if plain.stat().st_size>256*1024*1024:raise ValueError('Snapshot exceeds the bounded memory-volume budget')
    mode=encryption_mode(certificate)
    checked([OPENSSL,'cms','-encrypt','-binary','-outform','DER','-in',str(plain),
             '-out',str(destination),'-aes-256-gcm' if mode=='AES-256-GCM' else '-aes-256-cbc',str(certificate)])
    if not destination.is_file() or destination.stat().st_size==0:raise ValueError('Empty encrypted snapshot')
    return mode


def s3_client(site, secret):
    import boto3
    from botocore.config import Config
    return boto3.client('s3',endpoint_url=site['endpointURL'],region_name='auto',verify=True,
        aws_access_key_id=secret['ACCESS_KEY_ID'].decode(),aws_secret_access_key=secret['ACCESS_SECRET_KEY'].decode(),
        config=Config(signature_version='s3v4',connect_timeout=10,read_timeout=60,retries={'max_attempts':3},
                      s3={'addressing_style':'path'},request_checksum_calculation='when_required',
                      response_checksum_validation='when_required'))


def verify_object(client, bucket, key, expected):
    body=client.get_object(Bucket=bucket,Key=key)['Body']
    try:
        result=hashlib.sha256()
        for part in iter(lambda:body.read(1024*1024),b''):result.update(part)
    finally:body.close()
    if result.hexdigest()!=expected:raise ValueError('R2 round-trip checksum mismatch')


def retain(client, site, now):
    prefix=site['etcdPrefix']+'/'
    for page in client.get_paginator('list_objects_v2').paginate(Bucket=site['bucket'],Prefix=prefix):
        for item in page.get('Contents',[]):
            relative=item['Key'].removeprefix(prefix)
            if not re.fullmatch(r'snapshot-\d{8}T\d{6}Z\.db\.cms(?:\.manifest\.json)?',relative):continue
            if item['LastModified']<now-timedelta(days=7):
                client.delete_object(Bucket=site['bucket'],Key=item['Key'])


def upload(client, site, encrypted, manifest):
    key=site['etcdPrefix']+'/'+encrypted.name
    with encrypted.open('rb') as body:
        client.put_object(Bucket=site['bucket'],Key=key,Body=body,ContentLength=encrypted.stat().st_size,
                          ContentType='application/pkcs7-mime',Metadata={'sha256':manifest['encryptedSHA256']})
    raw=json.dumps(manifest,sort_keys=True).encode()
    client.put_object(Bucket=site['bucket'],Key=key+'.manifest.json',Body=raw,ContentType='application/json')
    verify_object(client,site['bucket'],key,manifest['encryptedSHA256'])
    verify_object(client,site['bucket'],key+'.manifest.json',hashlib.sha256(raw).hexdigest())
    return key


def perform(site, directory=Path('/backup')):
    os.umask(0o077)
    secret=credentials(site);certificate=Path('/recipient/certificate.pem')
    public_certificate(certificate)
    plain=directory/'snapshot.db';snapshot_time=datetime.fromtimestamp(plain.stat().st_mtime,timezone.utc)
    now=datetime.now(timezone.utc)
    if snapshot_time>now or now-snapshot_time>timedelta(minutes=30):raise ValueError('Snapshot time is stale or in the future')
    encrypted=directory/('snapshot-'+snapshot_time.strftime('%Y%m%dT%H%M%SZ')+'.db.cms')
    plain_hash=checksum(plain);mode=encrypt(plain,certificate,encrypted)
    manifest={'format':'CMS DER','mode':mode,'snapshotTime':snapshot_time.isoformat(),
              'plaintextSHA256':plain_hash,'encryptedSHA256':checksum(encrypted),
              'opensslVersion':checked([OPENSSL,'version']).decode().strip()}
    plain.unlink()  # Never upload the plaintext; tmpfs is removed with the Pod on failure.
    client=s3_client(site,secret);key=upload(client,site,encrypted,manifest)
    retain(client,site,now)
    api('/api/v1/namespaces/'+NS+'/configmaps/twinfra-backup-status','PATCH',
        {'data':{'etcdSnapshotTime':snapshot_time.isoformat(),'etcdObject':key,
                 'etcdEncryptedSHA256':manifest['encryptedSHA256'],'etcdMode':mode}})
    return {'status':'passed','mode':mode,'remoteVerified':True}


def main():
    try:
        print(json.dumps(perform(configuration(Path('/config/backup-config.json')))));return 0
    except Exception as error:
        # SDK/OpenSSL exception text may contain request or credential material.
        print(json.dumps({'status':'failed','errorType':type(error).__name__}));return 1


if __name__=='__main__':sys.exit(main())
