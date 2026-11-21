"""Opt-in free RSS -> metadata-only JSON. No DB, API key or model call."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import tempfile
import time
import unicodedata
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode
from app.briefing.collect import fetch,parse_feed
from app.public_digest.rights import allowed,publishable
from app.public_digest.adapters import mofcom_items
from app.briefing.model import TZ,CATEGORIES,stamp,validate_item,build_report,digest

ROOT=Path(__file__).resolve().parents[2]
CONFIG=ROOT/'config/public_sources.json'
RULES={
 'risk':('异常波动','严重异动','跌停','退潮','风险提示','立案调查'),
 'assets':('原油','黄金','期货','汇率','人民币中间价','美元指数'),
 'announcement':('业绩预告','公司公告','回购股份','减持计划','停复牌','重大合同'),
 'calendar':('今日公布','今日召开','将于今日'),
 'overseas':('美联储','美股','纳斯达克','道琼斯','标普','欧洲央行'),
 'policy':('政策','国务院','发改委','降准','宏观','减负','财政','央行','减税')}
SECTORS={'人工智能':('人工智能','AI','算力'),'半导体':('半导体','芯片'),
 '新能源':('新能源','光伏','储能'),'汽车':('汽车','电动车'),
 '医药':('医药','医疗','创新药'),'消费与商贸':('消费','零售','商贸','旅游'),
 '贸易政策':('贸易','关税','出口管制'),'货币政策':('monetary','interest rate'),'金融稳定':('financial stability','fiscal imbalances'),'金融':('银行','证券','保险'),'资源与商品':('原油','黄金','煤炭','期货')}


def canonical_url(url):
 p=urlsplit(url)
 if p.scheme not in ('http','https') or not p.hostname or p.username or p.password:raise ValueError('invalid news URL')
 query=[(k,v) for k,v in parse_qsl(p.query,keep_blank_values=True) if not k.lower().startswith('utm_') and k.lower() not in ('spm','from')]
 return urlunsplit((p.scheme,p.netloc,re.sub(r'/+', '/', p.path),urlencode(query),''))


def enrich(item):
 item={**item,'url':canonical_url(item['url'])}
 title=unicodedata.normalize('NFKC',item['title']).strip()
 item['title']=title
 if item['category']!='overseas':
  item['category']=next((cat for cat,words in RULES.items() if any(w in title for w in words)),'industry')
 item['sectors']=[sector for sector,words in SECTORS.items() if any(w in title for w in words)]
 item['classification_basis']='标题关键词规则，仅供研究；不是公司正式行业分类'
 # Only copy explicit exchange-qualified codes appearing in the original headline.
 item['stocks']=[{'code':code,'exchange':exchange,'relation':'source_explicit','evidence_url':item['url']}
   for code,suffix in re.findall(r'(?<!\d)(\d{6})[.](SH|SZ|BJ)(?![A-Z])',title)
   for exchange in [{'SH':'SSE','SZ':'SZSE','BJ':'BSE'}[suffix]]]
 item['summary']=f"系统独立核查提示：{item['source']}于{item['published_at'][:10]}发布一则信息。应核对适用对象、实施日期及附件；尚未验证其对A股个股业绩或价格的影响。"
 item['summary_method']='independent_metadata_analysis_v1'
 item['risk_note']='系统独立核查提示：风险关键词触发；须核对原始披露和行情，尚未验证全市场退潮。' if item['category']=='risk' else None
 return item


def generate(config=CONFIG,edition='morning',now=None,fetcher=fetch,attempts=2):
 if edition not in ('morning','snapshot'):raise ValueError('unknown edition')
 config=json.loads(Path(config).read_text())
 if len(config['sources'])>6:raise ValueError('public MVP source budget exceeded')
 items=[];checks=[]
 # Actual clock taken after requests, never back-date collected_at to 08:00.
 for source in config['sources']:
  if not source.get('enabled'):continue
  if not source.get('license_reviewed') or source.get('public_reuse',{}).get('decision')!='allowed' or source['reliability'] not in ('A','B'):raise ValueError('source not approved')
  parsed=[];error=None
  for attempt in range(attempts):
   try:
    raw=fetcher(source)
    collected=now or datetime.now(TZ)
    parsed=mofcom_items(raw,source,collected,fetcher) if source.get('format')=='mofcom_original' else parse_feed(raw,source,collected)
    collected=now or datetime.now(TZ)
    parsed=[enrich({**x,'collected_at':collected.isoformat()}) for x in parsed]
    parsed=[{**x,'source_id':source['id'],'license_basis_url':source['public_reuse']['basis_url'],'license_checked_on':source['public_reuse']['checked_on']} for x in parsed if allowed(source,x['url'])]
    for x in parsed:validate_item(x,collected,False)
    error=None;break
   except Exception as exc:
    error=type(exc).__name__ # No local paths, credentials, response body or traceback in public JSON.
    if attempt+1<attempts:time.sleep(max(1,source.get('request_interval_seconds',1)))
  items.extend(parsed if error is None else [])
  checks.append({'id':source['id'],'source':source['publisher'],'feed_url':source['url'],
    'allowed_hosts':source['allowed_hosts'],'public_reuse':source['public_reuse'],
    'checked_at':(now or datetime.now(TZ)).isoformat(),'fetch_status':'error' if error else 'ok',
    'parsed_count':len(parsed) if not error else 0,'error_type':error,'reliability':source['reliability']})
 clock=now or datetime.now(TZ)
 coverage={k:'unconfigured' for k in CATEGORIES}
 for item in items:coverage[item['category']]='ok'
 for c in checks:
  if c['id']=='fed-press' and c['fetch_status']=='error':coverage['overseas']='error'
 report=build_report(items,coverage,clock,False,cutoff_at=clock if edition=='snapshot' else None)
 # Re-evaluate observed categories on eligible news only; feeds with only stale items are not today's coverage.
 observed={i['category'] for i in report['items']}
 report['coverage']={k:('ok' if k in observed else ('error' if v=='error' else 'unconfigured')) for k,v in coverage.items()}
 report['status']='partial' if report['items'] else 'failed' # limited free sources never imply complete market coverage.
 report['edition']=edition
 report['edition_label']='真实采集验收快照（非08:00日报）' if edition=='snapshot' else '08:00盘前日报'
 report['generated_at']=clock.astimezone(TZ).isoformat()
 report['sources']=checks
 report['limitations']=['免费RSS样本，不覆盖全部公告、行情或风险','板块是标题关键词观察，股票代码只取原题显式代码',
  '仅许可范围内原标题和元数据；核查提示为系统独立模板，不是新闻摘要；不保存正文、图片或受保护摘要','RSS可能只保留近期条目；迟跑可能遗漏盘前消息']
 report['ranking_method']='来源级别优先、发布时间倒序；非阅读量或涨幅榜'
 report.pop('report_id',None);report['report_id']=digest(report)
 return report


def atomic_json(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 fd,temp=tempfile.mkstemp(dir=path.parent,suffix='.json');os.close(fd)
 try:
  Path(temp).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
  os.replace(temp,path)
 finally:Path(temp).unlink(missing_ok=True)


def rebuild_index(root):
 root=Path(root);entries=[]
 for path in sorted((root/'data/reports').glob('*.json')):
  r=json.loads(path.read_text())
  if not publishable(r):continue # Local legacy snapshots remain untouched and are never indexed publicly.
  if path.stem!=r['report_date'] or r.get('is_demo') or not r.get('items'):raise ValueError('invalid public archive')
  entries.append({'date':r['report_date'],'file':'data/reports/'+path.name,'generated_at':r['generated_at'],
    'count':len(r['items']),'edition':r['edition'],'status':r['status']})
 entries.sort(key=lambda x:x['date'],reverse=True)
 index={'schema_version':1,'latest_success_date':entries[0]['date'] if entries else None,'reports':entries}
 atomic_json(root/'data/index.json',index)
 return index


def persist(report,root):
 root=Path(root);day=report['report_date']
 path=root/'data/reports'/f'{day}.json'
 path.parent.mkdir(parents=True,exist_ok=True)
 if report['is_demo']:raise ValueError('demo data not permitted')
 if report['items'] and not publishable(report):raise ValueError('report lacks verified reuse permission')
 if path.exists() and not publishable(json.loads(path.read_text())):raise ValueError('local legacy report is quarantined; use a separate clean release workspace')
 check=dict(report);check.pop('report_id')
 if digest(check)!=report['report_id']:raise ValueError('report hash mismatch')
 early=report['edition']=='morning' and stamp(report['generated_at'])<stamp(report['scheduled_at'])
 state='pending' if early else 'failed'
 if report['items'] and not early:
  path.parent.mkdir(parents=True,exist_ok=True)
  # First successful daily file is immutable; manual rerun/retry cannot destroy history.
  fd,temp=tempfile.mkstemp(dir=path.parent,suffix='.tmp')
  try:
   with os.fdopen(fd,'w',encoding='utf-8') as f:
    json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
   try:
    os.link(temp,path) # atomically create complete daily JSON, never replace an existing report.
    state='success'
   except FileExistsError:
    state='preserved'
  finally:Path(temp).unlink(missing_ok=True)
  if state=='preserved':
   old=json.loads(path.read_text())
   if old.get('report_date')!=day or old.get('is_demo') or not old.get('items'):raise ValueError('existing report requires manual review')
   state='preserved'
 index=rebuild_index(root)
 atomic_json(root/'data/status.json',{'schema_version':1,'attempt_date':day,'attempted_at':report['generated_at'],
   'state':state,'latest_success_date':index['latest_success_date'],'accepted_items_this_attempt':len(report['items']),
   'sources':report['sources'],'message':('尚未到北京时间08:00；未发布' if early else ('采集失败；保留最近成功日报' if state=='failed' else '成功日报不覆盖；查看归档日期与版本标记'))})
 return state


def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--root',default='.')
 parser.add_argument('--config',default=str(CONFIG))
 parser.add_argument('--edition',choices=['morning','snapshot'],default='morning')
 args=parser.parse_args()
 report=generate(args.config,args.edition)
 state=persist(report,args.root)
 print(json.dumps({'state':state,'date':report['report_date'],'items':len(report['items']),'edition':args.edition},ensure_ascii=False))
 if state in ('failed','pending'):raise SystemExit(2)

if __name__=='__main__':main()
