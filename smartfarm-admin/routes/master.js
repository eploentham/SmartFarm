// routes/master.js
// Generic CRUD for any table defined in config/tables.js.
// Adds support for `fk` field type — renders proper dropdowns and joins on list pages.

const express = require('express');
const router = express.Router();
const { pool } = require('../db');
const TABLES = require('../config/tables');

// ---------- helpers --------------------------------------------------------

function tableConfig(name) {
  return TABLES[name] || null;
}

// Convert form body values to DB-ready values per the field config.
function buildRowFromBody(body, fields) {
  const row = {};
  for (const f of fields) {
    let v = body[f.name];
    if (f.type === 'boolean') {
      row[f.name] = v ? 1 : 0;
    } else if (f.type === 'set') {
      if (Array.isArray(v)) row[f.name] = v.join(',');
      else if (v) row[f.name] = v;
      else row[f.name] = null;
    } else if (f.type === 'number' || f.type === 'fk') {
      // fk values are stored as integers
      row[f.name] = v === '' || v == null ? null : Number(v);
    } else {
      row[f.name] = v === '' || v == null ? null : String(v).trim();
    }
  }
  return row;
}

// Fetch dropdown options for every fk field in the table config.
async function fetchFkOptions(cfg) {
  const out = {};
  const fkFields = cfg.fields.filter(f => f.type === 'fk');
  for (const f of fkFields) {
    const valueCol = f.fk_value || 'id';
    const orderBy = f.fk_display || valueCol;
    const cols = [
      `\`${valueCol}\` AS value`,
      `\`${f.fk_display}\` AS display`
    ];
    if (f.fk_display_secondary) {
      cols.push(`\`${f.fk_display_secondary}\` AS display2`);
    }
    const sql = `SELECT ${cols.join(', ')} FROM \`${f.fk_table}\` ORDER BY \`${orderBy}\``;
    const [rows] = await pool.query(sql);
    out[f.name] = rows;
  }
  return out;
}

// Build SELECT + LEFT JOINs to bring in FK display names for the list page.
// Returns { sql, fkFieldNames } — fkFieldNames maps each fk field to its display alias.
function buildListQuery(tableName, cfg) {
  const fkFields = cfg.fields.filter(f => f.type === 'fk');
  const joins = [];
  const extras = [];
  fkFields.forEach((f, idx) => {
    const alias = `__fk${idx}__`;
    const valueCol = f.fk_value || 'id';
    joins.push(
      `LEFT JOIN \`${f.fk_table}\` \`${alias}\` ON main.\`${f.name}\` = \`${alias}\`.\`${valueCol}\``
    );
    extras.push(`\`${alias}\`.\`${f.fk_display}\` AS \`__${f.name}_display__\``);
  });
  const selectClause = extras.length ? `main.*, ${extras.join(', ')}` : 'main.*';
  const joinClause = joins.length ? ' ' + joins.join(' ') : '';
  const sql = `SELECT ${selectClause} FROM \`${tableName}\` main${joinClause} ORDER BY main.id DESC`;
  return sql;
}

// ---------- ROUTES ---------------------------------------------------------

// GET /master/:table — list rows
router.get('/:table', async (req, res, next) => {
  try {
    const tableName = req.params.table;
    const cfg = tableConfig(tableName);
    if (!cfg) return res.status(404).send('Unknown table');

    const sql = buildListQuery(tableName, cfg);
    const [rows] = await pool.query(sql);

    res.render('master/list', {
      tableName, cfg, rows,
      success: req.flash('success')[0] || null,
      error: req.flash('error')[0] || null
    });
  } catch (err) { next(err); }
});

// GET /master/:table/new — empty form
router.get('/:table/new', async (req, res, next) => {
  try {
    const tableName = req.params.table;
    const cfg = tableConfig(tableName);
    if (!cfg) return res.status(404).send('Unknown table');

    const row = {};
    for (const f of cfg.fields) row[f.name] = f.default !== undefined ? f.default : '';
    const fkOptions = await fetchFkOptions(cfg);

    res.render('master/form', {
      tableName, cfg, row, mode: 'new', fkOptions,
      error: req.flash('error')[0] || null
    });
  } catch (err) { next(err); }
});

// POST /master/:table — create
router.post('/:table', async (req, res) => {
  const tableName = req.params.table;
  const cfg = tableConfig(tableName);
  if (!cfg) return res.status(404).send('Unknown table');

  try {
    const row = buildRowFromBody(req.body, cfg.fields);
    const cols = Object.keys(row);
    const placeholders = cols.map(() => '?').join(', ');
    const values = cols.map(c => row[c]);
    const sql = `INSERT INTO \`${tableName}\` (${cols.map(c => '`' + c + '`').join(', ')}) VALUES (${placeholders})`;
    await pool.query(sql, values);
    req.flash('success', 'เพิ่มข้อมูลใหม่เรียบร้อย');
    res.redirect(`/master/${tableName}`);
  } catch (err) {
    console.error('Insert error:', err);
    req.flash('error', 'เพิ่มข้อมูลไม่สำเร็จ: ' + err.message);
    res.redirect(`/master/${tableName}/new`);
  }
});

// GET /master/:table/:id/edit — prefilled form
router.get('/:table/:id/edit', async (req, res, next) => {
  try {
    const tableName = req.params.table;
    const cfg = tableConfig(tableName);
    if (!cfg) return res.status(404).send('Unknown table');

    const [rows] = await pool.query(
      `SELECT * FROM \`${tableName}\` WHERE id = ?`, [req.params.id]
    );
    if (rows.length === 0) return res.status(404).send('Row not found');

    const fkOptions = await fetchFkOptions(cfg);
    res.render('master/form', {
      tableName, cfg, row: rows[0], mode: 'edit', fkOptions,
      error: req.flash('error')[0] || null
    });
  } catch (err) { next(err); }
});

// POST /master/:table/:id — update
router.post('/:table/:id', async (req, res) => {
  const tableName = req.params.table;
  const cfg = tableConfig(tableName);
  if (!cfg) return res.status(404).send('Unknown table');

  try {
    const row = buildRowFromBody(req.body, cfg.fields);
    const cols = Object.keys(row);
    const setClause = cols.map(c => '`' + c + '` = ?').join(', ');
    const values = cols.map(c => row[c]);
    values.push(req.params.id);
    const sql = `UPDATE \`${tableName}\` SET ${setClause} WHERE id = ?`;
    await pool.query(sql, values);
    req.flash('success', 'บันทึกการแก้ไขเรียบร้อย');
    res.redirect(`/master/${tableName}`);
  } catch (err) {
    console.error('Update error:', err);
    req.flash('error', 'บันทึกไม่สำเร็จ: ' + err.message);
    res.redirect(`/master/${tableName}/${req.params.id}/edit`);
  }
});

// POST /master/:table/:id/delete — soft- or hard-delete
router.post('/:table/:id/delete', async (req, res) => {
  const tableName = req.params.table;
  const cfg = tableConfig(tableName);
  if (!cfg) return res.status(404).send('Unknown table');

  try {
    if (cfg.has_active_flag) {
      await pool.query(`UPDATE \`${tableName}\` SET is_active = 0 WHERE id = ?`, [req.params.id]);
      req.flash('success', 'ปิดใช้งานเรียบร้อย (Soft delete)');
    } else {
      await pool.query(`DELETE FROM \`${tableName}\` WHERE id = ?`, [req.params.id]);
      req.flash('success', 'ลบข้อมูลเรียบร้อย');
    }
    res.redirect(`/master/${tableName}`);
  } catch (err) {
    console.error('Delete error:', err);
    req.flash('error', 'ลบไม่สำเร็จ: ' + err.message + ' (อาจมีข้อมูลอื่นอ้างอิงอยู่)');
    res.redirect(`/master/${tableName}`);
  }
});

module.exports = router;
