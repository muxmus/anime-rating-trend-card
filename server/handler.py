"""HTTP 请求处理"""
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from core.card import generate_card
from core.parser import NotYetAired


class AnimeCardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        anime_id_str = parsed.path.strip("/")
        params = parse_qs(parsed.query)

        if not anime_id_str.isdigit():
            self.send_error(400, "Invalid anime ID")
            return

        anime_id = int(anime_id_str)
        fmt = params.get("type", ["svg"])[0].lower()

        try:
            content, mime = generate_card(anime_id, fmt)
        except NotYetAired:
            self.send_error(404, "Not yet aired")
            return
        except Exception as e:
            self.send_error(500, str(e))
            return

        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        pass
