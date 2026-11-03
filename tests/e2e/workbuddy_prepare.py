"""准备真实 WorkBuddy 验收工程；不启动服务、不建模、不改原始资料。"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from gongke_app.project import Project


def prepare(study: Path, output: Path):
    study, output = study.resolve(), output.resolve()
    dimensions = study / "dimensions.json"
    source = json.loads(dimensions.read_text(encoding="utf-8"))
    drawing = Path(source["source_path"])
    # 复制整个原文件，不重写来源、尺寸、假设或验收阈值。
    inputs = {
        "dimensions.json": dimensions,
        "cases.json": ROOT / "tests/fixtures/model_inspection/cases.json",
        "drawing" + drawing.suffix.lower(): drawing,
    }
    for path in inputs.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    output.mkdir(parents=True, exist_ok=False)
    project = Project.create(str(output / "project"), name="WorkBuddy P7 验收", teaching=False)
    references = project.path / "references"
    references.mkdir()
    records = []
    for name, path in inputs.items():
        target = references / name
        shutil.copyfile(path, target)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert hashlib.sha256(target.read_bytes()).hexdigest() == digest
        records.append({"source": str(path), "copy": str(target), "sha256": digest})
    result = {"project": str(project.path), "sources": records,
              "status": "prepared", "workbuddy_verified": False}
    (output / "preparation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="尚不存在的新验收目录")
    args = parser.parse_args()
    print(json.dumps(prepare(args.study, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
