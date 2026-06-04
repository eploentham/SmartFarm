// routes/auth.js
// Handles login form display, login POST submission, and logout.
const express = require('express');
const bcrypt = require('bcryptjs');
const router = express.Router();

// GET /login — show form
router.get('/login', (req, res) => {
  if (req.session && req.session.user) {
    return res.redirect('/');
  }
  res.render('login', {
    error: req.flash('error')[0] || null,
    info: req.flash('info')[0] || null
  });
});

// POST /login — validate credentials
router.post('/login', async (req, res) => {
  const { username, password } = req.body;
  const expectedUser = process.env.ADMIN_USERNAME || 'admin';
  const expectedHash = process.env.ADMIN_PASSWORD_HASH;

  if (!username || !password) {
    req.flash('error', 'กรุณากรอกชื่อผู้ใช้และรหัสผ่าน');
    return res.redirect('/login');
  }

  if (username !== expectedUser) {
    req.flash('error', 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง');
    return res.redirect('/login');
  }

  try {
    const ok = expectedHash ? await bcrypt.compare(password, expectedHash) : false;
    if (!ok) {
      req.flash('error', 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง');
      return res.redirect('/login');
    }
    req.session.user = { username };
    const redirectTo = req.session.returnTo || '/';
    delete req.session.returnTo;
    res.redirect(redirectTo);
  } catch (err) {
    console.error('Login error:', err);
    req.flash('error', 'เกิดข้อผิดพลาดในการเข้าสู่ระบบ');
    res.redirect('/login');
  }
});

// POST /logout
router.post('/logout', (req, res) => {
  req.session.destroy(() => {
    res.redirect('/login');
  });
});

module.exports = router;
