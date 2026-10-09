"""
AI 模型配置
============
部署时通过环境变量覆盖。API key 严禁硬编码——默认值仅为占位符，
app.py 启动时会校验并拒绝占位值（fail-fast）。部署前务必新开专用 key。
"""
import os

# 上游模型（OpenAI 兼容协议）
MODEL = os.environ.get("AI_MODEL", "kimi-k2.6")
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "fill-your-secret-key-here")
BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://opencode.ai/zen/go/v1")

# 生成参数
TEMPERATURE = float(os.environ.get("TEMPERATURE", "0.8"))  # 部署可覆盖；红队实测口径 0.8
MAX_TOKENS = 2048
TIMEOUT_SECONDS = 30   # 单次上游调用超时；失败重试 1 次，总超时 ≤ 60s

# 反向代理信任列表（逗号分隔，默认空=不信任任何转发头）。
# 支持精确 IP 与 CIDR 网段，如 "127.0.0.1,104.16.0.0/13"（Cloudflare 边缘段）。
# 仅当部署在可信反代 / CDN / WAF 之后才设置；直接对端不在列表内时一律不信任转发头，防伪造。
TRUST_PROXY_FOR = [ip.strip() for ip in os.environ.get("TRUST_PROXY_FOR", "114.514.114.514").split(",") if ip.strip()]

# CDN/WAF 客户端真实 IP 头（按优先级尝试，仅当直接对端受信时才读取，防客户端伪造）。
# 默认只认阿里云 CDN/WAF 的 ali-real-client-ip，内容原样作为真实 IP（IPv4/IPv6 均可）；
# 头部名大小写不敏感。换用其它厂商时按需覆盖，如 Cloudflare=CF-Connecting-IP、nginx反代=X-Real-IP。
CLIENT_IP_HEADERS = [
    h.strip() for h in os.environ.get("CLIENT_IP_HEADERS", "moectf-real-client-ip").split(",") if h.strip()
]
