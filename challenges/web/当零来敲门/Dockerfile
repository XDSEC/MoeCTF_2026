FROM golang:1.26-bookworm AS builder

WORKDIR /build

COPY server.go .
RUN go mod init chatroom && \
    go mod tidy && \
    go build -ldflags="-s -w" -o chatroom-server server.go

FROM debian:stable-slim

RUN echo 'deb https://mirrors.tuna.tsinghua.edu.cn/debian/ bookworm main contrib non-free non-free-firmware' > /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends python3 python3-requests && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /build/chatroom-server /app/chatroom-server
COPY index.html /app/index.html
COPY bot.py /app/bot.py
COPY entrypoint.sh /app/entrypoint.sh

RUN chmod +x /app/entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["/bin/bash", "/app/entrypoint.sh"]