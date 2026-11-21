"""Small bounded adapter for MOFCOM's own original publications; no body retained."""
from datetime import datetime
from html.parser import HTMLParser
import re
import time
from urllib.parse import urljoin
from app.briefing.model import TZ
from app.public_digest.rights import allowed


class Metadata(HTMLParser):
    def __init__(self):
        super().__init__(); self.meta = {}; self.links = []; self.text = []; self.skip = 0
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('script', 'style'): self.skip += 1
        if tag == 'meta': self.meta[(a.get('name') or a.get('property') or '').lower()] = a.get('content', '')
        if tag == 'a' and a.get('href'): self.links.append(a['href'])
    def handle_endtag(self, tag):
        if tag in ('script', 'style'): self.skip = max(0, self.skip - 1)
    def handle_data(self, data):
        if not self.skip: self.text.append(data)


def mofcom_metadata(raw, source, url, collected):
    page = Metadata(); page.feed(raw.decode('utf-8'))
    text = re.sub(r'\s+', ' ', ' '.join(page.text))
    # Require the visible publication strip, not a later CMS metadata generation time.
    strip = re.search(r'来源[：:]\s*(.{1,80}?)\s*(?:文章)?类型[：:]\s*原创\s*(?:分类[：:]\s*[^ ]+\s*)?(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})(?::\d{2})?', text)
    title = page.meta.get('articletitle')
    if not strip or not title or not allowed(source, url): return None
    published = datetime.fromisoformat(strip[2] + 'T' + strip[3]).replace(tzinfo=TZ)
    return dict(title=title, url=url, source=source['publisher'], published_at=published.isoformat(),
                collected_at=collected.isoformat(), category=source['category'], reliability=source['reliability'],
                sectors=[], stocks=[], risk_note=None, is_demo=False, original_type='原创',
                original_source=strip[1], publication_time_basis='visible_original_publication_strip_minute_precision',
                metadata_pubdate=page.meta.get('pubdate'), attribution='文章来源：商务部网站')


def mofcom_items(raw, source, collected, fetcher):
    page = Metadata(); page.feed(raw.decode('utf-8'))
    urls = sorted(dict.fromkeys(urljoin(source['url'], link) for link in page.links if allowed(source, urljoin(source['url'], link))),
                  key=lambda u: 0 if '/xwfyrth/' in u else 1)
    items = []
    for url in urls[:4]:
        time.sleep(1) # Small daily request budget; never crawl a full archive.
        item = mofcom_metadata(fetcher({**source, 'url': url}), source, url, collected)
        if item: items.append(item)
    return items
