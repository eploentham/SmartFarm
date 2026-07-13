"""
tv_display.py — the 55" TV board (HDMI-A-1). Default view = 6-camera CCTV wall.

NO CAMERA on this process. It shows:
  * DEFAULT: a 2x3 wall of 6 VIGI cameras, streamed through go2rtc (RTSP→browser).
  * DURING A SPRAY: the spray board pops over the wall (photo + Gemini reading),
    driven by tv_state.json, then returns to the wall when idle.

Prerequisites:
  * go2rtc running with go2rtc.yaml (the 6 cameras). See GO2RTC_URL in config.py.
  * telegram_bot.py writing tv_state.json during a spray.

Endpoints:
  GET /        the wall (+ spray overlay)
  GET /data    current tv_state.json (overlay polls this)
  GET /photo   the current bottle photo (files under CAPTURE_DIR only)

Run:
    pip install flask
    python tv_display.py            # serves http://localhost:5000
"""

import os

from flask import Flask, jsonify, render_template_string, send_file, abort

from config import CAPTURE_DIR, GO2RTC_URL, CCTV_STREAMS, SPRAY_OVERLAY
from tv_state import read_state

app = Flask(__name__)


@app.route("/data")
def data():
    return jsonify(read_state())


@app.route("/photo")
def photo():
    """Serve the current bottle photo, only if it lives under CAPTURE_DIR."""
    s = read_state()
    p = s.get("image_url")
    if not p:
        abort(404)
    real = os.path.realpath(p)
    if not real.startswith(os.path.realpath(CAPTURE_DIR)):
        abort(403)
    if not os.path.exists(real):
        abort(404)
    return send_file(real, mimetype="image/jpeg")


@app.route("/")
def index():
    return render_template_string(PAGE, streams=CCTV_STREAMS,
                                  go2rtc=GO2RTC_URL,
                                  overlay=("true" if SPRAY_OVERLAY else "false"))


PAGE = r"""
<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Smart Farm — CCTV Wall</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { height: 100%; background: #000; color: #f2f2f2;
    font-family: "Sarabun", "Noto Sans Thai", system-ui, sans-serif; overflow: hidden; }

  /* 2 rows x 3 columns CCTV grid */
  #cctv { display: grid; grid-template-columns: repeat(3, 1fr);
    grid-template-rows: repeat(2, 1fr); gap: 3px; width: 100vw; height: 100vh; }
  .cell { position: relative; background: #0a0a0a; overflow: hidden; }
  .cell iframe { width: 100%; height: 100%; border: 0; display: block; }
  .cell .tag { position: absolute; bottom: 8px; left: 10px; z-index: 2;
    background: rgba(0,0,0,.55); padding: 4px 12px; border-radius: 6px;
    font-size: 20px; font-weight: 500; }

  /* Spray overlay (hidden until a spray happens) */
  #spray { display: none; position: fixed; inset: 0; z-index: 10;
    background: #0d0f12; flex-direction: row; }
  .photo { flex: 0 0 44%; background: #000; display: flex; align-items: center; justify-content: center; }
  .photo img { width: 100%; height: 100%; object-fit: contain; }
  .photo .none { color: #4a5058; font-size: 30px; }
  .panel { flex: 1; padding: 40px 46px; display: flex; flex-direction: column; }
  .panel h1 { font-size: 36px; font-weight: 500; color: #9fe1cb; margin-bottom: 6px; }
  .sub { font-size: 22px; color: #9aa0a6; margin-bottom: 24px; }
  .banner { font-size: 40px; font-weight: 600; text-align: center; padding: 22px;
    border-radius: 14px; margin-bottom: 26px; line-height: 1.3; }
  .b-ok{background:#10402f;color:#7ee0b8;} .b-warn{background:#4a3510;color:#f5c46b;}
  .b-error{background:#4a1512;color:#f0907b;} .b-idle{background:#1e242b;color:#9aa0a6;}
  .center { flex: 1; display: flex; align-items: center; justify-content: center;
    text-align: center; font-size: 40px; color: #9aa0a6; line-height: 1.4; }
  .mixhdr { font-size: 30px; font-weight: 600; margin-bottom: 16px; text-align: center;
    padding: 14px; border-radius: 12px; line-height: 1.3; }
  .chemlist { flex: 1; overflow-y: auto; }
  .chem { display: flex; align-items: center; gap: 16px; padding: 14px 18px;
    margin-bottom: 10px; border-radius: 12px; background: #1a1f25;
    border-left: 8px solid #3a424b; }
  .chem.b-ok{border-left-color:#7ee0b8;} .chem.b-warn{border-left-color:#f5c46b;}
  .chem.b-error{border-left-color:#f0907b;} .chem.b-idle{border-left-color:#3a424b;}
  .chem-n{font-size:26px;font-weight:700;color:#6b7178;min-width:28px;}
  .chem-name{font-size:26px;font-weight:500;} .chem-sub{font-size:19px;color:#9aa0a6;margin-top:2px;}
  .rows{flex:1;} .row{display:flex;justify-content:space-between;align-items:baseline;
    padding:14px 0;border-bottom:1px solid #262c33;}
  .k{font-size:23px;color:#9aa0a6;} .v{font-size:29px;font-weight:500;text-align:right;max-width:62%;}
</style>
</head>
<body>
  <!-- Default: CCTV wall -->
  <div id="cctv">
    {% for s in streams %}
    <div class="cell">
      <iframe src="{{ go2rtc }}/stream.html?src={{ s }}&mode=webrtc" allow="autoplay"></iframe>
      <div class="tag">{{ s }}</div>
    </div>
    {% endfor %}
  </div>

  <!-- Overlay: spray board -->
  <div id="spray">
    <div class="photo"><img id="photo" alt="" style="display:none"><div id="nophoto" class="none">—</div></div>
    <div class="panel">
      <h1>บันทึกการพ่นยา (Spray Record)</h1>
      <div class="sub" id="worker">—</div>
      <div id="content" style="flex:1;display:flex;flex-direction:column"></div>
    </div>
  </div>

<script>
const OVERLAY_ENABLED = {{ overlay }};
const FLAG_TH = {
  OK_TO_APPROVE: ["✅ ยาถูกต้อง พร้อมบันทึก","Correct — ready to save","b-ok"],
  EXPIRED:       ["⚠️ ยาหมดอายุ","Chemical expired","b-error"],
  LOW_CONFIDENCE:["⚠️ ความมั่นใจต่ำ — ตรวจสอบ","Low confidence","b-warn"],
  NO_FK_MATCH:   ["⚠️ ไม่พบยาในระบบ","Not found in catalog","b-warn"],
};
const ACTIVE = new Set(['reading','collecting','retry','done','saved','error']);
let terminalSince = 0;   // when a saved/error state started (for auto-return)

function showSpray(on){
  document.getElementById('spray').style.display = on ? 'flex' : 'none';
  document.getElementById('cctv').style.display  = on ? 'none' : 'grid';
}
function setPhoto(show, ts){
  const img=document.getElementById('photo'), none=document.getElementById('nophoto');
  if(show){ img.src='/photo?ts='+(ts||Date.now()); img.style.display=''; none.style.display='none'; }
  else { img.style.display='none'; none.style.display=''; }
}
function row(k,v){ if(v==null||v==='') return ''; return `<div class="row"><span class="k">${k}</span><span class="v">${v}</span></div>`; }
function chemCard(c,i){
  const f=FLAG_TH[c.review_flag]||["","","b-idle"];
  const conc=(c.concentration_percent!=null)?' '+c.concentration_percent+'%':'';
  const bits=[c.active_ingredient?(c.active_ingredient+conc):'',c.chemical_type||'',c.catalog_group||'ไม่พบในระบบ'].filter(Boolean).join(' · ');
  return `<div class="chem ${f[2]}"><div class="chem-n">${i+1}</div><div><div class="chem-name">${c.brand_name||c.active_ingredient||'—'}</div><div class="chem-sub">${bits}</div></div></div>`;
}
function renderSpray(s){
  document.getElementById('worker').textContent = s.worker ? ('คนงาน (Worker): '+s.worker) : '—';
  const content=document.getElementById('content');
  const hasPhoto=!!s.image_url && ['done','retry','collecting','saved'].includes(s.status);
  setPhoto(hasPhoto, s.updated_at);
  if(s.status==='reading'){ content.innerHTML=`<div class="center">📷 กำลังอ่านฉลาก…<br>Reading label…</div>`; return; }
  if(s.status==='retry'){
    content.innerHTML=`<div class="banner b-warn">🔄 ${s.reason_th||'ลองใหม่'}<br><span style="font-size:24px;font-weight:400">${s.reason_en||'Please try again'}</span></div>`+
      `<div class="center" style="font-size:28px">📷 ถ่ายให้เห็นฉลากชัด ๆ แล้วส่งใหม่ทาง Telegram</div>`; return;
  }
  if(s.status==='error'){
    content.innerHTML=`<div class="banner b-error">❌ อ่านฉลากไม่สำเร็จ<br>Label read failed</div><div class="center" style="font-size:24px">${s.message||''}</div>`; return;
  }
  if(s.status==='collecting'||s.status==='saved'){
    const chems=s.chemicals||[];
    const hdr=(s.status==='saved')
      ? `<div class="mixhdr b-ok">✅ บันทึกแล้ว ${chems.length} ชนิด</div>`
      : `<div class="mixhdr b-idle">🧪 กำลังผสมยา — ${chems.length} ชนิด</div>`;
    content.innerHTML=hdr+`<div class="chemlist">`+chems.map(chemCard).join('')+`</div>`; return;
  }
  // single 'done'
  const f=FLAG_TH[s.review_flag]||["ผลการอ่าน","","b-idle"];
  const conf=(s.confidence!=null)?Math.round(s.confidence*100)+'%':'';
  const conc=(s.concentration_percent!=null)?s.concentration_percent+'%':'';
  content.innerHTML=`<div class="banner ${f[2]}">${f[0]}</div><div class="rows">`+
    row('ยี่ห้อ (Brand)',s.brand_name)+row('สารออกฤทธิ์ (Active)',s.active_ingredient)+
    row('ความเข้มข้น (Conc.)',conc)+row('ประเภท (Type)',s.chemical_type)+
    row('กลุ่ม (Group)',s.catalog_group)+row('วันหมดอายุ (Expiry)',s.expiry_date)+
    row('ความมั่นใจ (Confidence)',conf)+`</div>`;
}

function decide(s){
  const st=s.status||'idle';
  if(!OVERLAY_ENABLED || !ACTIVE.has(st)){ terminalSince=0; showSpray(false); return; }
  // saved/error: show briefly, then return to the wall after 20 s
  if(st==='saved'||st==='error'){
    if(!terminalSince) terminalSince=Date.now();
    if(Date.now()-terminalSince>20000){ showSpray(false); return; }
  } else { terminalSince=0; }
  showSpray(true);
  renderSpray(s);
}

async function poll(){
  try{ const r=await fetch('/data',{cache:'no-store'}); decide(await r.json()); }
  catch(e){ /* keep wall on transient error */ }
}
poll(); setInterval(poll, 1000);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, threaded=True)