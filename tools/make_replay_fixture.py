"""场景回放测试的 fixture 生成工具：对一串截图（一般是流程追踪 dev_out/chaos_trace/<时间>/ 里的 jpg）跑一遍真 OCR 和
coco 模板匹配，把结果存成 json；测试（tests/replay.py）只读 json + 图，不再跑 OCR，可重复、快。只能在 Windows 上跑（要 onnxocr）。

    .venv\\Scripts\\python.exe tools\\make_replay_fixture.py tests\\fixtures\\replay\\equip_1802.json ^
        D:\\...\\0043_refine.jpg --features leveltag --manual "target_member_tiny@0:0.66,0.47,0.70,0.55,0.64"

- 图片复制到 json 同目录（文件名不变，已在就不复制）；json 里记相对文件名。
- 流程追踪的截图被缩到 1280 宽：OCR/模板匹配前先放大到 --width（默认 1920，和实机 1920×1080 的坐标一致），
  框坐标都按放大后的像素存。回放时图也按同样尺寸放大，颜色取点用相对坐标，缩放影响很小（JPEG 压缩会让颜色差几个点）。
- --features：要预先匹配的 coco 特征（ok_tasks/assets/coco_annotations.json 里的名字），整帧找，阈值 --threshold。
- --manual：运行时才生成的特征（刷存档主战员头像 target_member_* 等）没法离线匹配，按流程追踪日志手填：
  「名字@帧号:x1,y1,x2,y2,置信度」，坐标是相对坐标；帧号可写 * 表示所有帧。
"""
import argparse
import json
import os
import shutil
import sys

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "ok_tasks", "assets")


def _ocr_engine():
    from onnxocr.onnx_paddleocr import ONNXPaddleOcr
    return ONNXPaddleOcr(use_angle_cls=False, use_npu=False, use_openvino=False)


def run_ocr(engine, image, threshold=0.2):
    """和 ok 框架 OCR.onnx_ocr 一样取框：左上角 + 宽高（第 0、2 个角点），置信度低于 threshold 的丢掉。"""
    result = engine.ocr(image)
    boxes = []
    for pos, (text, conf) in (result[0] or []):
        w, h = round(pos[2][0] - pos[0][0]), round(pos[2][1] - pos[0][1])
        if w <= 0 or h <= 0 or conf < threshold:
            continue
        boxes.append([round(float(pos[0][0])), round(float(pos[0][1])), w, h, round(float(conf), 4), text])
    return boxes


def _coco_templates(names):
    with open(os.path.join(ASSETS, "coco_annotations.json"), encoding="utf-8") as f:
        coco = json.load(f)
    cats = {c["id"]: c["name"] for c in coco["categories"]}
    images = {i["id"]: i for i in coco["images"]}
    out = {}
    for a in coco["annotations"]:
        name = cats[a["category_id"]]
        if name not in names or name in out:
            continue
        img = images[a["image_id"]]
        src = cv2.imread(os.path.join(ASSETS, img["file_name"]))
        x, y, w, h = (int(round(v)) for v in a["bbox"])
        out[name] = (src[y:y + h, x:x + w], img["width"], img["height"])
    missing = set(names) - set(out)
    if missing:
        raise SystemExit(f"coco 里没有这些特征：{sorted(missing)}")
    return out


def match_feature(frame, template, threshold):
    """整帧模板匹配（模板按 coco 原图高度等比缩放到帧高），返回去重后的 [x, y, w, h, conf]。"""
    tpl, _ref_w, ref_h = template
    s = frame.shape[0] / ref_h
    if s != 1:
        tpl = cv2.resize(tpl, (max(1, round(tpl.shape[1] * s)), max(1, round(tpl.shape[0] * s))))
    res = cv2.matchTemplate(frame, tpl, cv2.TM_CCOEFF_NORMED)
    th, tw = tpl.shape[:2]
    found = []
    ys, xs = np.where(res >= threshold)
    for conf, x, y in sorted(((float(res[y, x]), int(x), int(y)) for y, x in zip(ys, xs)), reverse=True):
        if all(abs(x - fx) >= tw / 2 or abs(y - fy) >= th / 2 for fx, fy, *_ in found):
            found.append([x, y, tw, th, round(conf, 4)])
    return found


def _parse_manual(items, w, h):
    out = []
    for item in items or []:
        name, rest = item.split("@", 1)
        idx, coords = rest.split(":", 1)
        x1, y1, x2, y2, conf = (float(v) for v in coords.split(","))
        out.append((name, idx, [round(x1 * w), round(y1 * h), round((x2 - x1) * w), round((y2 - y1) * h), conf]))
    return out


def dump(data):
    """每个框一行，方便看 diff。"""
    def one(v):
        return json.dumps(v, ensure_ascii=False)
    lines = ["{", f' "note": {one(data["note"])},', f' "width": {data["width"]}, "height": {data["height"]},', ' "frames": [']
    for i, fr in enumerate(data["frames"]):
        lines.append(f'  {{"image": {one(fr["image"])},')
        lines.append('   "texts": [' + ",\n             ".join(one(t) for t in fr["texts"]) + "],")
        feats = ",\n                ".join(f"{one(k)}: {one(v)}" for k, v in fr["features"].items())
        lines.append('   "features": {' + feats + "}}" + ("," if i + 1 < len(data["frames"]) else ""))
    lines += [" ]", "}", ""]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", help="输出 json 路径（图片复制到同目录）")
    ap.add_argument("images", nargs="+")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--features", default="", help="逗号分隔的 coco 特征名")
    ap.add_argument("--threshold", type=float, default=0.7)
    ap.add_argument("--manual", action="append", help="手填特征：名字@帧号:x1,y1,x2,y2,置信度（相对坐标）")
    ap.add_argument("--note", default="", help="写进 json 的说明（来源、当时实录）")
    ap.add_argument("--prefix", default="", help="复制过去的图片文件名加前缀（不同追踪目录的序号会重名）")
    args = ap.parse_args(argv)

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    names = [n for n in args.features.split(",") if n]
    templates = _coco_templates(names) if names else {}
    engine = _ocr_engine()
    frames = []
    for i, path in enumerate(args.images):
        img = cv2.imread(path)
        if img is None:
            raise SystemExit(f"读不了图：{path}")
        h = round(img.shape[0] * args.width / img.shape[1])
        big = cv2.resize(img, (args.width, h), interpolation=cv2.INTER_CUBIC) if img.shape[1] != args.width else img
        img_name = args.prefix + os.path.basename(path)
        dst = os.path.join(out_dir, img_name)
        if os.path.abspath(path) != os.path.abspath(dst) and not os.path.exists(dst):
            shutil.copyfile(path, dst)
        feats = {n: match_feature(big, templates[n], args.threshold) for n in names}
        for name, idx, b in _parse_manual(args.manual, args.width, h):
            if idx == "*" or int(idx) == i:
                feats.setdefault(name, []).append(b)
        texts = run_ocr(engine, big)
        frames.append({"image": img_name, "texts": texts, "features": feats})
        print(f"{img_name}: {len(texts)} 个文字框，特征 { {k: len(v) for k, v in feats.items()} }")
    data = {"note": args.note, "width": args.width, "height": frames and h, "frames": frames}
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(dump(data))
    print(f"写入 {args.out}")


if __name__ == "__main__":
    sys.exit(main())
