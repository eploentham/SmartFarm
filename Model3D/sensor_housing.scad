$fn = 60; // ความละเอียดรูกลมสูงสุด

module s500_rail_mount() {
    difference() {
        // บล็อกยึดรางคู่
        union() {
            // แผ่นเพลทหลัก ขยายหน้ากว้างเป็น 84mm รองรับขาเดือยพิกัดใหม่
            translate([-42, -30, 0]) cube([84, 60, 5]);
            
            // บล็อกหนาสำหรับเจาะรูล็อกท่อ 10mm (ระยะห่างรางศูนย์กลางท่อ S500 คือ 60mm)
            translate([-42, -30, 5]) cube([84, 12, 12]);
            translate([-42, 18, 5]) cube([84, 12, 12]);
            
            // ขาเดือยทรงกระบอก 4 จุด พิกัดตรงกับรูชิ้นล่างเป๊ะ (X = ±33, Y = ±11)
            translate([-33, -11, -6]) cylinder(d=6, h=6);
            translate([33, -11, -6]) cylinder(d=6, h=6);
            translate([-33, 11, -6]) cylinder(d=6, h=6);
            translate([33, 11, -6]) cylinder(d=6, h=6);
        }
        
        // 1. รูเจาะสำหรับสไลด์ท่อ Carbon Fiber ขนาด 10mm (เผื่อหลวมให้สไลด์ง่าย 10.2mm)
        translate([-43, -24, 11]) rotate([0, 90, 0]) cylinder(d=10.2, h=86);
        translate([-43, 24, 11]) rotate([0, 90, 0]) cylinder(d=10.2, h=86);
        
        // รูเจาะน็อตแนวตั้งสำหรับบีบล็อกท่อคาร์บอน (ใช้สกรู M3 หนีบพลาสติก)
        translate([-25, -24, 0]) cylinder(d=3, h=20);
        translate([25, -24, 0]) cylinder(d=3, h=20);
        translate([-25, 24, 0]) cylinder(d=3, h=20);
        translate([25, 24, 0]) cylinder(d=3, h=20);

        // 2. รูเจาะสำหรับสกรู M3 สลักทะลุแกนเดือยตรงพิกัดใหม่ (X = ±33, Y = ±11)
        translate([-33, -11, -7]) cylinder(d=3, h=15);
        translate([33, -11, -7]) cylinder(d=3, h=15);
        translate([-33, 11, -7]) cylinder(d=3, h=15);
        translate([33, 11, -7]) cylinder(d=3, h=15);
    }
}

// รันโมเดลชิ้นบน
s500_rail_mount();