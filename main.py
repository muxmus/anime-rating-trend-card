"""动漫评分卡片生成服务 —— 主入口"""
from http.server import HTTPServer
from server.handler import AnimeCardHandler

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 5700), AnimeCardHandler)
    print("动漫评分卡片服务已启动: http://0.0.0.0:5700/{anime_id}")
    print("默认 SVG，添加 ?type=jpg 获取 JPEG")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
        print("服务已停止")
