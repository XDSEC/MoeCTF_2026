# 使用轻量且极其稳定的 Debian Slim 镜像
FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-server \
    python3 \
    python3-pip \
    python3-venv \
    sudo \
    nano \
    vim \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir --break-system-packages \
    flask \
    fastapi \
    uvicorn

RUN mkdir /var/run/sshd \
    && sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config

RUN useradd -rm -d /home/moectf -s /bin/bash -G sudo -u 1000 moectf \
    && echo 'moectf:moectf' | chpasswd

RUN echo '#!/bin/sh\n\
# 锁定并备份最基础的安全环境变量\n\
SAFE_PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"\n\
SAFE_HOME="/home/moectf"\n\
SAFE_USER="moectf"\n\
\n\
# 动态获取当前所有环境变量的名，并全部 unset 擦除\n\
for var in $(env | cut -d= -f1); do\n\
    unset "$var"\n\
done\n\
export PATH=$SAFE_PATH\n\
export HOME=$SAFE_HOME\n\
export USER=$SAFE_USER\n\
\n\
# 启动 SSH 服务\n\
exec /usr/sbin/sshd -D\n\
' > /start.sh && chmod +x /start.sh

EXPOSE 22

ENTRYPOINT ["/start.sh"]