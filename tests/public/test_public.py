from datetime import datetime,timedelta
import json
from pathlib import Path
import tempfile
import unittest
from app.briefing.model import TZ
from app.public_digest.pipeline import generate,persist,canonical_url,rebuild_index

ROOT=Path(__file__).resolve().parents[2]
NOW=datetime(2026,11,18,8,2,tzinfo=TZ)


def feed(day='2026-11-18',clock='07:30:00',title='TEST fixture not real news',url='https://example.com/a'):
 return f'<rss><channel><item><title>{title}</title><link>{url}</link><pubDate>{day}T{clock}+08:00</pubDate></item></channel></rss>'.encode()

class PublicTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  self.config=self.root/'config.json'
  self.config.write_text(json.dumps({'sources':[{'id':'test','publisher':'TEST ONLY','url':'https://example.com/feed','allowed_hosts':['example.com'],'category':'industry','reliability':'B','license_reviewed':True,'enabled':True,'public_reuse':{'decision':'allowed','basis_url':'https://example.com/test-terms','checked_on':'2026-11-18','allowed_article_prefixes':['/a'],'restriction':'TEST FIXTURE ONLY'}}]}))
 def tearDown(self):self.tmp.cleanup()
 def report(self,now=NOW,data=None):
  return generate(self.config,'morning',now,fetcher=lambda s:data or feed(),attempts=1)

 def test_report_fields_date_and_strict_morning_cutoff(self):
  r=self.report();self.assertEqual(len(r['items']),1)
  self.assertEqual(r['report_date'],'2026-11-18')
  self.assertEqual(r['cutoff_at'],'2026-11-18T07:58:00+08:00')
  self.assertTrue(all(r['items'][0][key] for key in ('title','url','source','published_at','collected_at','summary')))
  self.assertEqual(len(self.report(data=feed(clock='08:00:00'))['items']),0)
  utc=datetime.fromisoformat('2026-11-18T00:02:00+00:00')
  self.assertEqual(self.report(utc)['report_date'],'2026-11-18')

 def test_manual_run_before_0800_does_not_freeze_a_premature_daily_report(self):
  r=self.report(NOW.replace(hour=7,minute=45))
  self.assertEqual(persist(r,self.root),'pending')
  self.assertFalse((self.root/'data/reports/2026-11-18.json').exists())

 def test_dedup_rules_and_no_speculative_stock_names(self):
  data=b'<rss><channel>'+feed().split(b'<channel>')[1].split(b'</channel>')[0]*2+b'</channel></rss>'
  self.assertEqual(len(self.report(data=data)['items']),1)
  self.assertEqual(self.report()['items'][0]['stocks'],[])
  self.assertEqual(canonical_url('https://example.com/x?utm_source=foo&amp=1#frag'),'https://example.com/x?amp=1')

 def test_duplicate_run_preserves_bytes_and_archive(self):
  r=self.report();self.assertEqual(persist(r,self.root),'success')
  p=self.root/'data/reports/2026-11-18.json';before=p.read_bytes()
  later=self.report(NOW+timedelta(minutes=10))
  self.assertEqual(persist(later,self.root),'preserved');self.assertEqual(before,p.read_bytes())
  tomorrow=generate(self.config,'morning',NOW+timedelta(days=1),lambda s:feed('2026-11-19'),attempts=1)
  persist(tomorrow,self.root)
  self.assertEqual([r['date'] for r in rebuild_index(self.root)['reports']],['2026-11-19','2026-11-18'])

 def test_network_failure_does_not_replace_success_or_fake_today(self):
  persist(self.report(),self.root)
  p=self.root/'data/reports/2026-11-18.json';before=p.read_bytes()
  def fail(s):raise OSError('TEST-ONLY-NETWORK')
  bad=generate(self.config,'morning',NOW+timedelta(days=1),fail,attempts=1)
  self.assertEqual(persist(bad,self.root),'failed')
  self.assertFalse((self.root/'data/reports/2026-11-19.json').exists())
  self.assertEqual(before,p.read_bytes())
  status=json.loads((self.root/'data/status.json').read_text())
  self.assertEqual(status['latest_success_date'],'2026-11-18')
  self.assertEqual(status['state'],'failed')

 def test_snapshot_is_explicit_and_not_a_backdated_morning_report(self):
  r=generate(self.config,'snapshot',NOW.replace(hour=20),lambda s:feed(clock='19:00:00'),attempts=1)
  self.assertEqual(len(r['items']),1)
  self.assertIn('非08:00',r['edition_label'])
  self.assertEqual(r['cutoff_at'],'2026-11-18T20:02:00+08:00')

 def test_export_allowlist_excludes_private_project_files(self):
  from app.public_digest.package import CODE,export_public
  persist(self.report(),self.root)
  for name in CODE:
   p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('PUBLIC TEST FIXTURE')
  for name in ('daily.yml.example','PUBLIC_README.md','gitignore.example'):
   p=self.root/'deploy/pages'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('PUBLIC TEMPLATE')
  private=self.root/'database/events.sqlite3';private.parent.mkdir();private.write_bytes(b'PRIVATE DATABASE')
  (self.root/'.env').write_text('PRIVATE TEST TOKEN')
  (self.root/'account.png').write_bytes(b'PRIVATE SCREENSHOT')
  out=export_public(self.root/'public-export',self.root)
  self.assertFalse((out/'database').exists())
  self.assertFalse((out/'.env').exists())
  self.assertFalse((out/'account.png').exists())
  self.assertTrue((out/'.github/workflows/daily.yml').exists())

 def test_build_only_serves_static_assets_and_public_json(self):
  from app.public_digest.package import build_site
  persist(self.report(),self.root)
  (self.root/'static_pages').mkdir()
  for name in ('index.html','style.css','app.js'):(self.root/'static_pages'/name).write_text('TEST')
  (self.root/'private.sqlite3').write_bytes(b'private')
  (self.root/'account-screenshot.png').write_bytes(b'private')
  site=build_site(self.root,self.root/'site')
  self.assertFalse((site/'private.sqlite3').exists())
  self.assertFalse((site/'account-screenshot.png').exists())
  self.assertTrue((site/'data/reports/2026-11-18.json').exists())


 def test_permission_missing_or_blocked_fails_before_network(self):
  config=json.loads(self.config.read_text());source=config['sources'][0]
  source.pop('public_reuse');self.config.write_text(json.dumps(config))
  with self.assertRaises(ValueError):self.report()
  source['public_reuse']={'decision':'blocked'};self.config.write_text(json.dumps(config))
  with self.assertRaises(ValueError):self.report()

 def test_license_path_scope_and_no_body_or_quoted_summary(self):
  from app.public_digest.rights import publishable
  r=self.report();item=r['items'][0]
  self.assertTrue(publishable(r));self.assertNotIn(item['title'],item['summary'])
  self.assertNotIn('body',item);self.assertNotIn('description',item)
  self.assertEqual(self.report(data=feed(url='https://example.com/speech'))['items'],[])
  item['body']='TEST ONLY';self.assertFalse(publishable(r))

 def test_legacy_snapshot_quarantined_but_not_deleted(self):
  from app.public_digest.package import build_site
  r=self.report();r['items'][0].pop('source_id')
  p=self.root/'data/reports/2026-11-18.json';p.parent.mkdir(parents=True);p.write_text(json.dumps(r))
  before=p.read_bytes();self.assertEqual(rebuild_index(self.root)['reports'],[])
  (self.root/'static_pages').mkdir()
  for name in ('index.html','style.css','app.js'):(self.root/'static_pages'/name).write_text('TEST')
  site=build_site(self.root,self.root/'site')
  self.assertFalse((site/'data/reports/2026-11-18.json').exists())
  self.assertEqual(before,p.read_bytes())
  with self.assertRaises(ValueError):persist(self.report(),self.root)
  with self.assertRaises(ValueError):build_site(self.root,site)

 def test_ecb_research_and_speeches_excluded(self):
  from app.public_digest.rights import allowed
  source={'allowed_hosts':['www.ecb.europa.eu'],'public_reuse':{'decision':'allowed','basis_url':'https://www.ecb.europa.eu/terms','checked_on':'2026-11-18','allowed_article_prefixes':['/press/pr/']}}
  self.assertTrue(allowed(source,'https://www.ecb.europa.eu/press/pr/date/2026/a.html'))
  for path in ['/press/key/date/a.html','/press/inter/a.html','/pub/pdf/a.pdf']:
   self.assertFalse(allowed(source,'https://www.ecb.europa.eu'+path))
  self.assertEqual(canonical_url('https://www.ecb.europa.eu//press/pr/a.html'),'https://www.ecb.europa.eu/press/pr/a.html')

 def test_mofcom_original_marker_and_visible_publication_time(self):
  from app.public_digest.adapters import mofcom_metadata
  source=json.loads(self.config.read_text())['sources'][0]
  html='<meta name="ArticleTitle" content="TEST ONLY"><meta name="PubDate" content="2026-11-18 09:00"><p>来源：商务部新闻办公室 <span>类型：原创</span> 分类：新闻 2026-11-18 07:30</p><p>PROTECTED BODY NOT RETAINED</p>'
  item=mofcom_metadata(html.encode(),source,'https://example.com/a',NOW)
  self.assertEqual(item['published_at'],'2026-11-18T07:30:00+08:00')
  self.assertNotIn('PROTECTED BODY',str(item))
  for replacement in ('转载','摘编','编译'):
   self.assertIsNone(mofcom_metadata(html.replace('原创',replacement).encode(),source,'https://example.com/a',NOW))
  self.assertIsNone(mofcom_metadata(b'<meta name="ArticleTitle" content="TEST">',source,'https://example.com/a',NOW))

if __name__=='__main__':unittest.main()
