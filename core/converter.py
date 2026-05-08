"""SVG 到 JPG 格式转换"""
import io


def svg_to_jpg(svg_str: str, quality: int = 90) -> bytes:
    try:
        import cairosvg
        from PIL import Image
    except ImportError as e:
        raise RuntimeError("请安装 cairosvg 和 Pillow") from e

    png_bytes = cairosvg.svg2png(bytestring=svg_str.encode('utf-8'))
    img = Image.open(io.BytesIO(png_bytes)).convert('RGB')
    jpg_buffer = io.BytesIO()
    img.save(jpg_buffer, format='JPEG', quality=quality)
    return jpg_buffer.getvalue()
