"""Bounded RSS/Atom adapter. Sources are opt-in after license/network review."""
from datetime import datetime
from email.utils import parsedate_to_datetime
import ipaddress
import json
from pathlib import Path
import socket
from urllib.parse import urlparse
import urllib.request
import xml.etree.ElementTree as ET
from app.briefing.model import CATEGORIES,TZ,stamp,build_report

MAX_BYTES=2*1024*1024


def local_name(tag):return tag.rsplit('}',1)[-1]


def parse_feed(data,source,collected_at):
    if len(data)>MAX_BYTES:raise ValueError('Feed exceeds size budget')
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():raise ValueError('XML declarations not allowed')
    root=ET.fromstring(data)
    if local_name(root.tag) not in ('rss','feed','RDF'):raise ValueError('Not an RSS/Atom feed')
    result=[]
    for entry in [e for e in root.iter() if local_name(e.tag) in ('item','entry')][:50]:
        fields={}
        for child in entry:
            key=local_name(child.tag)
            if key=='link':
                if child.attrib.get('rel','alternate')=='alternate':
                    fields['url']=child.attrib.get('href') or child.text
            elif key in ('title','pubDate','published','updated'):fields.setdefault(key,child.text)
        text=fields.get('pubDate') or fields.get('published')
        if not text:continue # updated time is not substituted for original publication.
        try:
            try:pub=stamp(text)
            except ValueError:
                pub=parsedate_to_datetime(text)
                if pub.tzinfo is None:continue
                pub=pub.astimezone(TZ)
            if not fields.get('title') or not fields.get('url'):continue
            result.append(dict(title=fields['title'],url=fields['url'],source=source['publisher'],
                published_at=pub.isoformat(),collected_at=collected_at.isoformat(),category=source['category'],
                reliability=source['reliability'],sectors=[],stocks=[],risk_note=None,is_demo=False))
        except (ValueError,TypeError):continue
    if not result and any(local_name(e.tag) in ('item','entry') for e in root.iter()):
        raise ValueError('Feed items missing usable publication metadata')
    return result


def safe_target(url,allowed_hosts):
    parsed=urlparse(url)
    if parsed.scheme!='https' or parsed.hostname not in allowed_hosts or parsed.username or parsed.password:
        raise ValueError('Feed URL must be HTTPS and match approved hosts')
    for addr in socket.getaddrinfo(parsed.hostname,parsed.port or 443,type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(addr[4][0]).is_global:raise ValueError('Non-public feed address blocked')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('Redirect requires explicit source review')


def fetch(source):
    safe_target(source['url'],source['allowed_hosts'])
    request=urllib.request.Request(source['url'],headers={'User-Agent':'Personal-AShare-Briefing/0.1'})
    with urllib.request.build_opener(NoRedirect()).open(request,timeout=12) as response:
        data=response.read(MAX_BYTES+1)
    if len(data)>MAX_BYTES:raise ValueError('Feed too large')
    return data


def collect(config_path,now=None,fetcher=fetch):
    now=now or datetime.now(TZ)
    config=json.loads(Path(config_path).read_text(encoding='utf-8'))
    sources=config['sources']
    if len(sources)>14:raise ValueError('Prototype source budget: at most 14')
    coverage={k:'unconfigured' for k in CATEGORIES}
    news=[];status_by_category={k:[] for k in CATEGORIES}
    for source in sources:
        if not source.get('enabled',False):continue
        cat=source['category']
        if cat not in CATEGORIES:raise ValueError('Unknown source category')
        if not source.get('license_reviewed') or not source.get('publisher') or source.get('reliability') not in ('A','B'):
            raise ValueError('启用前必须确认来源许可、发布者和可信度')
        try:
            parsed=parse_feed(fetcher(source),source,now)
            news.extend(parsed)
            status_by_category[cat].append('ok' if parsed else 'empty')
        except Exception:
            status_by_category[cat].append('error') # do not log credentials or full URLs from exceptions.
    for cat,states in status_by_category.items():
        if states:coverage[cat]='error' if 'error' in states else ('ok' if 'ok' in states else 'empty')
    return build_report(news,coverage,now)
