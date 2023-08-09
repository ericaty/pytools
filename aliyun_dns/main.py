import os
import re
import json
import requests
from aliyunsdkcore.client import AcsClient
from aliyunsdkalidns.request.v20150109.DescribeDomainRecordsRequest import DescribeDomainRecordsRequest
from aliyunsdkalidns.request.v20150109.UpdateDomainRecordRequest import UpdateDomainRecordRequest
from aliyunsdkalidns.request.v20150109.AddDomainRecordRequest import AddDomainRecordRequest
from aliyunsdkalidns.request.v20150109.DeleteDomainRecordRequest import DeleteDomainRecordRequest
try:
    from celery import current_app # noqa
    task = current_app.task
except Exception:
    def task(fn):
        return fn
try:
    from django.conf import settings  # noqa
    config = getattr(settings, 'ALIDNS', {})
    config = {'ALIDNS_' + k: v for k, v in config.items()}
except Exception:
    config = os.environ

APP_ID = config.get('ALIDNS_APP_ID')
APP_SECRET = config.get('ALIDNS_APP_SECRET')
REGION_ID = config.get('ALIDNS_REGION_ID')


def do_action(request):
    if APP_ID is None or APP_SECRET is None or REGION_ID is None:
        raise ValueError('未设置ALIDNS的APP_ID, APP_SECRET or REGION_ID')
    client = AcsClient(APP_ID, APP_SECRET, REGION_ID)
    request.set_accept_format('json')
    response = client.do_action_with_exception(request)
    return response


def get_records(domain: str) -> dict:
    request = DescribeDomainRecordsRequest()
    request.set_DomainName(domain)

    response = do_action(request)
    dic = json.loads(response)
    records = dic.get('DomainRecords', {}).get('Record')
    records = {r.get('RR') + '.' + r.get('DomainName'): r for r in records}
    return records


def get_host_ip() -> str:
    req = requests.get("http://www.net.cn/static/customercare/yourip.asp")
    ip = re.compile('<h2>((\d{1,3})(\.\d{1,3}){3})</h2>').findall(req.text)[0][0]  # noqa
    print('本机IP: ', ip)
    return ip


def change_record(record_id: str, rr: str, ip: str):
    request = UpdateDomainRecordRequest()
    request.set_RecordId(record_id)
    request.set_RR(rr)
    request.set_Type('A')
    request.set_Value(ip)

    response = do_action(request)
    print('修改成功: ', str(response, encoding='utf-8'))


def add_record(domain: str, rr: str, ip: str):
    request = AddDomainRecordRequest()
    request.set_DomainName(domain)
    request.set_RR(rr)
    request.set_Type('A')
    request.set_Value(ip)

    response = do_action(request)
    print('添加成功: ', str(response, encoding='utf-8'))


@task
def delete_record(domain: str, rr: str):
    record_dict = get_records(domain)
    host = rr + '.' + domain
    record = record_dict.get(host)
    if record is None:
        return
    record_id = record.get('RecordId')
    request = DeleteDomainRecordRequest()
    request.set_RecordId(record_id)

    response = do_action(request)
    print('删除成功: ', str(response, encoding='utf-8'))


@task
def add_or_change_record(domain: str, rrs: list[str], ip: str):
    record_dict = get_records(domain)
    for rr in rrs:
        host = rr + '.' + domain
        record = record_dict.get(host)
        try:
            if record is None:
                add_record(domain, rr, ip)
                print('add {} to {}'.format(host, ip))
            elif record.get('Value') != ip:
                record_id = record.get('RecordId')
                change_record(record_id, rr, ip)
                print('change {} to {}'.format(host, ip))
        except Exception:
            pass


@task
def change_records_to_localhost_ip(data: dict):
    '''
    :param data: {domain: [rr1, rr2]}
    '''
    ip = get_host_ip()
    for domain, rrs in data.items():
        add_or_change_record(domain, rrs, ip)
