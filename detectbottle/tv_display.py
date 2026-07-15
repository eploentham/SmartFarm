"""
tv_display.py — split-screen dashboard for the 55" TV (HDMI-A-1) on pi5camera01.

LEFT pane  : live MJPEG stream from camera 0 (watches the worker).
RIGHT pane : latest Gemini bottle-label reading (from tv_state.json).

Shown fullscreen via Chromium kiosk (see run_kiosk.sh).

⚠ CAMERA-0 OWNERSHIP: only ONE process may open camera 0 at a time. This app
owns camera 0 for the live stream while the display is tested standalone. When
detect_spray.py is integrated later, camera 0 must be owned by a SINGLE process
that both runs YOLO and serves this stream — never run two openers on camera 0.
Camera 1 (bottle reading) runs in the record pipeline's own process → no clash.

Run:
    pip install flask
    python tv_display.py        # serves http://localhost:5000
"""

import io
from threading import Condition

from flask import Flask, Response, jsonify, render_template_string

from tv_state import read_state

# --- Camera 0 MJPEG streaming (Picamera2) ---------------------------------
from picamera2 import Picamera2
from picamera2.encoders import MJPEGEncoder
from picamera2.outputs import FileOutput
from libcamera import controls


class StreamingOutput(io.BufferedIOBase):
    """Holds the most recent JPEG frame; wakes waiting stream clients."""

    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()


def _start_camera0():
    picam2 = Picamera2(camera_num=0)                 # camera 0 = worker view
    picam2.configure(picam2.create_video_configuration(main={"size": (1280, 720)}))
    picam2.set_controls({"AfMode": controls.AfModeEnum.Continuous})
    out = StreamingOutput()
    picam2.start_recording(MJPEGEncoder(), FileOutput(out))
    return picam2, out


picam2, output = _start_camera0()
app = Flask(__name__)


def _mjpeg_generator():
    while True:
        with output.condition:
            output.condition.wait()
            frame = output.frame
        yield (b"--FRAME\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")


@app.route("/stream")
def stream():
    return Response(_mjpeg_generator(),
                    mimetype="multipart/x-mixed-replace; boundary=FRAME")


@app.route("/data")
def data():
    return jsonify(read_state())


@app.route("/")
def index():
    return render_template_string(PAGE)


# --- The kiosk page (large fonts for TV viewing distance, bilingual) --------
PAGE = r"""
<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Smart Farm — Spray Record</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { height: 100%; background: #0d0f12; color: #f2f2f2;
    font-family: "Sarabun", "Noto Sans Thai", system-ui, sans-serif;
    overflow: hidden; }
  .wrap { display: flex; height: 100vh; }
  .pane { flex: 1 1 50%; height: 100%; position: relative; }
  .left { background: #000; display: flex; align-items: center; justify-content: center; }
  .left img { width: 100%; height: 100%; object-fit: cover; }
  .cam-label { position: absolute; top: 18px; left: 18px; background: rgba(0,0,0,.55);
    padding: 8px 16px; border-radius: 8px; font-size: 26px; font-weight: 500; }
  .cam-off { color: #f0997b; font-size: 34px; text-align: center; }
  .right { background: #14181d; padding: 40px 44px; display: flex; flex-direction: column; }
  .right h1 { font-size: 34px; font-weight: 500; color: #9fe1cb; margin-bottom: 6px; }
  .sub { font-size: 22px; color: #9aa0a6; margin-bottom: 26px; }
  .banner { font-size: 40px; font-weight: 600; text-align: center; padding: 22px;
    border-radius: 14px; margin-bottom: 30px; line-height: 1.3; }
  .b-ok    { background: #10402f; color: #7ee0b8; }
  .b-warn  { background: #4a3510; color: #f5c46b; }
  .b-error { background: #4a1512; color: #f0907b; }
  .b-idle  { background: #1e242b; color: #9aa0a6; }
  .rows { flex: 1; }
  .row { display: flex; justify-content: space-between; align-items: baseline;
    padding: 16px 0; border-bottom: 1px solid #262c33; }
  .k { font-size: 24px; color: #9aa0a6; }
  .v { font-size: 30px; font-weight: 500; text-align: right; max-width: 62%; }
  .foot { font-size: 20px; color: #6b7178; margin-top: 20px; text-align: right; }
  .center { flex: 1; display: flex; align-items: center; justify-content: center;
    text-align: center; font-size: 40px; color: #9aa0a6; line-height: 1.4; }
</style>
</head>
<body>
  <div class="wrap">
    <div class="pane left">
      <img id="cam" src="/stream" alt="camera 0"
           onerror="camError()">
      <div class="cam-label">📷 กล้อง 0 — คนงาน (Worker)</div>
    </div>
    <div class="pane right">
      <h1>บันทึกการพ่นยา (Spray Record)</h1>
      <div class="sub" id="worker">—</div>
      <div id="content"></div>
      <div class="foot" id="updated"></div>
    </div>
  </div>

<script>
const FLAG_TH = {
  OK_TO_APPROVE: ["✅ ยาถูกต้อง พร้อมบันทึก", "Correct — ready to save", "b-ok"],
  EXPIRED:       ["⚠️ ยาหมดอายุ", "Chemical expired", "b-error"],
  LOW_CONFIDENCE:["⚠️ ความมั่นใจต่ำ — ตรวจสอบ", "Low confidence — please check", "b-warn"],
  NO_FK_MATCH:   ["⚠️ ไม่พบยาในระบบ", "Not found in catalog", "b-warn"],
};

function camError() {
  const img = document.getElementById('cam');
  img.style.display = 'none';
  const p = img.parentElement;
  if (!p.querySelector('.cam-off')) {
    const d = document.createElement('div');
    d.className = 'cam-off';
    d.innerHTML = '⚠️ กล้องขาดการเชื่อมต่อ<br>Camera disconnected';
    p.appendChild(d);
  }
  // try to reconnect the stream after 3s
  setTimeout(() => {
    const off = p.querySelector('.cam-off');
    if (off) off.remove();
    img.style.display = '';
    img.src = '/stream?ts=' + Date.now();
  }, 3000);
}

function row(k, v) {
  if (v === null || v === undefined || v === '') return '';
  return `<div class="row"><span class="k">${k}</span><span class="v">${v}</span></div>`;
}

function render(s) {
  const worker = document.getElementById('worker');
  const content = document.getElementById('content');
  const updated = document.getElementById('updated');
  worker.textContent = s.worker ? ('คนงาน (Worker): ' + s.worker) : '—';
  updated.textContent = s.updated_at ? ('อัปเดต ' + s.updated_at) : '';

  if (s.status === 'idle' || !s.status) {
    content.innerHTML = `<div class="center">⏳ รอการพ่นยา<br>Waiting for spraying…</div>`;
    return;
  }
  if (s.status === 'reading') {
    content.innerHTML = `<div class="center">📷 กำลังอ่านฉลาก…<br>Reading label…</div>`;
    return;
  }
  if (s.status === 'error') {
    content.innerHTML =
      `<div class="banner b-error">❌ อ่านฉลากไม่สำเร็จ<br>Label read failed</div>` +
      `<div class="center" style="font-size:26px">${s.message || ''}</div>`;
    return;
  }
  // done
  const f = FLAG_TH[s.review_flag] || ["ผลการอ่าน", "", "b-idle"];
  const conf = (s.confidence != null) ? Math.round(s.confidence * 100) + '%' : '';
  const conc = (s.concentration_percent != null) ? s.concentration_percent + '%' : '';
  content.innerHTML =
    `<div class="banner ${f[2]}">${f[0]}<br><span style="font-size:24px;font-weight:400">${f[1]}</span></div>` +
    `<div class="rows">` +
      row('ยี่ห้อ (Brand)', s.brand_name) +
      row('สารออกฤทธิ์ (Active)', s.active_ingredient) +
      row('ความเข้มข้น (Conc.)', conc) +
      row('ประเภท (Type)', s.chemical_type) +
      row('กลุ่ม (Group)', s.catalog_group) +
      row('วันหมดอายุ (Expiry)', s.expiry_date) +
      row('ความมั่นใจ (Confidence)', conf) +
    `</div>`;
}

async function poll() {
  try {
    const r = await fetch('/data', { cache: 'no-store' });
    render(await r.json());
  } catch (e) { /* keep last frame on transient error */ }
}
poll();
setInterval(poll, 1000);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    # threaded=True so the MJPEG stream and /data poll don't block each other.
    app.run(host="0.0.0.0", port=5000, threaded=True)
