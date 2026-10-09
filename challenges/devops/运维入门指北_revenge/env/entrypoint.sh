#!/bin/bash
set -e

echo "[+] Starting LNMP Service Initialization..."

service mariadb start

mysql -u root <<EOF
CREATE USER IF NOT EXISTS 'moectf'@'%' IDENTIFIED BY 'xdsec';
CREATE DATABASE blog;
GRANT ALL PRIVILEGES ON *.* TO 'moectf'@'%';
FLUSH PRIVILEGES;
EOF

echo "[+] MariaDB initialized"

service php8.4-fpm start

service php8.4-fpm restart

rm -f /run/php/php-fpm.sock

chmod 700 /var/www/html/usr
chown -R root:root /var/www/html/usr

echo "[+] PHP-FPM configured (with flaws)."

mkdir -p /srv/blog/logs
touch /srv/blog/logs/access.log
touch /srv/blog/logs/error.log

cat << 'EOF' > /etc/nginx/sites-available/blog
server {
  listen 8080;
  server_name blog.moectf;

  root /var/www/html;
  index index.php;

  location / {
    try_files $uri $uri/ /index.php$is_args$args;
  }

  access_log /srv/blog/logs/access.log;
  error_log /srv/blog/logs/error.log;

  location ~ \.php$ {
    include fastcgi.conf;
    fastcgi_pass unix:/run/php/php-fpm.sock;
    fastcgi_index index.php;
    # fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
    include fastcgi_params;
  }
}
EOF

ln -sf /etc/nginx/sites-available/blog /etc/nginx/sites-enabled/blog
rm -f /etc/nginx/sites-enabled/default

service nginx start
echo "[+] Nginx started (with flaws)."

export FLAG="moectf{this-is-a-fake-flag}"

rm -f /entrypoint.sh

echo "[+] Environment is ready for CTF players!"
exec "$@"