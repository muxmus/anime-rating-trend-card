"""曲线平滑与降采样"""
import math


def catmull_rom_to_bezier(points, tension=0.1):
    """Catmull-Rom 转 Bezier 曲线"""
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


def generate_polyline(points):
    """产生折线路径，用于点数过少时"""
    if not points:
        return ""
    d = f"M {points[0][0]:.1f},{points[0][1]:.1f} "
    for p in points[1:]:
        d += f"L {p[0]:.1f},{p[1]:.1f} "
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
    """降采样"""
    if len(points) < 3:
        return points
    kept = [points[0]]
    for p in points[1:-1]:
        last = kept[-1]
        if math.hypot(p[0] - last[0], p[1] - last[1]) >= min_pixel_dist:
            kept.append(p)
    kept.append(points[-1])
    return kept
