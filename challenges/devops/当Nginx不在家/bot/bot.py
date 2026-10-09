import os
import time
import random
import requests

# 1. 强行获取平台注入的真实 FLAG
flag = os.environ.get("FLAG")
if not flag:
    # 兜底保护，防止平台注入延迟导致变量为空
    flag = "flag{test_empty_env_error}"

flag_len = len(flag)

# 2. 随机生成 3 个不重复的切分点，确保切片能够切成 4 段
# 范围在 1 到 flag_len-1 之间，sorted 保证顺序
cut_points = sorted(random.sample(range(1, flag_len), 3))

# 按顺序切成 4 片
fragments = [
    flag[:cut_points[0]],
    flag[cut_points[0]:cut_points[1]],
    flag[cut_points[1]:cut_points[2]],
    flag[cut_points[2]:]
]

url = "http://127.0.0.1:3000/flag"
headers = {"Content-Type": "application/json"}

# 延迟 5 秒等待选手容器网络及初始化就绪
time.sleep(5)

# 3. 开始无限循环按顺序发送 4 个碎片
while True:
    for frag in fragments:
        try:
            # 依次发送每个碎片，每次间隔 10 秒
            requests.post(url, json={"ch": frag}, headers=headers, timeout=5)
            time.sleep(3)
        except Exception:
            # 如果选手服务未开启或异常，忽略错误，等 10 秒后尝试发送下一个碎片
            # 保证机器人挂起不崩溃
            time.sleep(10)