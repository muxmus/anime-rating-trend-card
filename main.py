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

class NotYetAired(Exception):
    """动画尚未开播异常"""
    pass

# -------------------- 数据获取与处理 --------------------
def get_anime_data(anime_id: int) -> dict:
    url = f"https://api.netaba.re/subject/{anime_id}"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()

def parse_and_filter(data: dict) -> dict:
    subject = data["subject"]
    name_cn = subject["name_cn"] or subject["name"]
    air_date_utc = datetime.fromisoformat(subject["air_date"].replace("Z", "+00:00"))
    air_date_bjt = air_date_utc.astimezone(BJT)

    # 1. 检查是否未开播：获取所有 history 中最晚的 recordedAt
    history = data["history"]
    max_recorded_bjt = None
    for item in history:
        if "recordedAt" not in item:
            continue
        dt_utc = datetime.fromisoformat(item["recordedAt"].replace("Z", "+00:00"))
        dt_bjt = dt_utc.astimezone(BJT)
        if max_recorded_bjt is None or dt_bjt > max_recorded_bjt:
            max_recorded_bjt = dt_bjt

    # 若没有任何 history 记录，或开播日期晚于最新的记录时间，视为未开播
    if max_recorded_bjt is None or air_date_bjt > max_recorded_bjt:
        raise NotYetAired("动画尚未开播，无有效评分记录")

    # 构建评分序列（仅保留开播之后的记录）
    scores = []
    for item in history:
        if "score" not in item:
            continue
        dt_utc = datetime.fromisoformat(item["recordedAt"].replace("Z", "+00:00"))
        dt_bjt = dt_utc.astimezone(BJT)
        if dt_bjt.date() >= air_date_bjt.date():
            scores.append({"date": dt_bjt, "score": item["score"]})

    # 剧集信息
    eps = []
    for item in subject["eps"]:
        if item.get("type") != 0:
            continue
        if not item.get("airdate"):
            continue
        dt_utc = datetime.fromisoformat(item["airdate"].replace("Z", "+00:00"))
        dt_bjt = dt_utc.astimezone(BJT)
        ep_name_cn = item.get("name_cn", "")
        ep_name = item.get("name", "")
        ep_display_name = ep_name_cn or ep_name
        eps.append({
            "sort": item["sort"],
            "name": ep_name,
            "name_cn": ep_display_name,
            "airdate": dt_bjt
        })

    total_users = subject["rating"]["total"]
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

# -------------------- 坐标轴刻度辅助 --------------------
def nice_step(rough: float) -> float:
    """返回一个 >=0.1 且为 0.1 整数倍的美观步长"""
    if rough <= 0.1:
        return 0.1
    factor = 10 ** math.floor(math.log10(rough))
    normalized = rough / factor
    for candidate in [1, 2, 5, 10]:
        if candidate >= normalized:
            step = candidate * factor
            return max(0.1, step)
    return 10 * factor

# -------------------- SVG 生成 --------------------
def generate_svg(cooked: dict, show_eps_and_title: bool = True) -> str:
    WIDTH, HEIGHT = 1200, 630
    PAD_L, PAD_R, PAD_T, PAD_B = 100, 50, 50, 80
    COMPRESS_RATIO = 0.12

    plot_w = WIDTH - PAD_L - PAD_R
    normal_w = plot_w * (1 - COMPRESS_RATIO)
    compress_w = plot_w * COMPRESS_RATIO

    # 根据是否包含剧集信息选择不同的横轴计算方式
    if not show_eps_and_title:
        # 所有评分都在最后一集之后：仅使用评分时间范围
        score_dates = [s["date"] for s in cooked["scores"]]
        first_date = min(score_dates)
        normal_end_date = max(score_dates)
        is_finished = False   # 不加 "now" 标签，直接显示最后日期
        # 不使用压缩区域，整个横轴线性映射
        normal_w = plot_w
        compress_w = 0
        eps_sorted = []       # 无剧集信息
    else:
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
        # 正常区域宽度已算，保持不变
        normal_w = plot_w * (1 - COMPRESS_RATIO)
        compress_w = plot_w * COMPRESS_RATIO

    span_normal = max(1, (normal_end_date - first_date).days)

    if is_finished and show_eps_and_title:
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
        elif is_finished and show_eps_and_title:
            days_past = max(0, (d - compress_start).days)
            ratio = math.sqrt(days_past / span_compress)
            return PAD_L + normal_w + ratio * compress_w
        else:
            return PAD_L + normal_w

    scores = [s["score"] for s in cooked["scores"]]
    min_s, max_s = min(scores), max(scores)
    score_range = max_s - min_s

    step = nice_step(score_range / 4.0) if score_range > 0 else 0.1
    y_min = max(0.0, step * (math.floor(min_s / step) - 1))
    y_max = step * (math.ceil(max_s / step) + 1)
    if y_max <= y_min + step:
        y_max = y_min + step

    plot_h = HEIGHT - PAD_T - PAD_B

    def y_pos(s):
        ratio = (s - y_min) / (y_max - y_min) if y_max > y_min else 0.5
        return HEIGHT - PAD_B - ratio * plot_h

    dwg = svgwrite.Drawing(size=(WIDTH, HEIGHT))
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

    # 网格线与Y轴标签
    y_val = y_min
    while y_val <= y_max + 1e-9:
        y = y_pos(y_val)
        dwg.add(dwg.line((PAD_L, y), (WIDTH - PAD_R, y), class_="grid"))
        dwg.add(dwg.text(f"{y_val:.1f}", insert=(PAD_L - 10, y + 5), class_="y-label", text_anchor="end"))
        y_val += step

    dwg.add(dwg.line((PAD_L, HEIGHT - PAD_B), (WIDTH - PAD_R, HEIGHT - PAD_B), class_="axis"))

    # 剧集信息（仅当显示时）
    if show_eps_and_title:
        # 合并同一天播出的集数
        merged_eps = []
        i = 0
        while i < len(eps_sorted):
            ep = eps_sorted[i]
            airdate = ep["airdate"]
            same_day = [ep]
            j = i + 1
            while j < len(eps_sorted) and eps_sorted[j]["airdate"].date() == airdate.date():
                same_day.append(eps_sorted[j])
                j += 1
            first_ep = same_day[0]
            last_ep = same_day[-1]
            sort_min = first_ep["sort"]
            sort_max = last_ep["sort"]
            name_cn = first_ep["name_cn"]
            if len(same_day) == 1:
                label = f"EP{sort_min} {name_cn}" if name_cn else f"EP{sort_min}"
            else:
                label = f"EP{sort_min}-{sort_max} {name_cn} 等" if name_cn else f"EP{sort_min}-{sort_max}"
            merged_eps.append({"airdate": airdate, "label": label})
            i = j

        ep_dates = {ep["airdate"].date() for ep in merged_eps}
    else:
        merged_eps = []
        ep_dates = set()

    # 横轴刻度与日期（根据 show_eps_and_title 切换绘制方式）
    if show_eps_and_title:
        day = first_date
        while day <= normal_end_date:
            x = x_pos(day)
            dwg.add(dwg.line((x, HEIGHT - PAD_B - 4), (x, HEIGHT - PAD_B + 4), class_="axis"))
            if day.date() == first_date.date() or day.date() == normal_end_date.date() or day.date() in ep_dates:
                # 首个日期加上年份（如 25.1.20）
                if day.date() == first_date.date():
                    date_str = f"{day.year % 100}.{day.month}.{day.day}"
                else:
                    date_str = f"{day.month}.{day.day}"
                dwg.add(dwg.text(date_str, insert=(x, HEIGHT - PAD_B + 18), class_="date-label", text_anchor="middle"))
            day += timedelta(days=7)

        if is_finished:
            x_end = x_pos(latest_record)
            dwg.add(dwg.line((x_end, HEIGHT - PAD_B - 4), (x_end, HEIGHT - PAD_B + 4), class_="axis"))
            dwg.add(dwg.text("now", insert=(x_end, HEIGHT - PAD_B + 18), class_="date-label", text_anchor="middle"))
    else:
        # 仅显示最早评分记录和当前时间（now）
        x_start = x_pos(first_date)
        dwg.add(dwg.line((x_start, HEIGHT - PAD_B - 4), (x_start, HEIGHT - PAD_B + 4), class_="axis"))
        # 首个日期带年份
        start_date_str = f"{first_date.year % 100}.{first_date.month}.{first_date.day}"
        dwg.add(dwg.text(start_date_str, insert=(x_start, HEIGHT - PAD_B + 18), class_="date-label", text_anchor="middle"))

        x_end = x_pos(normal_end_date)
        dwg.add(dwg.line((x_end, HEIGHT - PAD_B - 4), (x_end, HEIGHT - PAD_B + 4), class_="axis"))
        dwg.add(dwg.text("now", insert=(x_end, HEIGHT - PAD_B + 18), class_="date-label", text_anchor="middle"))

    # 剧集小标题（仅当显示剧集时绘制）
    if show_eps_and_title:
        for ep in merged_eps:
            if ep["airdate"] < first_date or ep["airdate"] > max_date:
                continue
            x = x_pos(ep["airdate"])
            anchor_x = x + 16
            anchor_y = HEIGHT - PAD_B - 12
            dwg.add(dwg.text(
                ep["label"],
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

    # 动画总标题（始终显示）
    dwg.add(dwg.text(cooked["name_cn"], insert=(PAD_L, 44), class_="title"))

    # 最新评分与评价人数（始终显示）
    latest_score = round(cooked["scores"][-1]["score"], 1)
    total_users = cooked["total_users"]
    user_text = f"{total_users}人评价"
    digit_chars = len(str(total_users))
    user_est_width = digit_chars * 9 + 3 * 18
    score_x = WIDTH - PAD_R - user_est_width - 20
    dwg.add(dwg.text(f"{latest_score:.1f}",
                     insert=(score_x, 44),
                     class_="score-text",
                     text_anchor="end"))
    dwg.add(dwg.text(user_text,
                     insert=(WIDTH - PAD_R, 44),
                     class_="user-text",
                     text_anchor="end"))

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

    # 2. 检查最早评分是否晚于最后一集
    scores_sorted = sorted(cooked["scores"], key=lambda x: x["date"])
    eps_sorted = sorted(cooked["eps"], key=lambda e: e["airdate"])
    show_eps_and_title = True
    if eps_sorted and scores_sorted:
        last_ep_date = eps_sorted[-1]["airdate"]
        first_score_date = scores_sorted[0]["date"]
        if first_score_date > last_ep_date:
            show_eps_and_title = False

    svg_str = generate_svg(cooked, show_eps_and_title=show_eps_and_title)

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

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", 5700), AnimeCardHandler)
    print("动漫评分卡片服务已启动: http://0.0.0.0:5700/{anime_id}")
    print("默认 SVG，添加 ?type=jpg 获取 JPEG")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
        print("服务已停止")
