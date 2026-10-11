#!/bin/bash

python3 /app/bot.py > /dev/null 2>&1 &

exec /app/chatroom-server