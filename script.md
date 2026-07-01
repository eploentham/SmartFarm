mariadb-dump.exe -u ekapop -h 100.74.144.57 -p  --ssl=0 --default-character-set=utf8mb4 --routines  smartfarm > e:\backup\smartfarm20260609-2.sql


select device_id ,hot_time,cpu_temp_c,pi_cpu_pct,process_name,command from v_pi_hot_with_processes where cpu_temp_c > 90;