// middleware/requireAuth.js
// Redirects to /login if the user has no active session.
module.exports = function requireAuth(req, res, next) {
  if (req.session && req.session.user) {
    return next();
  }
  // remember where they were trying to go so we can redirect back after login
  req.session.returnTo = req.originalUrl;
  res.redirect('/login');
};
