import json
import math
import io
import requests
import svgwrite
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# 北京时区 (UTC+8)
BJT = timezone(timedelta(hours=8))

# -------------------- 数据获取与处理 --------------------
def get_anime_data(anime_id: int) -> dict:
    url = f"https://api.netaba.re/subject/{anime_id}"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()

def parse_and_filter(data: dict) -> dict:
    name_cn = data["subject"]["name_cn"] or data["subject"]["name"]
    air_date_utc = datetime.fromisoformat(data["subject"]["air_date"].replace("Z", "+00:00"))
    air_date_bjt = air_date_utc.astimezone(BJT)

    history = data["history"]
    scores = []
    for item in history:
        if "score" not in item:
            continue
        dt_utc = datetime.fromisoformat(item["recordedAt"].replace("Z", "+00:00"))
        dt_bjt = dt_utc.astimezone(BJT)
        if dt_bjt.date() >= air_date_bjt.date():
            scores.append({"date": dt_bjt, "score": item["score"]})

    eps = []
    for item in data["subject"]["eps"]:
        dt_utc = datetime.fromisoformat(item["airdate"].replace("Z", "+00:00"))
        dt_bjt = dt_utc.astimezone(BJT)
        ep_name_cn = item.get("name_cn", "")
        ep_name = item.get("name", "")
        eps.append({
            "sort": item["sort"],
            "name": ep_name,
            "name_cn": ep_name_cn or ep_name,
            "airdate": dt_bjt
        })

    total_users = data["subject"]["rating"]["total"]
    return {
        "name_cn": name_cn,
        "air_date": air_date_bjt,
        "scores": scores,
        "eps": eps,
        "total_users": total_users
    }

# -------------------- 曲线平滑工具 --------------------
def catmull_rom_to_bezier(points, tension=0.2):
    if len(points) < 2:
        return ""
    size = len(points)
    d = f"M {points[0][0]:.1f},{points[0][1]:.1f} "
    for i in range(size - 1):
        p0 = points[i - 1] if i > 0 else points[0]
        p1 = points[i]
        p2 = points[i + 1]
        p3 = points[i + 2] if i < size - 2 else p2

        cp1x = p1[0] + (p2[0] - p0[0]) * tension / 6
        cp1y = p1[1] + (p2[1] - p0[1]) * tension / 6
        cp2x = p2[0] - (p3[0] - p1[0]) * tension / 6
        cp2y = p2[1] - (p3[1] - p1[1]) * tension / 6

        d += f"C {cp1x:.1f},{cp1y:.1f} {cp2x:.1f},{cp2y:.1f} {p2[0]:.1f},{p2[1]:.1f} "
    return d.strip()

def moving_average_smooth(points, window=3):
    if len(points) < window:
        return points
    smoothed = []
    half = window // 2
    for i in range(len(points)):
        start = max(0, i - half)
        end = min(len(points), i + half + 1)
        avg_y = sum(p[1] for p in points[start:end]) / (end - start)
        smoothed.append((points[i][0], avg_y))
    return smoothed

def downsample_points(points, min_pixel_dist=10.0):
    if len(points) < 3:
        return points
    kept = [points[0]]
    for p in points[1:-1]:
        last = kept[-1]
        if math.hypot(p[0] - last[0], p[1] - last[1]) >= min_pixel_dist:
            kept.append(p)
    kept.append(points[-1])
    return kept

# -------------------- SVG 生成 --------------------
def generate_svg(cooked: dict) -> str:
    WIDTH, HEIGHT = 1200, 630
    PAD_L, PAD_R, PAD_T, PAD_B = 100, 50, 50, 80
    COMPRESS_RATIO = 0.12

    plot_w = WIDTH - PAD_L - PAD_R
    normal_w = plot_w * (1 - COMPRESS_RATIO)
    compress_w = plot_w * COMPRESS_RATIO

    eps_sorted = sorted(cooked["eps"], key=lambda e: e["airdate"])
    if not eps_sorted or not cooked["scores"]:
        raise ValueError("数据不足")

    latest_record = cooked["scores"][-1]["date"]
    last_ep_airdate = eps_sorted[-1]["airdate"]
    is_finished = last_ep_airdate <= latest_record

    if is_finished:
        max_date = latest_record
        normal_end_date = last_ep_airdate
    else:
        next_ep = next((ep for ep in eps_sorted if ep["airdate"] > latest_record), None)
        if next_ep is None:
            is_finished = True
            max_date = latest_record
            normal_end_date = last_ep_airdate
        else:
            max_date = next_ep["airdate"]
            normal_end_date = next_ep["airdate"]

    first_date = cooked["air_date"]
    span_normal = max(1, (normal_end_date - first_date).days)

    if is_finished:
        compress_start = last_ep_airdate
        compress_end = latest_record
        span_compress = max(1, (compress_end - compress_start).days)
    else:
        compress_start = normal_end_date
        compress_end = normal_end_date
        span_compress = 1

    def x_pos(d):
        if d <= normal_end_date:
            ratio = max(0, (d - first_date).days / span_normal)
            return PAD_L + ratio * normal_w
        elif is_finished:
            days_past = max(0, (d - compress_start).days)
            ratio = math.sqrt(days_past / span_compress)
            return PAD_L + normal_w + ratio * compress_w
        else:
            return PAD_L + normal_w

    scores = [s["score"] for s in cooked["scores"]]
    min_s, max_s = min(scores), max(scores)
    score_range = max_s - min_s
    y_buffer = score_range * 0.1 if score_range > 0 else 0.5
    y_min = max(0, min_s - y_buffer)
    y_max = min_s + score_range + y_buffer
    plot_h = HEIGHT - PAD_T - PAD_B

    def y_pos(s):
        ratio = (s - y_min) / (y_max - y_min) if y_max > y_min else 0.5
        return HEIGHT - PAD_B - ratio * plot_h

    dwg = svgwrite.Drawing(size=(WIDTH, HEIGHT))
    # ★ 关键修复：字体栈同时包含中英文字体，用 Noto Sans CJK / 文泉驿微米黑 作为最佳选择
    dwg.embed_stylesheet("""
        .grid { stroke: #e8e8e8; stroke-width: 1; }
        .axis { stroke: #555; stroke-width: 2; }
        .curve { fill: none; stroke: #4A90D9; stroke-width: 3; }
        .title { font-family: 'Noto Sans CJK SC', 'WenQuanYi Micro Hei', 'DejaVu Sans', Arial, sans-serif; font-size: 30px; font-weight: bold; fill: #333; }
        .score-text { font-family: 'Noto Sans CJK SC', 'WenQuanYi Micro Hei', 'DejaVu Sans', Arial, sans-serif; font-size: 38px; font-weight: bold; fill: #4A90D9; }
        .user-text { font-family: 'Noto Sans CJK SC', 'WenQuanYi Micro Hei', 'DejaVu Sans', Arial, sans-serif; font-size: 18px; font-weight: 600; fill: #666; }
        .ep-label { 
            font-family: 'Noto Sans CJK SC', 'WenQuanYi Micro Hei', 'DejaVu Sans', Arial, sans-serif; font-size: 14px; font-weight: bold; fill: #555; opacity: 0.5; 
            text-anchor: start;
        }
        .date-label { font-family: 'Noto Sans CJK SC', 'WenQuanYi Micro Hei', 'DejaVu Sans', Arial, sans-serif; font-size: 13px; font-weight: bold; fill: #999; }
        .y-label { font-family: 'Noto Sans CJK SC', 'WenQuanYi Micro Hei', 'DejaVu Sans', Arial, sans-serif; font-size: 14px; font-weight: bold; fill: #999; }
    """)
    dwg.add(dwg.rect(insert=(0, 0), size=(WIDTH, HEIGHT), fill="#fafafa"))

    # 网格线
    for i in range(6):
        y_val = y_min + (y_max - y_min) * i / 5
        y = y_pos(y_val)
        dwg.add(dwg.line((PAD_L, y), (WIDTH - PAD_R, y), class_="grid"))
        dwg.add(dwg.text(f"{y_val:.1f}", insert=(PAD_L - 10, y + 5), class_="y-label", text_anchor="end"))

    dwg.add(dwg.line((PAD_L, HEIGHT - PAD_B), (WIDTH - PAD_R, HEIGHT - PAD_B), class_="axis"))

    # 横轴日期标注
    day = first_date
    while day <= normal_end_date:
        x = x_pos(day)
        dwg.add(dwg.line((x, HEIGHT - PAD_B - 4), (x, HEIGHT - PAD_B + 4), class_="axis"))
        dwg.add(dwg.text(day.strftime("%m-%d"), insert=(x, HEIGHT - PAD_B + 18), class_="date-label", text_anchor="middle"))
        day += timedelta(days=7)

    if is_finished:
        x_end = x_pos(latest_record)
        dwg.add(dwg.line((x_end, HEIGHT - PAD_B - 4), (x_end, HEIGHT - PAD_B + 4), class_="axis"))
        dwg.add(dwg.text(latest_record.strftime("%m-%d"), insert=(x_end, HEIGHT - PAD_B + 18), class_="date-label", text_anchor="middle"))

    # 剧集标题
    for ep in eps_sorted:
        if ep["airdate"] < first_date or ep["airdate"] > max_date:
            continue
        x = x_pos(ep["airdate"])
        label = f"EP{ep['sort']} {ep['name_cn']}"
        anchor_x = x + 16
        anchor_y = HEIGHT - PAD_B - 12
        dwg.add(dwg.text(
            label,
            insert=(anchor_x, anchor_y),
            transform=f"rotate(-90, {anchor_x}, {anchor_y})",
            class_="ep-label"
        ))

    # 平滑曲线
    raw_points = [(x_pos(s["date"]), y_pos(s["score"])) for s in cooked["scores"]]
    sparse = downsample_points(raw_points, min_pixel_dist=10.0)
    smoothed = moving_average_smooth(sparse, window=3)
    if len(smoothed) >= 2:
        path_d = catmull_rom_to_bezier(smoothed, tension=0.2)
        dwg.add(dwg.path(d=path_d, class_="curve"))

    # 标题与评分
    dwg.add(dwg.text(cooked["name_cn"], insert=(PAD_L, 44), class_="title"))
    latest_score = round(cooked["scores"][-1]["score"], 1)
    dwg.add(dwg.text(f"{latest_score:.1f}",
                     insert=(WIDTH - PAD_R - 110, 44), class_="score-text", text_anchor="end"))
    dwg.add(dwg.text(f"{cooked['total_users']}人评价",
                     insert=(WIDTH - PAD_R, 44), class_="user-text", text_anchor="end"))

    return dwg.tostring()

def svg_to_jpg(svg_str: str, quality: int = 90) -> bytes:
    """将 SVG 字符串转换为 JPEG 字节流（惰性导入依赖）。"""
    try:
        import cairosvg
        from PIL import Image
    except ImportError as e:
        raise RuntimeError("请安装 cairosvg 和 Pillow：pip install cairosvg Pillow") from e

    png_bytes = cairosvg.svg2png(bytestring=svg_str.encode('utf-8'))
    img = Image.open(io.BytesIO(png_bytes)).convert('RGB')
    jpg_buffer = io.BytesIO()
    img.save(jpg_buffer, format='JPEG', quality=quality)
    return jpg_buffer.getvalue()

def generate_card(anime_id: int, fmt: str = "svg") -> tuple[bytes, str]:
    raw = get_anime_data(anime_id)
    cooked = parse_and_filter(raw)
    svg_str = generate_svg(cooked)

    if fmt == "jpg":
        try:
            jpg_bytes = svg_to_jpg(svg_str)
            return jpg_bytes, "image/jpeg"
        except Exception:
            pass
    return svg_str.encode("utf-8"), "image/svg+xml"

# -------------------- HTTP 服务器 --------------------
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

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 5700), AnimeCardHandler)
    print("动漫评分卡片服务已启动: http://0.0.0.0:5700/{anime_id}")
    print("默认 SVG，添加 ?type=jpg 获取 JPEG")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
        print("服务已停止")
