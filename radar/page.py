"""Builds the single-page site you check by hand (published with GitHub Pages)."""
from __future__ import annotations

import html
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

PAGE_DAYS = 60
PAGE_LIMIT = 5000


def build_page(state, matcher, settings, health, site_dir, repo: str, yc_index: dict | None = None) -> int:
    from .main import matches  # avoid a circular import at module load
    from .sources.yc_directory import lookup

    cutoff = (datetime.now(timezone.utc) - timedelta(days=PAGE_DAYS)).isoformat()
    rows = []
    for k, r in state.records.items():
        if r.get("closed") or r.get("first_seen", "") < cutoff:
            continue
        if not matches(matcher, r):
            continue
        sources = sorted(r.get("first_seen_by", r.get("seen_by", {})).items(), key=lambda kv: kv[1])
        source_ids = [s for s, _ in sources]
        yc_hit = lookup(yc_index or {}, r["company"], r.get("board"), r.get("url"))
        from_yc_board = "yc" in source_ids
        from_hn = any(s.startswith("hn:") for s in source_ids)
        rows.append({
            "k": k,
            "c": r["company"], "t": r["title"], "u": r["url"],
            "l": ", ".join(r.get("locations") or [])[:120], "ll": r.get("loc_label", ""),
            "s": r.get("season") or "", "p": r.get("posted_at") or "",
            "f": r["first_seen"], "q": bool(r.get("quiet")),
            # "e" = when it really appeared: the company's posting date if that's earlier than when we found it
            # (a list re-adding a months-old posting shouldn't look new)
            "e": min(r["first_seen"], r["posted_at"]) if r.get("posted_at") else r["first_seen"],
            "src": [label(s) for s in source_ids],
            # YC batch (e.g. "W24") if the company is in YC's directory, "YC" if found on YC's jobs board
            "yc": (yc_hit or {}).get("b") or ("YC" if from_yc_board else "") ,
            "ycu": (yc_hit or {}).get("u") or "",
            # startup = YC company, or found on YC's jobs board or Hacker News "Who is hiring?"
            "st": bool(yc_hit or from_yc_board or from_hn),
        })
    # newest posted first ("e" = the company's posting date, or when the radar found it if earlier/unknown)
    rows.sort(key=lambda x: x["e"], reverse=True)
    rows = rows[:PAGE_LIMIT]

    links = {
        "scan": f"https://github.com/{repo}/actions/workflows/radar.yml" if repo else "#",
        "edit": f"https://github.com/{repo}/edit/main/settings.toml" if repo else "#",
        "repo": f"https://github.com/{repo}" if repo else "#",
    }
    summary = {
        "roles": settings.role_keywords[:14],
        "roles_count": len(settings.role_keywords),
        "seasons": settings.seasons or ["Any season"],
        "remote": settings.allow_remote,
        "unknown": settings.allow_unknown,
    }
    data = json.dumps({"rows": rows, "health": health, "links": links, "summary": summary},
                      separators=(",", ":")).replace("</", "<\\/")
    out = Path(site_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(TEMPLATE.replace("__DATA__", data))
    (out / "postings.json").write_text(json.dumps(rows, indent=0))
    return len(rows)


def label(source_id: str) -> str:
    if source_id.startswith("list:"):
        return "List: " + source_id[5:]
    if source_id.startswith("hn:"):
        return "HN Who's hiring"
    if source_id == "yc":
        return "YC jobs board"
    system = source_id.split(":", 1)[0]
    return {"greenhouse": "Greenhouse", "lever": "Lever", "ashby": "Ashby", "workday": "Workday"}.get(system, system)


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Internship Radar</title>
<style>
:root{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1f;--muted:#6b6b70;--line:#e4e4e0;--accent:#2f5bd3;--new:#e8f7ee;--newink:#17723c;--chip:#eef1f8}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#121214;--card:#1b1b1f;--ink:#ececee;--muted:#9a9aa2;--line:#2c2c32;--accent:#7f9cff;--new:#163222;--newink:#7fdca3;--chip:#252a38}}
:root[data-theme="dark"]{--bg:#121214;--card:#1b1b1f;--ink:#ececee;--muted:#9a9aa2;--line:#2c2c32;--accent:#7f9cff;--new:#163222;--newink:#7fdca3;--chip:#252a38}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1000px;margin:0 auto;padding:20px 16px 60px}
header{display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between}
h1{font-size:22px;margin:0}
.sub{color:var(--muted);font-size:13px;margin-top:2px}
.btns{display:flex;gap:8px;flex-wrap:wrap}
.btn{display:inline-block;padding:8px 12px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink);text-decoration:none;font-weight:600;font-size:14px;cursor:pointer}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.stats{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;min-width:120px}
.stat b{display:block;font-size:20px}
.stat span{color:var(--muted);font-size:12px}
.filters{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 14px}
.filters input,.filters select{padding:8px 10px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink);font-size:14px}
.filters input[type=search]{flex:1 1 220px}
label.tog{display:flex;align-items:center;gap:6px;font-size:14px;color:var(--muted)}
.list{display:flex;flex-direction:column;gap:8px}
.row{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;display:grid;grid-template-columns:1fr auto;gap:4px 12px}
.row.isnew{background:var(--new)}
.t{font-weight:600;color:var(--ink);text-decoration:none}
.t:hover{text-decoration:underline}
.c{color:var(--muted);font-size:14px}
.meta{grid-column:1/-1;display:flex;gap:6px;flex-wrap:wrap;font-size:12px;color:var(--muted)}
.chip{background:var(--chip);border-radius:999px;padding:2px 8px}
.yc,.st{display:inline-block;font-size:11px;font-weight:700;border-radius:4px;padding:1px 6px;margin-left:6px;vertical-align:1px}
.yc{background:#f26522;color:#fff}
.st{background:var(--chip);color:var(--accent);border:1px solid var(--accent)}
.when{text-align:right;font-size:12px;color:var(--muted);white-space:nowrap}
.row.done{opacity:.55}
.row.done .t{text-decoration:line-through}
.donebtn{margin-top:6px;padding:4px 10px;border-radius:6px;border:1px solid var(--line);background:var(--bg);color:var(--ink);font-size:12px;font-weight:600;cursor:pointer}
.row.done .donebtn{background:var(--new);color:var(--newink);border-color:var(--newink)}
.badge{font-size:11px;font-weight:700;color:var(--newink)}
details{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin:12px 0}
summary{cursor:pointer;font-weight:600}
table{border-collapse:collapse;width:100%;font-size:13px;margin-top:8px}
td,th{text-align:left;padding:4px 6px;border-bottom:1px solid var(--line)}
.ok{color:var(--newink)}.bad{color:#d33}
.empty{color:var(--muted);padding:30px;text-align:center}
@media (max-width:560px){.row{grid-template-columns:1fr}.when{text-align:left}}
</style>
</head>
<body>
<div class="wrap">
<header>
  <div><h1>Internship Radar</h1><div class="sub" id="updated"></div></div>
  <div class="btns">
    <a class="btn primary" id="scan" target="_blank" rel="noopener">Scan now ↗</a>
    <a class="btn" id="edit" target="_blank" rel="noopener">Edit settings ↗</a>
    <button class="btn" id="seen">Mark all as seen</button>
  </div>
</header>
<div class="stats" id="stats"></div>
<div class="filters">
  <input type="search" id="q" placeholder="Search company, title, location…">
  <select id="src"><option value="">All sources</option></select>
  <select id="loc"><option value="">All locations</option><option>US</option><option>Remote</option><option>Unclear</option></select>
  <select id="sort"><option value="e">Newest posted first</option><option value="f">Newest found first</option></select>
  <select id="age"><option value="">Posted any time</option><option value="1">Posted in last 24 hrs</option><option value="3">Last 3 days</option><option value="7">Last 7 days</option><option value="14">Last 14 days</option></select>
  <select id="kind"><option value="">All companies</option><option value="yc">YC companies only</option><option value="st">Startups only (YC + HN)</option></select>
  <label class="tog"><input type="checkbox" id="onlynew"> New since my last visit</label>
  <label class="tog"><input type="checkbox" id="showdone"> Show done</label>
</div>
<div class="list" id="list"></div>
<details><summary>Your settings</summary><div id="settings"></div></details>
<details><summary>Scan health</summary><div id="health"></div></details>
</div>
<script type="application/json" id="data">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const $=id=>document.getElementById(id);
let lastVisit=null;try{lastVisit=localStorage.getItem('radarLastVisit')}catch(e){}
$('scan').href=D.links.scan;$('edit').href=D.links.edit;
const h=D.health,ago=t=>{if(!t)return'';const s=(Date.now()-new Date(t))/1000;if(s<3600)return Math.max(1,Math.round(s/60))+' min ago';if(s<86400)return Math.round(s/3600)+' hr ago';return Math.round(s/86400)+' d ago'};
$('updated').textContent='Last scan '+ago(h.run_at)+' · '+new Date(h.run_at).toLocaleString();
const posted=p=>{if(/T00:00:00\+00:00$/.test(p)){const d=Math.floor((Date.now()-new Date(p))/86400000);return d<1?'posted today':d<2?'posted yesterday':'posted '+d+' days ago'}return 'posted '+ago(p)};
const esc=s=>String(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const srcs=[...new Set(D.rows.flatMap(r=>r.src))].sort();
srcs.forEach(s=>{const o=document.createElement('option');o.textContent=s;$('src').appendChild(o)});
// "Done" marks are saved in this browser only (phone and laptop keep separate lists).
let done={};try{done=JSON.parse(localStorage.getItem('radarDone')||'{}')}catch(e){}
function saveDone(){try{localStorage.setItem('radarDone',JSON.stringify(done))}catch(e){}}
const NEW_WINDOW=3*86400000;
function isNew(r){return !r.q&&lastVisit&&r.f>lastVisit&&(Date.now()-new Date(r.e))<NEW_WINDOW}
function render(){
  const q=$('q').value.toLowerCase(),src=$('src').value,loc=$('loc').value,age=+$('age').value,onlyNew=$('onlynew').checked,showDone=$('showdone').checked;
  const cutoff=age?new Date(Date.now()-age*86400000).toISOString():'';
  const kind=$('kind').value,sortBy=$('sort').value;
  const rows=D.rows.filter(r=>(showDone||!done[r.k])&&(!q||(r.c+' '+r.t+' '+r.l+' '+r.s).toLowerCase().includes(q))&&(!src||r.src.includes(src))&&(!loc||r.ll===loc)&&(!cutoff||r.e>=cutoff)&&(!onlyNew||isNew(r))&&(!kind||(kind==='yc'?!!r.yc:r.st)));
  if(sortBy==='f')rows.sort((a,b)=>a.f<b.f?1:a.f>b.f?-1:(a.e<b.e?1:-1));
  const newCount=D.rows.filter(r=>isNew(r)&&!done[r.k]).length;
  const doneCount=D.rows.filter(r=>done[r.k]).length;
  $('stats').innerHTML=`<div class="stat"><b>${D.rows.length-doneCount}</b><span>open, not done</span></div><div class="stat"><b>${lastVisit?newCount:'—'}</b><span>new since last visit</span></div><div class="stat"><b>${D.rows.filter(r=>r.yc&&!done[r.k]).length}</b><span>at YC companies</span></div><div class="stat"><b>${doneCount}</b><span>marked done</span></div><div class="stat"><b>${h.new_matching??0}</b><span>new in last scan</span></div><div class="stat"><b>${h.boards_checked??0}</b><span>company boards checked</span></div>`;
  $('list').innerHTML=rows.length?rows.slice(0,800).map(r=>`<div class="row${isNew(r)?' isnew':''}${done[r.k]?' done':''}"><div><a class="t" href="${esc(r.u)}" target="_blank" rel="noopener">${esc(r.t)}</a> ${isNew(r)&&!done[r.k]?'<span class="badge">NEW</span>':''}<div class="c">${esc(r.c)}${r.yc?(r.ycu?`<a class="yc" href="${esc(r.ycu)}" target="_blank" rel="noopener" style="text-decoration:none">YC ${r.yc==='YC'?'':esc(r.yc)}</a>`:`<span class="yc">YC</span>`):(r.st?'<span class="st">Startup</span>':'')}</div></div><div class="when">${r.p?'<b>'+posted(r.p)+'</b><br>':''}${r.q?'found on first check':'found '+ago(r.f)}<br><button class="donebtn" data-k="${esc(r.k)}">${done[r.k]?'✓ Done (undo)':'Mark done'}</button></div><div class="meta">${r.l?`<span class="chip">📍 ${esc(r.l)}</span>`:`<span class="chip">📍 ${esc(r.ll)}</span>`}${r.s?`<span class="chip">🗓 ${esc(r.s)}</span>`:''}${r.src.map(s=>`<span class="chip">${esc(s)}</span>`).join('')}</div></div>`).join('')+(rows.length>800?`<div class="empty">Showing 800 of ${rows.length}. Search or filter to narrow down.</div>`:''):'<div class="empty">Nothing matches these filters.</div>';
}
$('list').addEventListener('click',e=>{const b=e.target.closest('.donebtn');if(!b)return;const k=b.dataset.k;if(done[k])delete done[k];else done[k]=new Date().toISOString();saveDone();render()});
['q','src','loc','age','onlynew','showdone','kind','sort'].forEach(id=>$(id).addEventListener('input',render));
$('seen').onclick=()=>{lastVisit=new Date().toISOString();try{localStorage.setItem('radarLastVisit',lastVisit)}catch(e){};render()};
if(!lastVisit){try{localStorage.setItem('radarLastVisit',new Date().toISOString())}catch(e){}}
const S=D.summary;
$('settings').innerHTML=`<p>Role keywords (${S.roles_count}): ${esc(S.roles.join(', '))}${S.roles_count>S.roles.length?'…':''}<br>Seasons: ${esc(S.seasons.join(', '))}<br>United States only · Remote ${S.remote?'included':'excluded'} · No-location postings ${S.unknown?'included':'excluded'}</p><p><a href="${D.links.edit}" target="_blank" rel="noopener">Edit settings.toml ↗</a> (changes apply on the next scan; tap Scan now to run one)</p>`;
const hs=Object.entries(h.sources||{}).map(([k,v])=>`<tr><td>${esc(k)}</td><td class="${v.ok?'ok':'bad'}">${v.ok?'OK':'Error'}</td><td>${esc(v.error||v.note||[v.internships!=null?v.internships+' internships':'',v.boards_ok!=null?v.boards_ok+' boards OK':'',v.failed?v.failed+' failed':'',v.comments_read!=null?v.comments_read+' new comments read':''].filter(Boolean).join(' · '))}</td></tr>`).join('');
const bad=Object.entries(h.boards||{}).slice(0,40).map(([k,v])=>`<tr><td>${esc(k)}</td><td colspan="2">${esc(v)}</td></tr>`).join('');
$('health').innerHTML=`<p>${h.boards_checked??0} company boards checked in ${h.duration_s}s · ${h.new_postings??0} new postings found (${h.new_matching??0} match your settings) · ${h.alerts_sent??0} alerts sent</p><table><tr><th>Source</th><th>Status</th><th>Details</th></tr>${hs}</table>${bad?`<p style="margin-top:12px">Boards that failed this scan (first 40):</p><table>${bad}</table>`:''}`;
render();
</script>
</body>
</html>
"""
