
FROM debian:stable-slim

RUN echo 'deb https://mirrors.tuna.tsinghua.edu.cn/debian/ bookworm main contrib non-free non-free-firmware' > /etc/apt/sources.list && \
    echo 'deb https://mirrors.tuna.tsinghua.edu.cn/debian/ bookworm-updates main contrib non-free non-free-firmware' >> /etc/apt/sources.list && \
    echo 'deb https://mirrors.tuna.tsinghua.edu.cn/debian/ bookworm-backports main contrib non-free non-free-firmware' >> /etc/apt/sources.list && \
    echo 'deb https://mirrors.tuna.tsinghua.edu.cn/debian-security bookworm-security main contrib non-free non-free-firmware' >> /etc/apt/sources.list

RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    openssh-server sudo curl procps netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /var/run/sshd && \
    sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config

RUN useradd -m -s /bin/bash moectf && \
    echo 'moectf:devops' | chpasswd && \
    echo 'moectf ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers

RUN echo 'export FLAG=""' >> /etc/profile && \
    echo 'export FLAG=""' >> /home/moectf/.bashrc

EXPOSE 22

CMD ["/usr/sbin/sshd", "-D"]