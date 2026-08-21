# 🚁 SKY (pi5drone1) — Vision Roadmap: บินถ่ายรอยโรคให้คมที่สุด

> Research note — เก็บชุดความคิด "โดรนบินหามุม+ระยะที่ดีที่สุด เพื่อถ่ายรอยโรคลำต้น/โคนต้นให้คม"
> ยังไม่ทำตอนนี้ (รอ spray Part 3+4 เสร็จ + โดรนบินเสถียร) แต่บางส่วน (ปัญหา 3) **ทำแยกบนโต๊ะได้เลย**

---

## 🎯 โจทย์ใหญ่

**pi5drone1 (SKY)** ติด CSI 2 ตัว:
```
CSI หน้า      → คู่กับ D435i (depth) → นำทาง / หลบสิ่งกีดขวาง / วัดระยะ
CSI ล่าง 45°  → ส่องลำต้น/โคนต้น ดูรอยโรค (ไม่ใช่ส่องพื้นตรงๆ — เอียงดูลำต้น)
```

**เป้าหมาย:** บินไปถ่าย **โคนต้น/ลำต้นที่สงสัยเป็นโรค** ให้ได้ **ภาพคมที่สุด** เพื่อส่ง Gemini วินิจฉัย

**ความท้าทายที่เจ้าของระบุ:**
1. ลำต้นหน้าตาเหมือนกันหมด → **รอยโรค**เป็นตัวชี้ว่า "ต้นนี้แหละ"
2. รอยโรคมักถ่ายไม่ชัด → ต้อง**บินปรับมุม**ให้เห็นชัด
3. มุมดีแล้ว แต่**ระยะโฟกัสไม่ชัด** → ต้องปรับ focus CSI
4. **YOLO ต้องรู้ว่า "เห็นรอยโรคแล้ว แต่ยังไม่คมพอ"** ← หัวใจ

---

## 🧩 แยกเป็น 4 ปัญหาย่อย (แต่ละอันแก้คนละวิธี)

### ปัญหา 1: "ต้นไหนที่ต้องไปดู?" — detection + localization
- CSI ล่าง 45° สแกนตอนบินผ่าน → YOLO เห็นรอยโรคจากภาพกว้าง → ได้ candidate + พิกัดคร่าว
- prerequisite: model detect รอยโรค (ยังไม่มี — ต้องเก็บภาพ+เทรน)

### ปัญหา 2: "บินไปมุมไหนถึงเห็นรอยโรคชัด?" — viewpoint optimization ⚠️ ยากสุด
- รอยโรคอาจอยู่ด้านที่โดรนมองไม่เห็น → ต้องบินรอบ/ปรับมุม
- นี่คือ **active vision** (ขยับเพื่อดูให้ดีขึ้น ไม่ใช่ถ่ายนิ่ง)
- **ยังเป็น research problem เปิดในวงการ robotics** — ไม่มีสูตรสำเร็จ ต้องลองหลาย approach
- prerequisite: โดรนบินเสถียร + control loop + obstacle avoidance (D435i) ก่อน

### ปัญหา 3: "ภาพนี้ชัดพอหรือยัง?" — sharpness/quality scoring ✅ ทำแยกก่อนได้
- **หัวใจ** ที่ปัญหาอื่นต้องพึ่ง (จะปรับ focus/หามุมได้ ต้องวัดคม/เบลอก่อน)
- **ทำบนโต๊ะได้เลย ไม่ต้องรอโดรน** ← เริ่มจากอันนี้
- (เจาะลึกด้านล่าง)

### ปัญหา 4: "ปรับ focus CSI ยังไงให้คม" — detect-driven focus (ROI)
- ต่อยอดจาก spray system: YOLO ชี้รอยโรค (box) → กล้อง focus บริเวณนั้น (`AfWindows`)
- reuse หลักการ detect-driven focus ตรงๆ (ดู handoff spray Part 4)

---

## 🔬 เจาะลึกปัญหา 3: "เห็นรอยโรคแล้ว แต่คมพอไหม?"

### แยก 2 สัญญาณอิสระ (กับดักที่คนพลาด)
```
สัญญาณ A: "เจอรอยโรคไหม?"  → detection (YOLO confidence + box)
สัญญาณ B: "ภาพคมพอไหม?"    → sharpness (วัดแยก ไม่พึ่ง YOLO)
```
**ทำไมต้องแยก:** YOLO อาจ "เดา" ว่าเจอโรคทั้งที่เบลอ (conf สูงได้แม้เบลอ ถ้ารูปทรงคุ้น)
→ เอา YOLO conf มาตัดสินความชัด = พลาด ต้องมีตัววัดความคม **อิสระ**

### ตัววัดความคม: Laplacian variance (เร็ว ฟรี รันบน Pi5 ได้ / reuse จาก grass index)
```python
import cv2
def sharpness_score(image_bgr):
    """สูง = คม, ต่ำ = เบลอ (Laplacian จับ edge: คม→ขอบชัด→variance สูง)"""
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()
```

### 🔴 3 Traps ที่ทำให้ Laplacian variance พลาด (ต้องเข้าใจ)

**Trap 1: วัดเฉพาะ ROI รอยโรค ไม่ใช่ทั้งภาพ**
- วัดทั้งภาพ → ใบไม้/พื้นรกๆ มี edge เยอะ ค่าสูงทั้งที่รอยโรคเบลอ → หลอกตา
- แก้: YOLO ให้ box → crop ROI → วัดแค่ตรงนั้น
```python
box = yolo_detect_disease(frame)
roi = frame[box.y:box.y+box.h, box.x:box.x+box.w]
score = sharpness_score(roi)     /* A บอก "ที่ไหน" → B บอก "คมพอไหม ตรงนั้น" */
```

**Trap 2: ค่า Laplacian เทียบข้ามภาพไม่ได้ตรงๆ (สำคัญมาก)**
- ค่าขึ้นกับ texture: เปลือกไม้หยาบ > ใบเรียบ โดยความคมเท่ากัน
- threshold ตายตัว "ถ้า >100 = คม" **ใช้ไม่ได้ทั่วไป**
- แก้: ใช้แบบ **relative** — ถ่ายหลายเฟรม (ขยับ focus/มุมนิดๆ) → เทียบกันเอง → คมสุดในชุด = ดีสุด
  (เหมือน autofocus: ไม่รู้ค่าคมสัมบูรณ์ แต่รู้ว่า "ทางนี้คมขึ้น/ลง")

**Trap 3: เบลอ 2 แบบ คนละสาเหตุ คนละวิธีแก้**
```
Out-of-focus blur (โฟกัสไม่เข้า) → ปรับ LensPosition / ROI focus
Motion blur (โดรนสั่น/ขยับ)      → บินนิ่งขึ้น / shutter เร็ว / gimbal
```
- Laplacian บอกแค่ "เบลอ" ไม่บอกว่าแบบไหน → motion blur แล้วไปปรับ focus = แก้ผิดจุด
- แก้เบื้องต้น: hover นิ่งแล้วยังเบลอ = out-of-focus / เบลอเป็นทาง (directional) = motion

### สถาปัตยกรรมปัญหา 3 (วัดชัด → ตัดสินใจ)
```
เฟรม CSI ล่าง
   │
   ▼
[YOLO detect โรค] ──เจอ?──> box (สัญญาณ A)
   │ ไม่เจอ                   │
   ▼                         ▼
บินสแกนต่อ        [crop ROI → Laplacian var] (สัญญาณ B)
                             │
              ┌──────────────┼──────────────┐
          score ต่ำมาก    score กลาง     score สูง
            (เบลอ)        (พอใช้)        (คม)
              │              │              │
        ปรับ focus /     ขยับนิดๆ       📸 เก็บภาพ
        เข้าใกล้         หามุมดีขึ้น    → Gemini วินิจฉัย
```

---

## ▶️ จุดเริ่มที่ทำได้เลย (ปัญหา 3 บนโต๊ะ — ไม่ต้องมีโดรน)

**Prototype ทดสอบ sharpness (แยกส่วนทำก่อนได้):**
1. CSI (imx708) + ภาพลำต้น/รอยโรคจริง (มีตัวอย่างในสวนเยอะ)
2. ถ่ายหลายระยะ focus (คม → เบลอ) วางบนโต๊ะ
3. วัด Laplacian variance ของ ROI → ดูว่าค่าแยกคม/เบลอได้จริงไหม
4. ทดลอง **relative focus sweep**: หมุน LensPosition ทีละสเต็ป → หา peak ของ sharpness (จุดคมสุด)
5. หา threshold / วิธี relative ที่ใช้ได้ในสวนจริง

→ พิสูจน์ปัญหา 3 บนโต๊ะ **ก่อน** เอาขึ้นโดรน = ลดความเสี่ยง (step-by-step)

---

## 🔗 อะไร reuse จากระบบที่มีแล้ว

| ต้องการ | reuse จาก |
|---|---|
| detect-driven focus (ROI + AfWindows) | spray Part 4 (bottle_capture) |
| Laplacian variance | แผน grass index (Feature B) |
| YOLO detection pipeline | spray receiver (mqtt_yolo_receiver) |
| MQTT event bus (drn/ topics) | สถาปัตยกรรม SFC2 |
| Gemini วินิจฉัยภาพ | spray gemini_extract (เปลี่ยน prompt เป็นวินิจฉัยโรค) |

---

## 📋 Prerequisites (ต้องมีก่อนทำเต็มระบบ)

```
ปัญหา 3 (sharpness)  → ไม่มี prereq ทำบนโต๊ะได้เลย ✅
ปัญหา 4 (ROI focus)  → ต้องมี detect model + ปัญหา 3
ปัญหา 1 (detect โรค) → ต้องเก็บภาพรอยโรค + เทรน model
ปัญหา 2 (viewpoint)  → ต้องมี: โดรนบินเสถียร + control loop + D435i obstacle avoidance
                       + ปัญหา 1,3,4 ครบก่อน (ยากสุด ทำท้ายสุด)
```

---

## 💡 Insight หลัก (เก็บไว้)

**"detect-driven everything"** — หลักการกลางของทั้งระบบ SKY/RVR/SCOUT:
> AI (YOLO) เป็นตา → เห็นอะไร/ที่ไหน → สั่ง hardware (focus/บิน/gimbal) ไปตรงนั้น → เห็นชัดขึ้น → วนซ้ำ

นี่คือ **closed loop** ระหว่าง perception (มองเห็น) กับ action (ขยับ) — หัวใจของ "ระบบปฏิบัติการเกษตร"
ที่ node ทุกตัวควรมี: SKY (focus ใบเป็นโรค), RVR (focus วัชพืช), SCOUT (focus แมลง/รอยกัด)

**คำเตือน (honest):** ปัญหา 2 (viewpoint optimization) เป็น research problem จริง — อย่าคาดหวังสูตรสำเร็จ
เริ่มจากปัญหา 3 (วัดได้/พิสูจน์ได้) แล้วค่อยไต่ขึ้นไป ทำทีละชิ้นตามที่แยกส่วนได้