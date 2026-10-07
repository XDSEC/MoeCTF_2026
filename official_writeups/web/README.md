# 题解

## 当零来敲门

在本地条件下，当林林刚发完 0，用这个脚本从 1 到 500 快速发送请求即可得到 flag。

```python
import requests
for i in range(500):
    url = "http://127.0.0.1:8080/chat"
    body = {"user":'挑战者',"msg":(i+1)}
    x=requests.post(url, json=body)
```

但比赛平台和做题者之间存在网络延迟，如果等发完 0 之后手动启动脚本，没发多少就被打断了。如果是让 Python 自己重新开始呢？比如这样，也只能达到 130 左右。

```python
import requests
url = "http://127.0.0.1:8080/chat"
while True:
    for i in range(500):
        body = {"user": "挑战者", "msg": (i + 1)}
        try:
            x = requests.post(url, json=body)
            if x.json().get("status") != "success":
                break
        except Exception:
            break
```

`requsts.post()`的时间花销是比较大的，如果可以重用每次请求的握手，说不定能快一点。这段代码重用了 session，第一次达到 440，网络存在波动，多试几次就成功了。

```python
import requests

url = "http://127.0.0.1:8080/chat"

with requests.Session() as session:
    while True:
        for i in range(500):
            body = {"user": "挑战者", "msg": (i + 1)}
            try:
                x = session.post(url, json=body, timeout=0.5)
                if x.json().get("status") != "success":
                    break
            except Exception:
                break
```

但是现在校园网的环境恶化了，上面这个脚本也有点过不了了，用一用异步吧。

```python
import asyncio
import aiohttp

async def main():
    async with aiohttp.ClientSession() as s:
        for i in range(500):
            async with s.post("http://127.0.0.1:8080/chat",
                    json={"user": "挑战者", "msg": i + 1}) as resp:
                pass

asyncio.run(main())
```

后面发现异步也做不了，开了一个本地环境，这样第一版的脚本就能跑通。