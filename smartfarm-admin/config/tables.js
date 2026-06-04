// config/tables.js
// Schema configuration for all master tables.
// Field "type" values:
//   text       — single-line input
//   textarea   — multi-line input
//   number     — numeric input
//   enum       — <select> dropdown (options required)
//   boolean    — checkbox (stored as 1/0)
//   set        — multiple-select (for MariaDB SET type, options required)
//   fk         — foreign-key dropdown
//              required props: fk_table, fk_display
//              optional props: fk_value (default 'id'), fk_display_secondary

// ----- Group definitions (used to organize the dashboard) -----
const GROUPS = {
  classification: { label_th: 'การจำแนกประเภท', label_en: 'Classification', icon: '🔬', order: 1 },
  chemicals:      { label_th: 'กลุ่มสารเคมี (IRAC/FRAC)', label_en: 'Chemical Groups', icon: '🧪', order: 2 },
  products:       { label_th: 'สินค้าและผู้ผลิต', label_en: 'Products & Manufacturers', icon: '🏪', order: 3 }
};

const TABLES = {

  // ============================ Classification ============================
  pathogen_type: {
    group: 'classification',
    label_th: 'ชนิดเชื้อโรค', label_en: 'Pathogen Type', icon: '🦠',
    primary_display: 'name_th', secondary_display: 'name_en',
    has_active_flag: true,
    fields: [
      { name: 'code', label: 'รหัส (Code)', type: 'text', required: true, help: 'รหัสย่อ เช่น FUN, OOM, BAC' },
      { name: 'name_en', label: 'ชื่อ (อังกฤษ)', type: 'text', required: true },
      { name: 'name_th', label: 'ชื่อ (ไทย)', type: 'text' },
      { name: 'cell_structure', label: 'โครงสร้างเซลล์', type: 'text' },
      { name: 'description', label: 'คำอธิบาย (EN)', type: 'textarea' },
      { name: 'description_th', label: 'คำอธิบาย (ไทย)', type: 'textarea' },
      { name: 'transmission_method', label: 'วิธีแพร่กระจาย (EN)', type: 'text' },
      { name: 'transmission_method_th', label: 'วิธีแพร่กระจาย (ไทย)', type: 'text' },
      { name: 'treatment_category', label: 'หมวดการรักษา (EN)', type: 'text' },
      { name: 'treatment_category_th', label: 'หมวดการรักษา (ไทย)', type: 'text' },
      { name: 'common_examples_th', label: 'ตัวอย่างโรคที่พบ (ไทย)', type: 'text' },
      { name: 'severity_in_th_orchards', label: 'ความรุนแรง', type: 'enum',
        options: ['Low', 'Medium', 'High', 'Critical'] },
      { name: 'ai_detection_level', label: 'ระดับการตรวจจับด้วย AI', type: 'enum',
        options: ['High', 'Medium', 'Low', 'None'] },
      { name: 'icon_emoji', label: 'Icon (อีโมจิ)', type: 'text', help: 'เช่น 🍄 🌊 🦠' },
      { name: 'is_active', label: 'เปิดใช้งาน', type: 'boolean', default: 1 }
    ]
  },

  pest_master: {
    group: 'classification',
    label_th: 'แมลงศัตรูพืช', label_en: 'Pest Master', icon: '🐛',
    primary_display: 'common_name_th', secondary_display: 'common_name_en',
    has_active_flag: false,
    fields: [
      { name: 'common_name_en', label: 'ชื่อ (อังกฤษ)', type: 'text', required: true },
      { name: 'common_name_th', label: 'ชื่อ (ไทย)', type: 'text' },
      { name: 'scientific_name', label: 'ชื่อวิทยาศาสตร์', type: 'text' },
      { name: 'pest_type', label: 'ประเภท', type: 'enum',
        options: ['Insect', 'Mite', 'Snail', 'Other'] },
      { name: 'affected_part', label: 'ส่วนที่ทำลาย', type: 'set',
        options: ['Leaf', 'Stem', 'Trunk', 'Root', 'Fruit', 'Flower', 'Shoot'] },
      { name: 'host_plants', label: 'พืชอาศัย', type: 'text', help: 'เช่น Durian, Guava, Wax Apple' },
      { name: 'damage_description', label: 'การทำลาย (EN)', type: 'textarea' },
      { name: 'damage_description_th', label: 'การทำลาย (ไทย)', type: 'textarea' },
      { name: 'severity_level', label: 'ความรุนแรง', type: 'enum',
        options: ['Low', 'Medium', 'High', 'Critical'] },
      { name: 'ai_detection_level', label: 'ระดับการตรวจจับด้วย AI', type: 'enum',
        options: ['High', 'Medium', 'Low', 'None'] },
      { name: 'notes', label: 'หมายเหตุ (EN)', type: 'textarea' },
      { name: 'notes_th', label: 'หมายเหตุ (ไทย)', type: 'textarea' }
    ]
  },

  // ============================ Chemicals ============================
  frac_fungicide: {
    group: 'chemicals',
    label_th: 'ยาฆ่าเชื้อรา (FRAC)', label_en: 'Fungicide (FRAC)', icon: '💊',
    primary_display: 'active_ingredient', secondary_display: 'chemical_group_th',
    has_active_flag: true,
    fields: [
      { name: 'frac_group', label: 'กลุ่ม FRAC', type: 'text', required: true, help: 'เช่น 1, 3, 4, 11, 33, M01, BM' },
      { name: 'active_ingredient', label: 'ชื่อสารออกฤทธิ์', type: 'text', required: true, help: 'เช่น Metalaxyl, Fosetyl-Aluminium' },
      { name: 'moa_description', label: 'กลไกการออกฤทธิ์ (EN)', type: 'text' },
      { name: 'chemical_group', label: 'ชื่อกลุ่มเคมี (EN)', type: 'text' },
      { name: 'chemical_group_th', label: 'ชื่อกลุ่มเคมี (ไทย)', type: 'text' },
      { name: 'target_diseases', label: 'โรคที่ควบคุม (EN)', type: 'text' },
      { name: 'target_diseases_th', label: 'โรคที่ควบคุม (ไทย)', type: 'text' },
      { name: 'mobility', label: 'การเคลื่อนที่ในพืช', type: 'enum',
        options: ['Contact', 'Systemic', 'Translaminar', 'Locally Systemic'] },
      { name: 'action_timing', label: 'ช่วงเวลาออกฤทธิ์', type: 'enum',
        options: ['Preventive', 'Curative', 'Both'] },
      { name: 'resistance_risk', label: 'ความเสี่ยงดื้อยา', type: 'enum',
        options: ['Low', 'Medium', 'High'] },
      { name: 'typical_dose_per_l', label: 'อัตราต่อลิตรน้ำ', type: 'number', step: '0.01' },
      { name: 'dose_unit', label: 'หน่วย', type: 'enum', options: ['g', 'ml'] },
      { name: 'who_toxicity_class', label: 'WHO Toxicity Class', type: 'enum',
        options: ['Ia', 'Ib', 'II', 'III', 'U'] },
      { name: 'organic_approved', label: 'ใช้ได้ในเกษตรอินทรีย์', type: 'boolean' },
      { name: 'notes', label: 'หมายเหตุ (EN)', type: 'textarea' },
      { name: 'notes_th', label: 'หมายเหตุ (ไทย)', type: 'textarea' },
      { name: 'is_active', label: 'เปิดใช้งาน', type: 'boolean', default: 1 }
    ]
  },

  irac_insecticide: {
    group: 'chemicals',
    label_th: 'ยาฆ่าแมลง (IRAC)', label_en: 'Insecticide (IRAC)', icon: '💉',
    primary_display: 'active_ingredient', secondary_display: 'chemical_group_th',
    has_active_flag: false,
    fields: [
      { name: 'irac_group', label: 'กลุ่ม IRAC', type: 'text', required: true, help: 'เช่น 1A, 3A, 4A, 6, 28, UN' },
      { name: 'active_ingredient', label: 'ชื่อสารออกฤทธิ์', type: 'text', required: true, help: 'เช่น Abamectin, Imidacloprid' },
      { name: 'moa_description', label: 'กลไกการออกฤทธิ์ (EN)', type: 'text' },
      { name: 'chemical_group', label: 'ชื่อกลุ่มเคมี (EN)', type: 'text' },
      { name: 'chemical_group_th', label: 'ชื่อกลุ่มเคมี (ไทย)', type: 'text' },
      { name: 'target_pests', label: 'แมลงที่ควบคุม (EN)', type: 'text' },
      { name: 'target_pests_th', label: 'แมลงที่ควบคุม (ไทย)', type: 'text' },
      { name: 'typical_dose_ml_per_l', label: 'อัตราต่อลิตรน้ำ (ml)', type: 'number', step: '0.01' },
      { name: 'who_toxicity_class', label: 'WHO Toxicity Class', type: 'enum',
        options: ['Ia', 'Ib', 'II', 'III', 'U'] },
      { name: 'bee_toxic', label: 'พิษต่อผึ้ง 🐝', type: 'boolean' },
      { name: 'banned_in_th', label: 'ถูกแบนในประเทศไทย', type: 'boolean' },
      { name: 'organic_approved', label: 'ใช้ได้ในเกษตรอินทรีย์', type: 'boolean' },
      { name: 'notes', label: 'หมายเหตุ (EN)', type: 'textarea' },
      { name: 'notes_th', label: 'หมายเหตุ (ไทย)', type: 'textarea' }
    ]
  },

  // ============================ Products ============================
  manufacturer: {
    group: 'products',
    label_th: 'บริษัทผู้ผลิต', label_en: 'Manufacturer', icon: '🏢',
    primary_display: 'name_th', secondary_display: 'name_en',
    has_active_flag: true,
    fields: [
      { name: 'name_th', label: 'ชื่อบริษัท (ไทย)', type: 'text', required: true,
        help: 'เช่น บริษัท โซตัส อินเตอร์เนชั่นแนล จำกัด' },
      { name: 'name_en', label: 'Company name (EN)', type: 'text' },
      { name: 'website_url', label: 'เว็บไซต์', type: 'text', help: 'https://...' },
      { name: 'phone', label: 'โทรศัพท์', type: 'text' },
      { name: 'email', label: 'อีเมล', type: 'text' },
      { name: 'address', label: 'ที่อยู่', type: 'textarea' },
      { name: 'country', label: 'ประเทศ', type: 'text', default: 'Thailand' },
      { name: 'notes', label: 'หมายเหตุ', type: 'textarea' },
      { name: 'is_active', label: 'เปิดใช้งาน', type: 'boolean', default: 1 }
    ]
  },

  chemical_product: {
    group: 'products',
    label_th: 'สินค้ายาเกษตร', label_en: 'Chemical Product', icon: '🧴',
    primary_display: 'product_name', secondary_display: 'product_name_en',
    has_active_flag: true,
    fields: [
      { name: 'product_name', label: 'ชื่อทางการค้า (ไทย)', type: 'text', required: true,
        help: 'เช่น เซฟวิน 85, คาร์บาริล' },
      { name: 'product_name_en', label: 'Brand name (EN)', type: 'text' },
      { name: 'manufacturer_id', label: 'บริษัทผู้ผลิต', type: 'fk', required: true,
        fk_table: 'manufacturer', fk_value: 'id',
        fk_display: 'name_th', fk_display_secondary: 'name_en' },
      { name: 'chemical_type', label: 'ประเภท', type: 'enum', required: true,
        options: ['Insecticide', 'Fungicide', 'Herbicide', 'Other'] },
      { name: 'insecticide_id', label: 'สารออกฤทธิ์ (IRAC)', type: 'fk',
        fk_table: 'irac_insecticide', fk_value: 'id',
        fk_display: 'active_ingredient', fk_display_secondary: 'irac_group',
        help: 'เลือกถ้าเป็นยาฆ่าแมลง - ปล่อยว่างถ้าเป็นยาฆ่าเชื้อรา' },
      { name: 'fungicide_id', label: 'สารออกฤทธิ์ (FRAC)', type: 'fk',
        fk_table: 'frac_fungicide', fk_value: 'id',
        fk_display: 'active_ingredient', fk_display_secondary: 'frac_group',
        help: 'เลือกถ้าเป็นยาฆ่าเชื้อรา - ปล่อยว่างถ้าเป็นยาฆ่าแมลง' },
      { name: 'formulation', label: 'รูปแบบ', type: 'text', help: 'เช่น 85% WP, 10% EC, 5% GR' },
      { name: 'package_size', label: 'ขนาดบรรจุ', type: 'text', help: 'เช่น 100g, 500ml, 1kg' },
      { name: 'product_url', label: 'ลิงก์สินค้า', type: 'text' },
      { name: 'registration_no', label: 'เลขทะเบียนวัตถุอันตราย', type: 'text' },
      { name: 'price_baht', label: 'ราคา (บาท)', type: 'number', step: '0.01' },
      { name: 'notes_th', label: 'หมายเหตุ', type: 'textarea' },
      { name: 'is_active', label: 'เปิดใช้งาน', type: 'boolean', default: 1 }
    ]
  }

};

module.exports = TABLES;
module.exports.GROUPS = GROUPS;
