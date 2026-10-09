FROM debian:stable-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    openssh-server nginx php8.4-fpm php8.4-mysql mariadb-server \
    wget unzip sudo nano python3 curl \
    php8.4-mbstring php8.4-xml php8.4-curl \
    && rm -rf /var/lib/apt/lists/*

RUN wget https://raw.githubusercontent.com/gdraheim/docker-systemctl-replacement/master/files/docker/systemctl3.py -O /usr/bin/systemctl && \
    chmod +x /usr/bin/systemctl

RUN mkdir -p /var/www/html && \
    wget https://github.com/typecho/typecho/releases/latest/download/typecho.zip -O /tmp/typecho.zip && \
    unzip /tmp/typecho.zip -d /var/www/html/ && \
    rm /tmp/typecho.zip && \
    chown -R www-data:www-data /var/www/html

RUN mkdir /var/run/sshd -p && \
    useradd -m -s /bin/bash moeops && \
    echo 'moeops:foo' | chpasswd && \
    adduser moeops sudo

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 22 3306 8080
ENTRYPOINT ["/entrypoint.sh"]
CMD ["/usr/sbin/sshd", "-D"]