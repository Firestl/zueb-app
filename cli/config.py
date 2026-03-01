from pathlib import Path

LOGIN_BASE_URL = "https://cas.zueb.edu.cn/token/"
PERSONAL_BASE_URL = "https://authx-service.zueb.edu.cn/personal/"
WEBHR_BASE_URL = "https://rsxt1.zueb.edu.cn/webhr/"
JWXT_BASE_URL = "https://jwxt.zueb.edu.cn"
CAS_LOGIN_URL = "https://cas.zueb.edu.cn/cas/login"
APP_ID = "com.supwisdom.zueb"

DEFAULT_HEADERS = {
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Mobile Safari/537.36"
    ),
}

CONFIG_DIR = Path.home() / ".config" / "zueb-cli"
TOKEN_FILE = CONFIG_DIR / "session.json"
DEVICE_FILE = CONFIG_DIR / "device.json"
