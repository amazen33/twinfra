#!/usr/bin/env python3
"""Run inside LocalStack: fixed loopback target and explicitly fake AWS credentials."""
import json
from urllib.request import urlopen
import boto3
from botocore.config import Config

EXPECTED=('s3','ec2','iam','dynamodb')


def check_health(data):
    states={name:data.get('services',{}).get(name) for name in EXPECTED}
    if any(value!='running' for value in states.values()):
        raise RuntimeError('Configured AWS APIs are not all running: '+json.dumps(states))
    return states


def main():
    session=boto3.Session(aws_access_key_id='test',aws_secret_access_key='test',region_name='us-east-1')
    config=Config(connect_timeout=3,read_timeout=10,retries={'max_attempts':0})
    operations={'s3':'list_buckets','ec2':'describe_instances','iam':'list_users','dynamodb':'list_tables'}
    result={}
    for service,operation in operations.items():
        client=session.client(service,endpoint_url='http://127.0.0.1:4566',config=config)
        code=getattr(client,operation)()['ResponseMetadata']['HTTPStatusCode']
        if code!=200:raise RuntimeError(service+' API did not return HTTP 200')
        result[service]={'operation':operation,'http_status':code}
    with urlopen('http://127.0.0.1:4566/_localstack/health',timeout=5) as response:
        result['health']=check_health(json.load(response))
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
