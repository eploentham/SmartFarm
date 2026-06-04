# 🚀 Smart Farm Admin — Upgrade v2

This upgrade adds:
- ✅ **Two new pages**: `manufacturer` (บริษัทผู้ผลิต) and `chemical_product` (สินค้ายาเกษตร)
- ✅ **FK dropdowns** — when adding a product, you pick a company from a list (no more typing IDs!)
- ✅ **Grouped main page** — tables organized into Classification / Chemicals / Products sections
- ✅ **Grouped navbar** — dropdown menus by category

---

## 📦 What's in the Zip

```
upgrade/
├── config/
│   └── tables.js              ← REPLACE  (new entries + group property)
├── routes/
│   └── master.js              ← REPLACE  (fk field support + JOIN for list)
├── views/
│   ├── dashboard.ejs          ← REPLACE  (grouped sections)
│   ├── partials/
│   │   └── navbar.ejs         ← REPLACE  (dropdown menus)
│   └── master/
│       ├── form.ejs           ← REPLACE  (renders fk as dropdown)
│       └── list.ejs           ← REPLACE  (shows fk display names)
├── style-additions.css        ← APPEND to your public/css/style.css
└── UPGRADE.md                 ← this file
```

---

## 🛠️ How to Apply

### Step 1: Make sure the DB tables exist

Run the `CREATE TABLE manufacturer` and `CREATE TABLE chemical_product` scripts (and the foreign keys) from the previous response, if you haven't already. Insert at least Sotus + Sevin 85 + Packing Ag + คาร์บาริล as sample data.

Quick check:
```sql
SELECT COUNT(*) FROM manufacturer;       -- should be >= 1
SELECT COUNT(*) FROM chemical_product;   -- should be >= 1
```

### Step 2: Copy the upgrade files over your project

From your `smartfarm-admin` folder:

```bash
# Copy the 6 changed files (overwrite existing)
cp /path/to/upgrade/config/tables.js          ./config/tables.js
cp /path/to/upgrade/routes/master.js          ./routes/master.js
cp /path/to/upgrade/views/dashboard.ejs       ./views/dashboard.ejs
cp /path/to/upgrade/views/partials/navbar.ejs ./views/partials/navbar.ejs
cp /path/to/upgrade/views/master/form.ejs     ./views/master/form.ejs
cp /path/to/upgrade/views/master/list.ejs     ./views/master/list.ejs
```

### Step 3: Append the CSS

Open `public/css/style.css` and paste the contents of `style-additions.css` at the bottom.

Or run:
```bash
cat /path/to/upgrade/style-additions.css >> ./public/css/style.css
```

### Step 4: Restart the server

```bash
# If using npm start
# Ctrl+C to stop, then:
npm start

# If using systemd:
sudo systemctl restart smartfarm-admin
```

### Step 5: Verify

Open http://localhost:3000 — you should see:
- 🔬 **Classification** section (pathogen_type, pest_master)
- 🧪 **Chemical Groups** section (frac_fungicide, irac_insecticide)
- 🏪 **Products & Manufacturers** section (manufacturer, chemical_product) ← NEW!

Click **🧴 สินค้ายาเกษตร → ➕ เพิ่มข้อมูลใหม่** — the manufacturer field should now be a proper dropdown listing your companies. 🎉

---

## 🆕 What's New: The `fk` Field Type

In `config/tables.js`, you can now define foreign-key fields:

```javascript
{
  name: 'manufacturer_id',
  label: 'บริษัทผู้ผลิต',
  type: 'fk',
  fk_table: 'manufacturer',          // table to look up
  fk_value: 'id',                     // column to use as the saved value (default 'id')
  fk_display: 'name_th',              // column to show in the dropdown
  fk_display_secondary: 'name_en',    // optional - shown after middot
  required: true
}
```

The framework will:
- ✅ Auto-populate the dropdown from the `fk_table`
- ✅ JOIN to that table on list pages to show the display name (not the bare id)
- ✅ Store the foreign-key value correctly

Use this for any future tables (e.g. mapping tables, transaction logs).

---

## 🌾 What's Next

After you confirm this works, the next phases are:
- **Phase 2**: mapping tables (`disease_fungicide_map`, `pest_insecticide_map`) using the new `fk` type
- **Phase 3**: the farmer-facing spray-log form (`t_chemical_application`)
- **Phase 4**: read-only dashboards (sensors, irrigation, resistance warnings)
