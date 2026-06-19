# -*- coding: utf-8 -*-
"""
量化交易平台启动入口

使用 uvicorn 以编程方式启动 FastAPI 应用，启动后自动打开浏览器。

启动方式:
    python main.py

访问地址:
    主页:       http://localhost:8000
    API 文档:   http://localhost:8000/docs
    回测页面:   http://localhost:8000/backtest
    策略管理:   http://localhost:8000/strategy
    数据管理:   http://localhost:8000/data
    交易监控:   http://localhost:8000/monitor
"""
import threading
import webbrowser
import uvicorn
from config.settings import WEB_HOST, WEB_PORT
from web.app import app


def _open_browser():
    """延迟 1.5 秒后自动打开浏览器"""
    import time
    time.sleep(1.5)
    url = f"http://{WEB_HOST}:{WEB_PORT}"
    webbrowser.open(url)


if __name__ == "__main__":
    print(f"量化交易平台启动中...")
    print(f"  主页:       http://{WEB_HOST}:{WEB_PORT}")
    print(f"  API 文档:   http://{WEB_HOST}:{WEB_PORT}/docs")
    print("=" * 50)

    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run(app, host=WEB_HOST, port=WEB_PORT)
