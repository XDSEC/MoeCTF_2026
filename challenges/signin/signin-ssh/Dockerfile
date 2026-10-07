FROM debian:stable-slim

ENV DEBIAN_FRONTEND=noninteractive

# 1. 安装 openssh-server, sudo 和基础工具
RUN apt-get update && apt-get install -y \
    openssh-server \
    && rm -rf /var/lib/apt/lists/*

# 2. 创建 sshd 运行时需要的目录
RUN mkdir /var/run/sshd -p

# 3. 创建 moeops 用户，设置密码为 foo，并赋予 sudo 权限
RUN useradd -m -s /bin/bash moeops && \
    echo 'moeops:foo' | chpasswd && \
    adduser moeops sudo

# 4. 配置 SSH
RUN sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config

# 5. 复制启动脚本并赋予执行权限
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 22

# 使用 entrypoint.sh 作为入口
ENTRYPOINT ["/entrypoint.sh"]

# 默认执行的命令（会作为参数传给 entrypoint.sh 里的 "$@"）
CMD ["/usr/sbin/sshd", "-D"]