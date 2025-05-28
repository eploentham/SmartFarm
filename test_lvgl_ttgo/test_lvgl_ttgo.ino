#include <lvgl.h>
#include <TFT_eSPI.h>

// ระบุขนาดจอของ TTGO (ปรับตามรุ่นที่คุณใช้)
#define SCREEN_WIDTH  135  // ความกว้างจอ TTGO
#define SCREEN_HEIGHT 240  // ความสูงจอ TTGO
enum ValveState {
    IDLE,       // พัก
    OPENING,    // กำลังเปิด
    RUNNING,    // กำลังทำงาน
    CLOSING     // กำลังปิด
}

// ตัวแปรสำหรับวาล์วแต่ละตัว
struct Valve {
    ValveState state;
    unsigned long startTime;
    unsigned long duration;
    bool isRunning;
    int pin;
    const char* name;
};
// สร้างอ็อบเจ็กต์ TFT
TFT_eSPI tft = TFT_eSPI();

// สร้าง buffer สำหรับ LVGL
static lv_disp_draw_buf_t draw_buf;
static lv_color_t buf[SCREEN_WIDTH * 10]; // ใช้ buffer ขนาด 1/10 ของหน้าจอ

// ฟังก์ชันสำหรับ flush จอแสดงผล
void my_disp_flush(lv_disp_drv_t *disp, const lv_area_t *area, lv_color_t *color_p)
{
    uint32_t w = (area->x2 - area->x1 + 1);
    uint32_t h = (area->y2 - area->y1 + 1);

    tft.startWrite();
    tft.setAddrWindow(area->x1, area->y1, w, h);
    tft.pushColors((uint16_t*)color_p, w * h, true);
    tft.endWrite();

    lv_disp_flush_ready(disp);
}

void setup() {
    Serial.begin(115200);
    
    // เริ่มต้น TFT
    tft.begin();
    tft.setRotation(1); // ปรับการหมุนหน้าจอตามความเหมาะสม
    
    // เริ่มต้น LVGL
    lv_init();
    
    // จัดการ buffer สำหรับการวาด
    lv_disp_draw_buf_init(&draw_buf, buf, NULL, SCREEN_WIDTH * 10);
    
    // จัดการไดรเวอร์การแสดงผล
    static lv_disp_drv_t disp_drv;
    lv_disp_drv_init(&disp_drv);
    disp_drv.hor_res = SCREEN_WIDTH;
    disp_drv.ver_res = SCREEN_HEIGHT;
    disp_drv.flush_cb = my_disp_flush;
    disp_drv.draw_buf = &draw_buf;
    lv_disp_drv_register(&disp_drv);
    
    // สร้าง UI ตัวอย่าง
    // สร้างปุ่ม
    lv_obj_t *btn = lv_btn_create(lv_scr_act());
    lv_obj_align(btn, LV_ALIGN_CENTER, 0, -40); // จัดวางตรงกลาง เลื่อนขึ้นด้านบนเล็กน้อย
    
    // สร้างเลเบลภายในปุ่ม
    lv_obj_t *label = lv_label_create(btn);
    lv_label_set_text(label, "Smart Farm");
    lv_obj_center(label);
    
    // สร้างเลเบลสำหรับอุณหภูมิ
    lv_obj_t *temp_label = lv_label_create(lv_scr_act());
    lv_label_set_text(temp_label, "Temp: 28.5 C");
    lv_obj_align(temp_label, LV_ALIGN_CENTER, 0, 0);
    
    // สร้างเลเบลสำหรับความชื้น
    lv_obj_t *humid_label = lv_label_create(lv_scr_act());
    lv_label_set_text(humid_label, "Humidity: 65%");
    lv_obj_align(humid_label, LV_ALIGN_CENTER, 0, 30);
    
    // สร้างเลเบลสำหรับสถานะ MQTT
    lv_obj_t *mqtt_label = lv_label_create(lv_scr_act());
    lv_label_set_text(mqtt_label, "MQTT: Disconnected");
    lv_obj_set_style_text_color(mqtt_label, lv_color_hex(0xFF0000), LV_PART_MAIN | LV_STATE_DEFAULT); // สีแดง
    lv_obj_align(mqtt_label, LV_ALIGN_BOTTOM_LEFT, 10, -10);
}

void loop() {
    lv_timer_handler(); // จัดการงานของ LVGL (ต้องเรียกเป็นประจำ)
    delay(5);
}