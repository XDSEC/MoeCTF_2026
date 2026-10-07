"""WebSocket 连接管理。

服务端持有一组已连接的 WebSocket，并对每个客户端推送**个性化**的状态快照
（`public_state` 含 me / my_bid / my_flag），这样每个玩家看到自己的出价、
身份和 FLAG，同时不会泄露他人的信息。

广播采用显式调用（`await broadcast(...)`），在每次游戏状态变更点触发。
单个死连接 / 慢连接不会阻塞其他客户端（`asyncio.gather(return_exceptions=True)`）。
"""

import asyncio
from typing import Any, Optional

from fastapi import WebSocket


class WsManager:
    def __init__(self) -> None:
        # ws -> (identity, my_player_id)
        self._conns: dict[WebSocket, tuple[Optional[dict], Optional[str]]] = {}
        self._lock = asyncio.Lock()

    async def connect(
        self,
        ws: WebSocket,
        identity: Optional[dict],
        my_player_id: Optional[str],
        subprotocol: Optional[str] = None,
    ) -> None:
        # 反作弊握手在 ws_endpoint 已校验通过；这里回显客户端请求的子协议
        # tboi.v1.<token>（None 时不回显，等价于旧行为）。
        await ws.accept(subprotocol=subprotocol)
        async with self._lock:
            self._conns[ws] = (identity, my_player_id)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._conns.pop(ws, None)

    async def send_state(self, ws: WebSocket, game) -> None:
        identity, pid = self._conns.get(ws, (None, None))
        await ws.send_json({"type": "state", "data": game.public_state(pid, identity)})

    async def broadcast(self, game, change: str = "") -> None:
        async with self._lock:
            conns = list(self._conns.items())
        if not conns:
            return
        jobs = []
        for ws, (identity, pid) in conns:
            data = game.public_state(pid, identity)
            data["_change"] = change
            jobs.append(self._safe_send(ws, {"type": "state", "data": data}))
        await asyncio.gather(*jobs, return_exceptions=True)

    async def _safe_send(self, ws: WebSocket, message: dict[str, Any]) -> None:
        try:
            await ws.send_json(message)
        except Exception:
            await self.disconnect(ws)
