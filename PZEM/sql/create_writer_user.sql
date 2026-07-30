/* create_writer_user.sql
 * Run as a MariaDB admin (root):
 *   mysql --default-character-set=utf8mb4 -h <host> -u root -p smartfarm < create_writer_user.sql
 *
 * Creates the least-privilege user the logger uses: it may only SELECT the
 * pump whitelist and SELECT/INSERT the energy table. No UPDATE/DELETE/DDL.
 * Change the password before running.
 *
 * Host scope: '%' works for a logger on another machine (e.g. mini-PC .254).
 * For a logger on the DB host itself, use 'localhost' instead of '%'.
 */

CREATE USER IF NOT EXISTS 'smartfarm_writer'@'localhost' IDENTIFIED BY 'CHANGE_ME_strong';

GRANT SELECT               ON smartfarm.m_pump         TO 'smartfarm_writer'@'localhost';
GRANT SELECT, INSERT       ON smartfarm.t_pump_energy  TO 'smartfarm_writer'@'localhost';
/* enable once t_water_pressure exists:
GRANT SELECT, INSERT       ON smartfarm.t_water_pressure TO 'smartfarm_writer'@'localhost';
*/

FLUSH PRIVILEGES;
