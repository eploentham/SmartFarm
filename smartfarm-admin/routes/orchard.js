/**
 * routes/orchard.js
 * ----------------------------------------------------------------
 * CRUD routes for orchard master tables: m_crop and m_plot.
 * Mount in app.js with:
 *   app.use('/orchard', requireAuth, require('./routes/orchard'));
 * ----------------------------------------------------------------
 */
const express = require('express');
const router = express.Router();
const db = require('../db');

// ================================================================
// Helpers
// ================================================================

const parseNum = (v) => {
  if (v === '' || v === undefined || v === null) return null;
  const n = parseFloat(v);
  return isNaN(n) ? null : n;
};

const parseInt0 = (v) => {
  if (v === '' || v === undefined || v === null) return null;
  const n = parseInt(v, 10);
  return isNaN(n) ? null : n;
};

const validateGeoJSON = (s) => {
  if (!s || s.trim() === '') return null;
  try {
    JSON.parse(s);
    return s.trim();
  } catch (e) {
    throw new Error('GeoJSON ไม่ถูกต้อง: ' + e.message);
  }
};

// ================================================================
// 🌳 m_crop — CRUD
// ================================================================

// LIST
router.get('/crops', async (req, res, next) => {
  try {
    const showInactive = req.query.show_inactive === '1';
    const whereClause = showInactive ? '' : 'WHERE is_active = 1';
    const [rows] = await db.query(
      `SELECT * FROM m_crop ${whereClause} ORDER BY crop_code`
    );
    res.render('orchard/crops_list', {
      title: 'ชนิดพืช (Crops)',
      crops: rows,
      showInactive,
      flash: req.flash()
    });
  } catch (err) { next(err); }
});

// NEW FORM
router.get('/crops/new', (req, res) => {
  res.render('orchard/crops_form', {
    title: 'เพิ่มชนิดพืชใหม่',
    crop: {},
    mode: 'create',
    flash: req.flash()
  });
});

// CREATE
router.post('/crops', async (req, res) => {
  try {
    const { crop_code, name_th, name_en, scientific_name, variety_th, notes_th } = req.body;

    if (!crop_code || !name_th || !name_en) {
      throw new Error('กรุณากรอกข้อมูลที่จำเป็น (รหัสพืช, ชื่อไทย, ชื่ออังกฤษ)');
    }

    await db.query(
      `INSERT INTO m_crop
       (crop_code, name_th, name_en, scientific_name, variety_th, notes_th, is_active)
       VALUES (?, ?, ?, ?, ?, ?, 1)`,
      [
        crop_code.toUpperCase().trim(),
        name_th.trim(),
        name_en.trim(),
        scientific_name?.trim() || null,
        variety_th?.trim() || null,
        notes_th?.trim() || null
      ]
    );

    req.flash('success', `เพิ่มชนิดพืช "${name_th}" เรียบร้อย`);
    res.redirect('/orchard/crops');
  } catch (err) {
    if (err.code === 'ER_DUP_ENTRY') {
      req.flash('error', 'รหัสพืชนี้มีอยู่แล้วในระบบ');
    } else {
      req.flash('error', err.message);
    }
    res.redirect('/orchard/crops/new');
  }
});

// EDIT FORM
router.get('/crops/:id/edit', async (req, res, next) => {
  try {
    const [rows] = await db.query('SELECT * FROM m_crop WHERE id = ?', [req.params.id]);
    if (rows.length === 0) {
      req.flash('error', 'ไม่พบชนิดพืชนี้');
      return res.redirect('/orchard/crops');
    }
    res.render('orchard/crops_form', {
      title: 'แก้ไขชนิดพืช',
      crop: rows[0],
      mode: 'edit',
      flash: req.flash()
    });
  } catch (err) { next(err); }
});

// UPDATE
router.post('/crops/:id', async (req, res) => {
  try {
    const { crop_code, name_th, name_en, scientific_name, variety_th, notes_th } = req.body;

    if (!crop_code || !name_th || !name_en) {
      throw new Error('กรุณากรอกข้อมูลที่จำเป็น');
    }

    await db.query(
      `UPDATE m_crop SET
         crop_code = ?, name_th = ?, name_en = ?,
         scientific_name = ?, variety_th = ?, notes_th = ?
       WHERE id = ?`,
      [
        crop_code.toUpperCase().trim(),
        name_th.trim(),
        name_en.trim(),
        scientific_name?.trim() || null,
        variety_th?.trim() || null,
        notes_th?.trim() || null,
        req.params.id
      ]
    );

    req.flash('success', `แก้ไข "${name_th}" เรียบร้อย`);
    res.redirect('/orchard/crops');
  } catch (err) {
    if (err.code === 'ER_DUP_ENTRY') {
      req.flash('error', 'รหัสพืชนี้มีอยู่แล้วในระบบ');
    } else {
      req.flash('error', err.message);
    }
    res.redirect(`/orchard/crops/${req.params.id}/edit`);
  }
});

// TOGGLE ACTIVE (soft delete / reactivate)
router.post('/crops/:id/toggle', async (req, res) => {
  try {
    // Check if any active plots reference this crop before deactivating
    const [current] = await db.query('SELECT is_active FROM m_crop WHERE id = ?', [req.params.id]);
    if (current.length === 0) {
      req.flash('error', 'ไม่พบชนิดพืชนี้');
      return res.redirect('/orchard/crops');
    }
    const wasActive = current[0].is_active === 1;

    if (wasActive) {
      const [usage] = await db.query(
        'SELECT COUNT(*) AS cnt FROM m_plot WHERE crop_id = ? AND is_active = 1',
        [req.params.id]
      );
      if (usage[0].cnt > 0) {
        req.flash(
          'error',
          `ไม่สามารถปิดใช้งานได้ — มีแปลงปลูกที่ active อยู่ ${usage[0].cnt} แปลง อ้างอิงพืชนี้`
        );
        return res.redirect('/orchard/crops');
      }
    }

    await db.query('UPDATE m_crop SET is_active = NOT is_active WHERE id = ?', [req.params.id]);
    req.flash('success', wasActive ? 'ปิดใช้งานเรียบร้อย' : 'เปิดใช้งานเรียบร้อย');
    res.redirect('/orchard/crops');
  } catch (err) {
    req.flash('error', err.message);
    res.redirect('/orchard/crops');
  }
});

// ================================================================
// 🗺️ m_plot — CRUD
// ================================================================

// LIST (JOIN to m_crop)
router.get('/plots', async (req, res, next) => {
  try {
    const showInactive = req.query.show_inactive === '1';
    const whereClause = showInactive ? '' : 'WHERE p.is_active = 1';
    const [rows] = await db.query(`
      SELECT p.*,
             c.crop_code  AS crop_code,
             c.name_th    AS crop_name_th,
             c.name_en    AS crop_name_en
      FROM m_plot p
      LEFT JOIN m_crop c ON p.crop_id = c.id
      ${whereClause}
      ORDER BY p.code
    `);
    res.render('orchard/plots_list', {
      title: 'แปลงปลูก (Plots)',
      plots: rows,
      showInactive,
      flash: req.flash()
    });
  } catch (err) { next(err); }
});

// NEW FORM
router.get('/plots/new', async (req, res, next) => {
  try {
    const [crops] = await db.query(
      'SELECT id, crop_code, name_th, name_en FROM m_crop WHERE is_active = 1 ORDER BY crop_code'
    );
    if (crops.length === 0) {
      req.flash('error', 'กรุณาเพิ่มชนิดพืชก่อนจึงจะสร้างแปลงปลูกได้');
      return res.redirect('/orchard/crops/new');
    }
    res.render('orchard/plots_form', {
      title: 'เพิ่มแปลงปลูกใหม่',
      plot: {},
      crops,
      mode: 'create',
      flash: req.flash()
    });
  } catch (err) { next(err); }
});

// CREATE
router.post('/plots', async (req, res) => {
  try {
    const b = req.body;

    if (!b.code || !b.name_th || !b.crop_id || !b.area_rai) {
      throw new Error('กรุณากรอกข้อมูลที่จำเป็น (รหัสแปลง, ชื่อ, ชนิดพืช, พื้นที่)');
    }

    const boundary = validateGeoJSON(b.boundary_geojson);

    await db.query(
      `INSERT INTO m_plot
       (code, name_th, name_en, crop_id, area_rai,
        tree_count, trees_per_mound, planted_year,
        center_lat, center_lon, elevation_m,
        boundary_geojson, notes_th, is_active)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)`,
      [
        b.code.toUpperCase().trim(),
        b.name_th.trim(),
        b.name_en?.trim() || null,
        parseInt0(b.crop_id),
        parseNum(b.area_rai),
        parseInt0(b.tree_count),
        parseInt0(b.trees_per_mound),
        parseInt0(b.planted_year),
        parseNum(b.center_lat),
        parseNum(b.center_lon),
        parseNum(b.elevation_m),
        boundary,
        b.notes_th?.trim() || null
      ]
    );

    req.flash('success', `เพิ่มแปลง "${b.name_th}" เรียบร้อย`);
    res.redirect('/orchard/plots');
  } catch (err) {
    if (err.code === 'ER_DUP_ENTRY') {
      req.flash('error', 'รหัสแปลงนี้มีอยู่แล้วในระบบ');
    } else if (err.code === 'ER_NO_REFERENCED_ROW_2') {
      req.flash('error', 'ไม่พบชนิดพืชที่เลือก (FK error)');
    } else {
      req.flash('error', err.message);
    }
    res.redirect('/orchard/plots/new');
  }
});

// EDIT FORM
router.get('/plots/:id/edit', async (req, res, next) => {
  try {
    const [rows] = await db.query('SELECT * FROM m_plot WHERE id = ?', [req.params.id]);
    if (rows.length === 0) {
      req.flash('error', 'ไม่พบแปลงปลูกนี้');
      return res.redirect('/orchard/plots');
    }
    // Include the plot's current crop even if inactive, so edit still works
    const [crops] = await db.query(
      'SELECT id, crop_code, name_th, name_en FROM m_crop WHERE is_active = 1 OR id = ? ORDER BY crop_code',
      [rows[0].crop_id]
    );
    res.render('orchard/plots_form', {
      title: 'แก้ไขแปลงปลูก',
      plot: rows[0],
      crops,
      mode: 'edit',
      flash: req.flash()
    });
  } catch (err) { next(err); }
});

// UPDATE
router.post('/plots/:id', async (req, res) => {
  try {
    const b = req.body;

    if (!b.code || !b.name_th || !b.crop_id || !b.area_rai) {
      throw new Error('กรุณากรอกข้อมูลที่จำเป็น');
    }

    const boundary = validateGeoJSON(b.boundary_geojson);

    await db.query(
      `UPDATE m_plot SET
         code = ?, name_th = ?, name_en = ?, crop_id = ?, area_rai = ?,
         tree_count = ?, trees_per_mound = ?, planted_year = ?,
         center_lat = ?, center_lon = ?, elevation_m = ?,
         boundary_geojson = ?, notes_th = ?
       WHERE id = ?`,
      [
        b.code.toUpperCase().trim(),
        b.name_th.trim(),
        b.name_en?.trim() || null,
        parseInt0(b.crop_id),
        parseNum(b.area_rai),
        parseInt0(b.tree_count),
        parseInt0(b.trees_per_mound),
        parseInt0(b.planted_year),
        parseNum(b.center_lat),
        parseNum(b.center_lon),
        parseNum(b.elevation_m),
        boundary,
        b.notes_th?.trim() || null,
        req.params.id
      ]
    );

    req.flash('success', `แก้ไข "${b.name_th}" เรียบร้อย`);
    res.redirect('/orchard/plots');
  } catch (err) {
    if (err.code === 'ER_DUP_ENTRY') {
      req.flash('error', 'รหัสแปลงนี้มีอยู่แล้วในระบบ');
    } else if (err.code === 'ER_NO_REFERENCED_ROW_2') {
      req.flash('error', 'ไม่พบชนิดพืชที่เลือก');
    } else {
      req.flash('error', err.message);
    }
    res.redirect(`/orchard/plots/${req.params.id}/edit`);
  }
});

// TOGGLE ACTIVE
router.post('/plots/:id/toggle', async (req, res) => {
  try {
    await db.query('UPDATE m_plot SET is_active = NOT is_active WHERE id = ?', [req.params.id]);
    req.flash('success', 'อัปเดตสถานะเรียบร้อย');
    res.redirect('/orchard/plots');
  } catch (err) {
    req.flash('error', err.message);
    res.redirect('/orchard/plots');
  }
});

module.exports = router;
