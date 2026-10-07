#!/bin/bash

# 1. 检查是否存在 FLAG 环境变量，如果存在就写入 /tmp/flag
if [ -n "$FLAG" ]; then
    echo "$FLAG" > /tmp/flag
else
    echo "moectf{default_ssh_flag_placeholder}" > /tmp/flag
fi

export FLAG="moectf{is-this-a-real-flag}"

# 2. 确保 flag 文件对 moeops 用户是只读的，防止被删改
chmod 444 /tmp/flag

# 3. 执行 Dockerfile 传进来的后续命令（即启动 SSH 服务）
exec "$@"