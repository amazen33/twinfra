#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Execute inside the storage-ui Pod; default read-only, optional explicit lab seed."""
import argparse
import json
import sys
import urllib.request
sys.path.insert(0, '/app')
import ui

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--seed', action='store_true', help='create named empty acceptance resources in both local emulators')
args = parser.parse_args()
for backend, endpoint in ui.ENDPOINTS.items():
    with urllib.request.urlopen(endpoint + '/_' + backend + '/health', timeout=4) as response:
        health = json.load(response)
        assert response.status == 200
    if backend == 'localstack':
        assert all(health['services'][x] == 'running' for x in ('s3', 'ec2', 'iam', 'dynamodb'))
    print(backend + ': health HTTP 200')
    if args.seed:
        # These empty named fixtures cannot reach AWS (fixed service endpoints).
        ui.read(ui.signed_request(backend, 's3', method='PUT', path='/vcloud-console-acceptance'))
        names = json.loads(ui.read(ui.signed_request(backend, 'dynamodb', 'POST', payload=b'{}', target='DynamoDB_20120810.ListTables')))['TableNames']
        if 'vcloud-console-acceptance' not in names:
            create = {'TableName': 'vcloud-console-acceptance', 'AttributeDefinitions': [{'AttributeName': 'id', 'AttributeType': 'S'}],
                      'KeySchema': [{'AttributeName': 'id', 'KeyType': 'HASH'}], 'BillingMode': 'PAY_PER_REQUEST'}
            ui.read(ui.signed_request(backend, 'dynamodb', 'POST', payload=json.dumps(create).encode(), target='DynamoDB_20120810.CreateTable'))
    for view in ('storage', 'dynamodb'):
        html = ui.browser(view, backend)
        assert '<script>' not in html
        if args.seed:
            assert 'vcloud-console-acceptance' in html
            detail = ui.browser(view, backend, 'vcloud-console-acceptance')
            assert 'vcloud-console-acceptance' in detail
        print(backend + ': ' + view + ' signed read/view PASS')
    for service, action, version in [('ec2', 'DescribeInstances', '2016-11-15'), ('iam', 'ListUsers', '2010-05-08')]:
        raw = ui.read(ui.signed_request(backend, service, query={'Action': action, 'Version': version}))
        assert action + 'Response' in raw.decode()
        print(backend + ': ' + action + ' signed API HTTP 200')
print('PASS: dual emulator health, signed S3/EC2/IAM/DynamoDB and read-only views')
