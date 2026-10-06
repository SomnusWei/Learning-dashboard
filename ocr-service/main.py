"""OCR HTTP 服务（基于 rapidocr-onnxruntime 1.4.3 + PP-OCRv3 模型，兼容无 AVX 的 CPU）。
方案 I：按 y 坐标切割成题干和选项两部分，分别 OCR 后合并结果。
避免题干行的"黯，唇甲"被选项百分比数字干扰而漏识。
"""
import io
import logging
import time

from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ocr")

app = FastAPI(title="OCR Service")

_ocr: RapidOCR | None = None


def get_ocr() -> RapidOCR:
    global _ocr
    if _ocr is None:
        logger.info("初始化 rapidocr-onnxruntime 1.4.3 引擎（PP-OCRv3）...")
        _ocr = RapidOCR()
        logger.info("RapidOCR 引擎初始化完成")
    return _ocr


def _ocr_image(engine: RapidOCR, img: Image.Image, label: str) -> tuple[list[str], list[dict]]:
    """对单张图片做 OCR，返回 (texts, boxes_info)。"""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    raw = buf.getvalue()

    result = engine(raw)
    texts: list[str] = []
    boxes_info: list[dict] = []
    if result and len(result) >= 1:
        lines = result[0] if isinstance(result, tuple) else result
        if lines:
            for i, line in enumerate(lines):
                if not line or len(line) < 2:
                    continue
                box = line[0]
                text_item = line[1]
                score = line[2] if len(line) >= 3 else None
                if isinstance(text_item, (list, tuple)):
                    text_str = str(text_item[0]) if len(text_item) >= 1 else ""
                else:
                    text_str = str(text_item)
                texts.append(text_str)
                boxes_info.append({
                    "idx": i, "region": label,
                    "text": text_str,
                    "score": float(score) if score is not None else None,
                    "box": box,
                })
    return texts, boxes_info


@app.get("/health")
def health():
    return {"status": "ok", "ocr_loaded": _ocr is not None}


@app.post("/ocr")
async def ocr(image: UploadFile = File(...)):
    """识别图片中的文字（方案 I：分块 OCR）。"""
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(400, "请上传图片文件")

    raw = await image.read()
    if not raw:
        raise HTTPException(400, "图片为空")

    try:
        img = Image.open(io.BytesIO(raw))
        img.verify()
        img = Image.open(io.BytesIO(raw))
        logger.info(f"输入图片: {img.size[0]}x{img.size[1]} {img.mode}, 字节数={len(raw)}")
    except Exception as e:
        raise HTTPException(400, f"无效图片: {e}")

    start = time.time()
    try:
        engine = get_ocr()
        # 方案 I：按 y=40% 切割成题干区域和选项区域，分别 OCR
        # 蓝基因 App 截图布局：
        #   - 上 40%: 科目 + 题型 + 题干文字（这里容易漏识）
        #   - 下 60%: 选项 A-E + 答案 + 统计信息
        # 分块 OCR 避免题干文字被选项百分比数字干扰
        cut_y = int(img.height * 0.40)
        top_img = img.crop((0, 0, img.width, cut_y))
        bottom_img = img.crop((0, cut_y, img.width, img.height))
        logger.info(f"切割: 上半 {top_img.size[0]}x{top_img.size[1]}, 下半 {bottom_img.size[0]}x{bottom_img.size[1]}")

        top_texts, top_boxes = _ocr_image(engine, top_img, "top")
        logger.info(f"上半 OCR: {len(top_texts)} 行")
        for info in top_boxes:
            logger.info(f"  [top-{info['idx']}] score={info['score']:.4f} text={info['text']!r}")

        bottom_texts, bottom_boxes = _ocr_image(engine, bottom_img, "bottom")
        logger.info(f"下半 OCR: {len(bottom_texts)} 行")
        for info in bottom_boxes:
            logger.info(f"  [bot-{info['idx']}] score={info['score']:.4f} text={info['text']!r}")

        texts = top_texts + bottom_texts
        boxes_info = top_boxes + bottom_boxes
    except Exception as e:
        logger.exception("OCR 识别失败")
        raise HTTPException(500, f"OCR 识别失败: {e}")

    elapsed = round(time.time() - start, 2)
    text = "\n".join(texts)
    logger.info(f"OCR 完成（分块）: 上半 {len(top_texts)} 行 + 下半 {len(bottom_texts)} 行 = {len(texts)} 行, 耗时 {elapsed}s")
    return {"text": text, "lines": texts, "elapsed": elapsed, "boxes_info": boxes_info}
