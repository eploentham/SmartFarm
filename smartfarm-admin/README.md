# 🌳 Smart Farm Admin

Node.js web admin for managing the smartfarm master tables on your Raspberry Pi 5.

**Phase 1 covers 4 standalone master tables:**
- 🦠 `pathogen_type` — ชนิดเชื้อโรค
- 🐛 `pest_master` — แมลงศัตรูพืช
- 💊 `frac_fungicide` — ยาฆ่าเชื้อรา (FRAC)
- 💉 `irac_insecticide` — ยาฆ่าแมลง (IRAC)

Each table has full CRUD: view list, add new, edit, delete (soft-delete for tables with `is_active`).

---

## 🛠️ Installation (Pi 5 / Linux)

### 1. Install Node.js (if not already)

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo bash -
sudo apt-get install -y nodejs
node --version   # should show v22.x
```

### 2. Get the code

```bash
# copy the smartfarm-admin folder onto your Pi 5
cd ~
# (place the folder here)
cd smartfarm-admin
```

### 3. Install dependencies

```bash
npm install
```

### 4. Configure environment

```bash
cp .env.example .env
nano .env
```

Edit these values:
- `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` — your MariaDB credentials
- `SESSION_SECRET` — change to any long random string
- `ADMIN_PASSWORD_HASH` — change to your own password (see below)

### 5. Set a new admin password

The default password is `admin123`. **Change it!**

Generate a new bcrypt hash:
```bash
node -e "console.log(require('bcryptjs').hashSync('your_new_password', 10))"
```
Copy the output into `.env` as `ADMIN_PASSWORD_HASH`.

### 6. Start the server

```bash
npm start
```

Open your browser: **http://localhost:3000** (or `http://<pi-ip>:3000` from another device).

Default login (change ASAP!):
- Username: `admin`
- Password: `admin123`

---

## 🚀 Run as a systemd service (auto-start on boot)

Create the service file:

```bash
sudo nano /etc/systemd/system/smartfarm-admin.service
```

Paste:

```ini
[Unit]
Description=Smart Farm Admin Web Interface
After=network.target mariadb.service

[Service]
Type=simple
User=ekapop
WorkingDirectory=/home/ekapop/smartfarm-admin
ExecStart=/usr/bin/node app.js
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable smartfarm-admin
sudo systemctl start smartfarm-admin
sudo systemctl status smartfarm-admin
```

Check logs:
```bash
journalctl -u smartfarm-admin -f
```

---

## 📁 Project Structure

```
smartfarm-admin/
├── app.js                 — main Express entry point
├── db.js                  — MariaDB connection pool
├── config/
│   └── tables.js          — schema config for all 4 master tables
├── middleware/
│   └── requireAuth.js     — login-required guard
├── routes/
│   ├── auth.js            — login / logout
│   └── master.js          — generic CRUD for all master tables
├── views/
│   ├── partials/          — shared head, navbar, foot
│   ├── login.ejs
│   ├── dashboard.ejs
│   ├── error.ejs
│   └── master/
│       ├── list.ejs       — generic list page
│       └── form.ejs       — generic add/edit form
├── public/
│   └── css/style.css      — farm-themed Bootstrap overrides
├── .env.example
├── .gitignore
├── package.json
└── README.md
```

---

## ➕ Adding a New Master Table

To add another master table (e.g. `irrigation_zone`):

1. Open `config/tables.js`
2. Add a new entry following the pattern of `pathogen_type`
3. Restart the server
4. New table will appear in the navbar and dashboard automatically

No code changes needed in routes or views — the generic CRUD handles it. 🎯

---

## 🔒 Security Notes

- **Always change the default password.**
- The admin login is single-user from `.env`. For multi-user, add a `users` table.
- Run behind a reverse proxy (nginx) with HTTPS if exposing beyond your LAN.
- Sessions expire after 8 hours by default (see `app.js`).

---

## 🌾 What's Next (Future Phases)

- **Phase 2**: mapping tables (`disease_fungicide_map`, `pest_insecticide_map`)
- **Phase 3**: transaction tables (`t_chemical_application` spray log)
- **Phase 4**: read-only dashboards (sensor data, irrigation history)
- **Phase 5**: LINE notification integration

---

Built for the Smart Orchard System (durian, guava, wax apple) 🌳
