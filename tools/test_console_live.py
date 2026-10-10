#!/usr/bin/env python3
"""Real PKCE/MFA acceptance with an ephemeral realm user, deleted in finally.

Passwords, TOTP seeds, OAuth codes, tokens and cookie jars remain in memory.
Only sanitized check labels and optional public UI screenshots are written.
The operator's vcloud-admin temporary password is neither consumed nor changed.
"""
import argparse
import base64
import hashlib
import hmac
from html.parser import HTMLParser
import http.cookiejar
import json
from pathlib import Path
import secrets
import struct
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from configure_console_identity import guard, profile
from wsl_keycloak_admin import API, ADMIN, ADMIN_SECRET, credential, obj, k

ROOT=Path(__file__).resolve().parents[1]
ORIGIN='http://localhost:18080'
class RoleDenied(ValueError): pass


class Form(HTMLParser):
    def __init__(self, raw):
        super().__init__(); self.action=None; self.fields={}; self.feed(raw)
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag=='form' and self.action is None: self.action=attrs.get('action')
        if tag=='input' and attrs.get('name'):
            self.fields[attrs['name']]=attrs.get('value','')


class LocalRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, url):
        parsed=urllib.parse.urlsplit(url)
        if (parsed.scheme,parsed.hostname,parsed.port) not in {('http','localhost',18080),('https','localhost',18443)}:
            raise ValueError('Unexpected cross-origin redirect')
        return super().redirect_request(req,fp,code,msg,headers,url)


class Session:
    def __init__(self, context):
        self.cookies=http.cookiejar.CookieJar()
        self.opener=urllib.request.build_opener(LocalRedirect(),urllib.request.HTTPCookieProcessor(self.cookies),urllib.request.HTTPSHandler(context=context))
    def request(self,path,data=None,headers=None,method=None):
        url=path if path.startswith('https://localhost:18443/') else ORIGIN+path
        request=urllib.request.Request(url,data=urllib.parse.urlencode(data).encode() if data else None,headers=headers or {},method=method)
        try: response=self.opener.open(request,timeout=15)
        except urllib.error.HTTPError as error: response=error
        with response:
            raw=response.read(1024*1024+1)
            if len(raw)>1024*1024: raise ValueError('Oversized response')
            return response.status,response.url,raw.decode(),response.headers
    def login(self,username,password):
        code,url,html,headers=self.request('/console/overview')
        if '/realms/vcloud/' not in url or code!=200: raise ValueError('Login redirect failed')
        form=Form(html)
        if not form.action: raise ValueError('Login form missing')
        data={**form.fields,'username':username,'password':password}
        code,url,html,headers=self.request(form.action,data)
        if 'totpSecret' in html:
            form=Form(html); seed=form.fields.get('totpSecret')
            if not seed: raise ValueError('MFA setup seed unavailable')
            # Keycloak's hidden totpSecret is the raw UTF-8 secret; the displayed
            # manual setup value is separately Base32-encoded by TotpBean.
            secret=seed.encode()
            digest=hmac.new(secret,struct.pack('>Q',int(time.time())//30),hashlib.sha1).digest()
            offset=digest[-1]&15
            otp=str((struct.unpack('>I',digest[offset:offset+4])[0]&0x7fffffff)%1000000).zfill(6)
            code,url,html,headers=self.request(form.action,{**form.fields,'totp':otp,'userLabel':'vcloud-acceptance'})
        elif 'name="otp"' in html:
            raise ValueError('Unexpected prior MFA state')
        # APISIX returns 401 when its authenticated ID-token claim schema fails;
        # the BFF returns 403 for a valid identity without a permitted client role.
        if code in (401,403) and url.startswith(ORIGIN+'/console/'):
            raise RoleDenied('Authenticated callback denied by gateway role policy')
        if code!=200 or not url.startswith(ORIGIN+'/console/') or '<title>Twinfra' not in html:
            raise ValueError('Authenticated callback failed (HTTP '+str(code)+', portal origin '+str(url.startswith(ORIGIN+'/console/'))+')')
        return headers


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser',help='Optional Windows browser executable; cookies passed only through process stdin')
    args=parser.parse_args(); guard(); api=API(); p=profile()
    token=api.login(ADMIN,credential(obj(['get','secret',ADMIN_SECRET,'-o','json']),ADMIN))
    call=lambda path,**kwargs:api.request('/admin/realms/vcloud'+path,token,**kwargs)
    cid=call('/clients?clientId=vcloud-console')[0]['id']
    name='console-acceptance-'+uuid.uuid4().hex[:12]; password=secrets.token_urlsafe(48); uid=None
    try:
        # Never replay an operator callback. Synthetic codes are discarded when
        # no valid browser session exists; they must not reach a token exchange.
        for headers in ({}, {'Cookie':'vcloud_portal=invalid'}):
            missing=Session(api.context)
            code,_,body,response_headers=missing.request('/console/callback?code=synthetic-unused-code&state=synthetic-unused-state',headers=headers)
            if code!=401 or 'Start sign-in again' not in body or 'synthetic-unused-code' in body or response_headers.get('Cache-Control')!='no-store' or response_headers.get('Referrer-Policy')!='no-referrer':
                raise ValueError('Missing/malformed callback session did not fail closed with recovery')
        print('PASS: missing and malformed callback sessions -> HTTP 401; fixed fresh-login link; no reflected codes',flush=True)
        call('/users',method='POST',value={'username':name,'enabled':True,'requiredActions':['CONFIGURE_TOTP'],
            'credentials':[{'type':'password','value':password,'temporary':False}]})
        uid=call('/users?username='+name+'&exact=true')[0]['id']
        role=call('/clients/'+cid+'/roles/console.viewer')
        call('/users/'+uid+'/role-mappings/clients/'+cid,method='POST',value=[role])
        session=Session(api.context)
        code,_,_,_=session.request('/console/api/identity')
        if code!=401: raise ValueError('Anonymous API not denied')
        print('PASS: anonymous API -> HTTP 401',flush=True)
        forged=base64.b64encode(json.dumps({'iss':p['issuer'],'aud':p['client'],'exp':time.time()+60,
            'sub':'forged','resource_access':{p['client']:{'roles':['console.admin']}}}).encode()).decode()
        code,_,_,_=session.request('/console/api/identity',headers={'X-ID-Token':forged,'X-Userinfo':forged})
        if code!=401: raise ValueError('Spoofed identity header reached the API')
        print('PASS: spoofed identity headers -> HTTP 401',flush=True)
        session.login(name,password)
        print('PASS: actual confidential code/PKCE callback with mandatory TOTP enrollment',flush=True)
        for path in ('identity','overview','gitops','storage?backend=ministack',
                     'dynamodb?backend=ministack','cloud?backend=ministack'):
            code,_,body,_=session.request('/console/api/'+path)
            if code!=200: raise ValueError('Read-only API failed: '+path)
            json.loads(body)
            print('PASS: '+path+' -> HTTP 200',flush=True)
        code,_,_,_=session.request('/console/api/cloud',data={'operation':'denied'},method='POST')
        if code!=405: raise ValueError('Authenticated write operation was not denied')
        print('PASS: authenticated API write -> HTTP 405',flush=True)
        for path in ('storage','dynamodb'):
            code,_,body,headers=session.request('/console/proxy/'+path+'/?backend=ministack')
            if code!=200 or headers.get('X-Frame-Options')!='SAMEORIGIN' or "frame-ancestors 'self'" not in headers.get('Content-Security-Policy',''):
                raise ValueError('Same-origin legacy view failed')
            if '/console/proxy/'+path+'/console.css' not in body: raise ValueError('Legacy asset path escaped prefix')
            print('PASS: same-origin '+path+' view and framing headers',flush=True)
        if args.browser:
            browser_name='console-browser-'+uuid.uuid4().hex[:12]; browser_id=None
            browser_password=secrets.token_urlsafe(48)
            try:
                actions=call('/authentication/required-actions')
                if not any(a['alias']=='UPDATE_PASSWORD' and a.get('enabled') for a in actions):
                    raise ValueError('Enabled temporary password change provider required')
                call('/users',method='POST',value={'username':browser_name,'enabled':True,
                    'requiredActions':['UPDATE_PASSWORD','CONFIGURE_TOTP'],
                    'credentials':[{'type':'password','value':browser_password,'temporary':True}]})
                browser_id=call('/users?username='+browser_name+'&exact=true')[0]['id']
                call('/users/'+browser_id+'/role-mappings/clients/'+cid,method='POST',value=[role])
                certificate=base64.b64decode(k(['get','secret','vcloud-wsl-keycloak-tls','-o','jsonpath={.data.tls\\.crt}'])).decode()
                value={'origin':ORIGIN,'browser':args.browser,'username':browser_name,'password':browser_password,
                    'newPassword':secrets.token_urlsafe(48),'certificate':certificate}
                proc=subprocess.run(['/mnt/c/Program Files/nodejs/node.exe','E:/vCloud/console/browser-login.mjs'],
                    input=json.dumps(value).encode(),capture_output=True,timeout=150)
                # Browser exceptions may contain private OAuth URLs. Only a
                # fixed stage classifier or known PASS labels may escape RAM.
                if proc.returncode:
                    safe=next((line for line in proc.stdout.decode(errors='replace').splitlines()
                        if line.startswith('FAIL: browser login stage ') and all(c.isalnum() or c in ' :;_' for c in line)),None)
                    raise ValueError(safe or 'Full browser login failed; private output withheld')
                if call('/users/'+browser_id).get('requiredActions'):
                    raise ValueError('Browser left required actions incomplete')
                print('PASS: actual browser first login, password change, TOTP enrollment and returning MFA login; required actions complete',flush=True)
            finally:
                if browser_id: call('/users/'+browser_id,method='DELETE')
            cookies=[{'name':c.name,'value':c.value,'domain':'localhost','path':c.path,'httpOnly':True,'sameSite':'Lax'} for c in session.cookies if c.name.startswith('vcloud_portal')]
            value={'origin':ORIGIN,'cookies':cookies,'browser':args.browser,'output':'E:/vCloud/.build/console/screenshots'}
            proc=subprocess.run(['/mnt/c/Program Files/nodejs/node.exe','E:/vCloud/console/browser-acceptance.mjs'],
                input=json.dumps(value).encode(),capture_output=True,timeout=120)
            if proc.returncode:
                safe=next((line for line in proc.stdout.decode(errors='replace').splitlines()
                    if line.startswith('FAIL: browser stage ') and all(c.isalnum() or c in ' :;-_' for c in line)),None)
                for line in proc.stdout.decode(errors='replace').splitlines():
                    if line.startswith('STATUS: ') and all(c.isalnum() or c in ' =:-' for c in line): print(line,flush=True)
                raise ValueError(safe or 'Browser acceptance failed; private process output withheld')
            print('PASS: authenticated Windows browser navigation; six views; mobile/desktop screenshots',flush=True)
        session.request('/console/logout')
        code,_,_,_=session.request('/console/api/identity')
        if code!=401: raise ValueError('Logout did not deny the session')
        print('PASS: logout -> API HTTP 401',flush=True)
        # TOTP seed is not persisted; use a separate roleless acceptance user.
        roleless=name+'-denied'; denied_id=None
        try:
            call('/users',method='POST',value={'username':roleless,'enabled':True,'requiredActions':['CONFIGURE_TOTP'],
                'credentials':[{'type':'password','value':password,'temporary':False}]})
            denied_id=call('/users?username='+roleless+'&exact=true')[0]['id']
            denied=Session(api.context)
            try: denied.login(roleless,password)
            except RoleDenied:
                code,_,_,_=denied.request('/console/api/identity')
                if code not in (401,403): raise ValueError('Roleless session was not denied')
            else: raise ValueError('Roleless user reached portal HTML')
            print('PASS: authenticated roleless user denied portal access',flush=True)
        finally:
            if denied_id: call('/users/'+denied_id,method='DELETE')
    finally:
        if uid: call('/users/'+uid,method='DELETE')
    print('PASS: ephemeral acceptance users removed; operator temporary password preserved',flush=True)


if __name__=='__main__':
    try: main()
    except Exception as error:
        print('FAIL: '+(str(error) if isinstance(error,ValueError) else type(error).__name__)+'; private details withheld',flush=True)
        raise SystemExit(1)
