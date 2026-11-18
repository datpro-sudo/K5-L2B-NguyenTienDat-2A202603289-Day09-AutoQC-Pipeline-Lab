"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict

import yaml

from ..common import ERROR, parse_yolo_line


def fix(ds, issues, cfg):
    remove_codes = {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}
    drop_codes = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
    removals = {}
    needs_label = set()
    line_codes = defaultdict(lambda: defaultdict(set))
    rename_classes = False

    for issue in issues:
        if issue.severity != ERROR:
            continue
        if issue.code.startswith("DUP_IMAGE_") or issue.code in remove_codes:
            removals.setdefault(issue.image, issue)
        elif issue.code == "MISSING_LABEL_FILE":
            needs_label.add(issue.image)
        elif issue.code == "BAD_CLASS_NAME":
            rename_classes = True
        elif issue.code in drop_codes | {"BOX_OUT_OF_IMAGE"} and issue.line is not None:
            line_codes[issue.image][issue.line].add(issue.code)

    fixes = []
    removed = set()
    for stem in sorted(removals):
        image_path = ds.image_path(stem)
        label_path = ds.label_path(stem)
        if image_path is None and not label_path.exists():
            continue
        before = image_path.name if image_path is not None else "(không có ảnh)"
        if image_path is not None:
            image_path.unlink()
        label_path.unlink(missing_ok=True)
        fixes.append({
            "image": stem,
            "line": None,
            "action": "remove_image",
            "before": before,
            "after": "đã xoá ảnh và nhãn khỏi dataset làm việc",
        })
        removed.add(stem)

    for stem in sorted(needs_label - removed):
        if ds.image_path(stem) is not None and not ds.label_path(stem).exists():
            fixes.append({
                "image": stem,
                "line": None,
                "action": "needs_label",
                "before": "(không có file)",
                "after": "chuyển người gán",
            })

    if rename_classes:
        yaml_path = ds.yaml_path
        original_text = yaml_path.read_text(encoding="utf-8") if yaml_path.exists() else ""
        current = yaml.safe_load(original_text) or {}
        if not isinstance(current, dict):
            current = {}
        before_names = current.get("names", "(không có names)")
        updated = dict(current)
        updated["names"] = dict(enumerate(cfg["classes"]))
        updated_text = yaml.safe_dump(updated, allow_unicode=True, sort_keys=False)
        if updated_text != original_text:
            yaml_path.write_text(updated_text, encoding="utf-8")
            fixes.append({
                "image": "data.yaml",
                "line": None,
                "action": "rename_classes",
                "before": str(before_names),
                "after": str(cfg["classes"]),
            })

    for stem in sorted(set(line_codes) - removed):
        label_path = ds.label_path(stem)
        if not label_path.exists():
            continue
        original_text = label_path.read_text(encoding="utf-8", errors="replace")
        lines = original_text.splitlines()
        trailing_newline = original_text.endswith(("\n", "\r"))
        changes = []

        for line_no in sorted(line_codes[stem]):
            index = line_no - 1
            if index < 0 or index >= len(lines) or lines[index] is None:
                continue
            line = lines[index]
            codes = line_codes[stem][line_no]

            if codes & drop_codes:
                lines[index] = None
                changes.append({
                    "image": stem,
                    "line": line_no,
                    "action": "drop_line",
                    "before": line,
                    "after": "(đã xoá dòng)",
                })
                continue

            if "BOX_OUT_OF_IMAGE" in codes:
                cls, cx, cy, width, height = parse_yolo_line(line)
                left, top = cx - width / 2, cy - height / 2
                right, bottom = cx + width / 2, cy + height / 2
                clipped_left, clipped_top = max(0.0, left), max(0.0, top)
                clipped_right, clipped_bottom = min(1.0, right), min(1.0, bottom)

                if clipped_right <= clipped_left or clipped_bottom <= clipped_top:
                    lines[index] = None
                    changes.append({
                        "image": stem,
                        "line": line_no,
                        "action": "drop_line",
                        "before": line,
                        "after": "(box nằm ngoài ảnh, đã xoá dòng)",
                    })
                else:
                    new_width = clipped_right - clipped_left
                    new_height = clipped_bottom - clipped_top
                    new_cx = (clipped_left + clipped_right) / 2
                    new_cy = (clipped_top + clipped_bottom) / 2
                    after = " ".join((
                        str(cls),
                        f"{new_cx:.12g}",
                        f"{new_cy:.12g}",
                        f"{new_width:.12g}",
                        f"{new_height:.12g}",
                    ))
                    if after != line:
                        lines[index] = after
                        changes.append({
                            "image": stem,
                            "line": line_no,
                            "action": "clip_box",
                            "before": line,
                            "after": after,
                        })

        if changes:
            remaining = [line for line in lines if line is not None]
            updated_text = "\n".join(remaining)
            if trailing_newline and remaining:
                updated_text += "\n"
            label_path.write_text(updated_text, encoding="utf-8")
            fixes.extend(changes)

    return fixes
