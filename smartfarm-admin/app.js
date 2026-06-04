// app.js — Smart Farm Admin
// Main Express entry point. Wires up sessions, flash messages, views, and routes.

require('dotenv').config();
const path = require('path');
const express = require('express');
const session = require('express-session');
const flash = require('connect-flash');

const { testConnection } = require('./db');
const requireAuth = require('./middleware/requireAuth');
const authRoutes = require('./routes/auth');
const masterRoutes = require('./routes/master');
const TABLES = require('./config/tables');
const orchardRoutes = require('./routes/orchard');

const app = express();

// ----- view engine ---------------------------------------------------------
app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));

// ----- static & body parsing ----------------------------------------------
app.use(express.static(path.join(__dirname, 'public')));
app.use(express.urlencoded({ extended: true }));
app.use(express.json());

// ----- session + flash -----------------------------------------------------
app.use(session({
  secret: process.env.SESSION_SECRET || 'change-me-in-production',
  resave: false,
  saveUninitialized: false,
  cookie: { httpOnly: true, maxAge: 1000 * 60 * 60 * 8 } // 8 hours
}));
app.use(flash());

// expose session user + tables to all templates
app.use((req, res, next) => {
  res.locals.currentUser = req.session.user || null;
  res.locals.TABLES = TABLES;
  res.locals.currentPath = req.path;
  next();
});

// ----- routes --------------------------------------------------------------
app.use('/', authRoutes);

// dashboard (requires login)
app.get('/', requireAuth, (req, res) => {
  res.render('dashboard');
});

// master CRUD (all require login)
app.use('/master', requireAuth, masterRoutes);

// 404
app.use((req, res) => {
  res.status(404).render('error', { message: 'ไม่พบหน้าที่ต้องการ (404)' });
});

// generic error handler
app.use((err, req, res, next) => {
  console.error('App error:', err);
  res.status(500).render('error', { message: err.message || 'เกิดข้อผิดพลาด' });
});

// ----- start ---------------------------------------------------------------
const PORT = process.env.PORT || 3000;

(async () => {
  const dbOk = await testConnection();
  if (!dbOk) {
    console.error('⚠️  Could not connect to MariaDB. Check your .env settings.');
    console.error('    The server will start anyway, but DB pages will fail.');
  } else {
    console.log('✅ Database connection OK');
  }
  app.listen(PORT, () => {
    console.log(`🌳 Smart Farm Admin running on http://localhost:${PORT}`);
    console.log(`   Default login: admin / admin123  (CHANGE in .env!)`);
  });
})();
