/* Buildless, same-origin JSON only. Never render news with innerHTML. */
(function(root){
'use strict';
const categories={policy:'政策与宏观',announcement:'公司公告线索',industry:'产业热点',overseas:'海外消息',assets:'商品与汇率',calendar:'财经日程',risk:'风险线索'};
function beijingDay(value=new Date()){
 const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(value);
 const get=k=>parts.find(x=>x.type===k).value;return `${get('year')}-${get('month')}-${get('day')}`;
}
function safeLink(url){try{const u=new URL(url);return ['http:','https:'].includes(u.protocol)&&!u.username&&!u.password?u.href:null;}catch{return null;}}
function selectToday(index,today){return (index.reports||[]).find(r=>r.date===today)||null;}
function stateMessage(index,status,today){
 const entry=selectToday(index,today), latest=index.latest_success_date||'暂无';
 if(!entry)return `今日早报暂未更新。最近成功更新日期：${latest}。旧日报仅在历史归档展示。`;
 if(status&&status.attempt_date===today&&status.state==='failed')return `最近一次采集失败；当前保留最近成功版本（${latest}），请核对版本标记和真实生成时间。`;
 if(entry.edition==='snapshot')return '当前是人工触发的真实采集验收快照，不是08:00盘前成稿。请核对实际采集时间。';
 return '当前为今日盘前日报。采集仅覆盖有限免费来源，未出现的消息不代表不存在。';
}
const api={beijingDay,safeLink,selectToday,stateMessage};
if(typeof module!=='undefined')module.exports=api;
root.PublicBriefing=api;
if(typeof document==='undefined')return;
const $=id=>document.getElementById(id);
const node=(tag,text,cls)=>{const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;return el;};
function link(text,url,cls){const el=node('a',text,cls),href=safeLink(url);if(href){el.href=href;el.target='_blank';el.rel='noopener noreferrer';}return el;}
async function loadJson(url){const r=await fetch(url,{cache:'no-store'});if(!r.ok)throw new Error('HTTP '+r.status);return r.json();}
function formatTime(s){return s?new Date(s).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}):'暂无';}
let index={reports:[],latest_success_date:null},status=null,current,sequence=0;
function renderNews(){
 $('news').replaceChildren();
 if(!current)return;
 const byId=new Map(current.items.map(x=>[x.id,x]));const filter=$('category').value;
 const top=current.top_ids.map(id=>byId.get(id)).filter(Boolean);
 const items=top.filter(x=>filter==='all'||x.category===filter);
 $('news-count').textContent=`本期 ${top.length} 条 / 筛选 ${items.length} 条`;
 for(const n of items){
  const card=node('article',undefined,'story'),rank=node('span',String(top.indexOf(n)+1).padStart(2,'0'),'rank'),body=node('div');
  const title=node('h3');title.append(link(n.title,n.url));body.append(title);
  const tags=node('div');tags.append(node('span',categories[n.category]||'待分类','tag'),node('span',`来源级别 ${n.reliability}`,'tag'));body.append(tags);
  body.append(node('p',n.summary));if(n.attribution)body.append(node('p',n.attribution));body.append(node('p',`${n.source} ｜ 发布 ${formatTime(n.published_at)}`));
  body.append(node('p',`采集 ${formatTime(n.collected_at)}`));
  body.append(node('p',`板块观察：${n.sectors.length?n.sectors.join('、'):'待核实'}`));
  body.append(node('p',`涉及股票：${n.stocks.length?n.stocks.map(s=>s.code+'.'+s.exchange).join('、'):'标题没有显式股票代码，待核实'}`));
  body.append(link('查看原始新闻 ↗',n.url,'evidence'));card.append(rank,body);$('news').append(card);
 }
 if(!items.length)$('news').append(node('p','此分类暂无合格条目，不补造。','hint'));
}
function renderSide(report){
 const map=new Map(report.items.map(i=>[i.id,i]));
 for(const [id,list] of [['themes',report.themes],['risks',report.risks]]){
  const el=$(id);el.replaceChildren();
  if(!list.length)el.append(node('p',id==='themes'?'暂无足够证据形成观察主题。':'暂无合格风险线索；不代表市场没有风险。'));
  for(const value of list){el.append(node('h3',value.name||value.text));if(value.status)el.append(node('p',value.status));
   for(const newsId of value.evidence_ids){const n=map.get(newsId);if(n)el.append(link(n.title,n.url,'evidence'));}
  }
 }
 $('sources').replaceChildren();
 for(const s of report.sources){const p=node('p',`${s.source} · ${s.fetch_status==='ok'?'可访问':'本次失败'} · ${s.parsed_count}条解析`);$('sources').append(p,link('原始来源',s.feed_url,'evidence'));}
 for(const s of report.sources){if(s.public_reuse){$('sources').append(link('许可依据',s.public_reuse.basis_url,'evidence'),node('p',`许可检查 ${s.public_reuse.checked_on} ｜ ${s.public_reuse.restriction}`));}}
 const ul=node('ul');for(const limitation of report.limitations)ul.append(node('li',limitation));$('sources').append(ul);
}
async function show(day,isToday){
 const ticket=++sequence;
 $('today').classList.toggle('active',isToday);$('history').classList.toggle('active',!isToday);
 current=null;$('content').hidden=true;$('empty').hidden=true;$('updated').textContent='暂无';$('report-date').textContent=day||'—';
 const entry=(index.reports||[]).find(x=>x.date===day);
 if(!entry){$('empty').hidden=false;return;}
 // Strict derived relative path: never fetch arbitrary URLs from the archive index.
 if(!/^\d{4}-\d{2}-\d{2}$/.test(day))throw new Error('日期无效');
 const report=await loadJson(`data/reports/${day}.json`);
 if(ticket!==sequence)return;
 if(report.report_date!==day||report.is_demo||!Array.isArray(report.items))throw new Error('日报校验失败');
 current=report;$('content').hidden=false;$('updated').textContent=formatTime(report.generated_at);
 $('edition').textContent=`${day} · ${report.edition_label}`;
 $('meta').textContent=`采集截止 ${formatTime(report.cutoff_at)} ｜ ${isToday?'今日视图':'历史归档，不代表今天'} ｜ 覆盖不全时保留缺口`;
 $('category').replaceChildren(node('option','全部类别'));$('category').options[0].value='all';
 for(const k of [...new Set(report.items.map(x=>x.category))]){const o=node('option',categories[k]||k);o.value=k;$('category').append(o);}
 $('coverage').replaceChildren();for(const [k,v] of Object.entries(report.coverage))$('coverage').append(node('span',`${categories[k]||k}：${v==='ok'?'有样本':'未完整覆盖'}`));
 renderNews();renderSide(report);
}
function error(){ $('notice').textContent='数据读取失败；无法确认今日是否更新。请稍后重试，不展示旧内容冒充今天。';$('notice').className='notice error';$('content').hidden=true;$('empty').hidden=false; }
async function start(){
 try{
  index=await loadJson('data/index.json');try{status=await loadJson('data/status.json');}catch{status=null;}
  const today=beijingDay();$('last-success').textContent=index.latest_success_date||'暂无';
  $('notice').textContent=stateMessage(index,status,today);$('notice').className='notice'+(!selectToday(index,today)||selectToday(index,today).edition==='snapshot'?' warn':'');
  $('archive').replaceChildren(node('option','请选择日期'));$('archive').options[0].value='';
  for(const r of index.reports||[]){if(r.date>today)continue;const o=node('option',`${r.date}${r.edition==='snapshot'?' · 验收快照':''}`);o.value=r.date;$('archive').append(o);}
  await show(today,true);
 }catch{error();}
}
$('refresh').addEventListener('click',start);
$('today').addEventListener('click',()=>{ $('notice').textContent=stateMessage(index,status,beijingDay());show(beijingDay(),true).catch(error);});
$('history').addEventListener('click',()=>{const day=$('archive').value||index.latest_success_date;$('archive').value=day||'';$('notice').textContent=`历史归档：${day||'暂无'}，不是今日热点。`;show(day,false).catch(error);});
$('archive').addEventListener('change',()=>{const day=$('archive').value;if(day){$('notice').textContent=`历史归档：${day}，不是今日热点。`;show(day,false).catch(error);}});
$('category').addEventListener('change',renderNews);
start();
})(typeof globalThis!=='undefined'?globalThis:this);
