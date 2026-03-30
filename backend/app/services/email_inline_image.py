"""邮件内联图：限长边 + 统一为 RGB + 高压缩 PNG（上传与发信共用逻辑）。"""
import io

from PIL import Image

from app.config import settings


def normalize_to_inline_png(data: bytes) -> bytes | None:
  """
  将任意 Pillow 可读图片转为内联用 PNG：长边不超过 INLINE_IMAGE_MAX_SIDE，
  optimize=True、compress_level=9。失败返回 None。
  """
  try:
    img = Image.open(io.BytesIO(data))
    img.load()
    if img.mode == "P":
      img = img.convert("RGBA")
    if img.mode == "RGBA":
      bg = Image.new("RGB", img.size, (255, 255, 255))
      bg.paste(img, mask=img.split()[3])
      img = bg
    elif img.mode != "RGB":
      img = img.convert("RGB")
    max_side = max(320, min(int(settings.inline_image_max_side or 1400), 8192))
    w, h = img.size
    if max(w, h) > max_side:
      try:
        resample = Image.Resampling.LANCZOS
      except AttributeError:
        resample = Image.LANCZOS  # type: ignore[attr-defined]
      img.thumbnail((max_side, max_side), resample)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True, compress_level=9)
    return buf.getvalue()
  except Exception:
    return None
