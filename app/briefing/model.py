from datetime import date, datetime, time, timedelta
import hashlib
import json
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")
CATEGORIES = {"policy":"国内政策与宏观", "announcement":"A股上市公司公告",
    "industry":"行业及产业热点", "overseas":"隔夜海外市场", "assets":"大宗商品和汇率",
    "calendar":"今日重要财经事件", "risk":"高位连板、退潮与异常波动风险"}
STATES = {"ok", "empty", "error", "unconfigured"}


def stamp(value):
    d=datetime.fromisoformat(value.replace("Z","+00:00"))
    if d.tzinfo is None: raise ValueError("时间必须包含时区")
    return d.astimezone(TZ)


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def validate_item(item, now, demo=False):
    for key in ("title","url","source","published_at","collected_at","category","reliability"):
        if not isinstance(item.get(key),str) or not item[key].strip():
            raise ValueError("缺少新闻字段："+key)
    url=urlparse(item["url"])
    if url.scheme not in ("http","https") or not url.hostname: raise ValueError("来源链接无效")
    if item["category"] not in CATEGORIES or item["reliability"] not in ("A","B","C"):
        raise ValueError("未知分类或可信度")
    pub, collected = stamp(item["published_at"]), stamp(item["collected_at"])
    if pub>collected or collected>now: raise ValueError("发布时间/采集时间顺序无效")
    if bool(item.get("is_demo",False)) != demo: raise ValueError("模拟/真实数据不可混用")
    if demo and not item['title'].startswith('[模拟测试]'): raise ValueError("模拟条目必须显式标记")
    if not demo and url.hostname.endswith(".invalid"): raise ValueError("测试域名不可用于真实早报")
    if item.get('event_date'):
        date.fromisoformat(item['event_date'])
        if item['category']!='calendar':raise ValueError('event_date仅用于财经事件日历')
    for stock in item.get("stocks",[]):
        if stock.get('exchange') not in ('SSE','SZSE','BSE') or len(stock.get('code',''))!=6 or not stock['code'].isdigit():
            raise ValueError('股票代码或交易所无效')
        if stock.get('relation') not in ('source_explicit','research_hypothesis') or not stock.get('evidence_url'):
            raise ValueError('股票关联必须保留依据与关联性质')
    return {**item,"published_at":pub.isoformat(),"collected_at":collected.isoformat(),
        "id":digest([item['url'],pub.isoformat(),item['title']]),
        "sectors":list(item.get('sectors',[])),"stocks":list(item.get('stocks',[])),
        "risk_note":item.get('risk_note') or None,"is_demo":demo}


def build_report(items, coverage, now=None, demo=False, *, cutoff_at=None):
    now=now or datetime.now(TZ)
    if now.tzinfo is None: raise ValueError('运行时间必须带时区')
    now=now.astimezone(TZ)
    release=datetime.combine(now.date(),time(8),TZ)
    cutoff=min(now,cutoff_at or datetime.combine(now.date(),time(7,58),TZ))
    start=cutoff-timedelta(hours=24)
    coverage={key:coverage.get(key,'unconfigured') for key in CATEGORIES}
    if any(s not in STATES for s in coverage.values()): raise ValueError('来源覆盖状态无效')
    selected={}
    for item in items:
        item=validate_item(item,now,demo)
        if stamp(item['published_at'])<=cutoff and (stamp(item['published_at'])>=start or item.get('event_date')==now.date().isoformat()) and item['reliability'] in ('A','B'):
            selected[item['id']]=item
    news=sorted(selected.values(),key=lambda n:(n['reliability']!='A',-stamp(n['published_at']).timestamp(),n['id']))
    groups={}
    for n in news:
        for sector in n['sectors']:
            groups.setdefault(sector,[]).append(n['id'])
    themes=[{'name':name,'evidence_ids':ids,'status':'研究观察，非收益判断'}
            for name,ids in sorted(groups.items(),key=lambda p:(-len(p[1]),p[0]))[:3]]
    risks=[{'text':n['risk_note'] or n['title'],'evidence_ids':[n['id']]}
           for n in news if n['category']=='risk' or n['risk_note']][:3]
    complete=all(s in ('ok','empty') for s in coverage.values())
    status=('ready' if complete else 'partial') if news else 'failed'
    report={'schema_version':1,'report_date':now.date().isoformat(),'timezone':'Asia/Shanghai',
        'scheduled_at':release.isoformat(),'cutoff_at':cutoff.isoformat(),'window_start':start.isoformat(),
        'prepared_at':now.isoformat(),'is_demo':demo,'status':status,'coverage':coverage,
        'items':news,'top_ids':[n['id'] for n in news[:10]],'themes':themes,'risks':risks,
        'ranking_method':'优先A类原始来源，其次发布时间倒序；不是热度或涨幅排名'}
    report['report_id']=digest(report)
    return report
