"""Run the frozen service after copying it outside the source checkout."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
from uuid import uuid4
import zipfile


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--service-dir", type=Path, default=root / "desktop/service/gongke-service")
    parser.add_argument("--evidence", type=Path, default=root / "out" / ("service-clean-room-" + uuid4().hex[:8]))
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="gongke-installed-") as temp:
        installed = Path(temp)
        shutil.copytree(args.service_dir, installed / "service", symlinks=True)
        binary = installed / "service" / ("gongke-service.exe" if os.name == "nt" else "gongke-service")
        env = {key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "GONGKE_DATA"}}
        env["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32") if os.name == "nt" else "/usr/bin:/bin"
        process = subprocess.Popen([str(binary), "--state-dir", str(installed / "state")], cwd=installed,
                                   env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        timer = threading.Timer(180, process.kill)
        timer.start()
        rows, result = [], None
        try:
            requests = [
                {"id": 1, "method": "system.status"},
                {"id": 2, "method": "project.create", "params": {"path": str(installed / "project"), "teaching": True}},
                {"id": 3, "method": "design.calculate"},
                {"id": 4, "method": "design.generate", "params": {"name": "verified", "step": True, "drawings": True, "report_docx": True}},
            ]
            process.stdin.write("".join(json.dumps(row) + "\n" for row in requests))
            process.stdin.flush()
            for line in process.stdout:
                row = json.loads(line)
                rows.append(row)
                if "error" in row:
                    raise RuntimeError(row["error"])
                if row.get("event") == "task.updated" and row["task"]["status"] not in {"queued", "running"}:
                    result = row["task"]
                    break
            process.stdin.close()
            process.wait(timeout=15)
            if process.returncode != 0 or result is None:
                raise RuntimeError("Frozen service failed: " + process.stderr.read())
            # Preserve failed artifacts and the exact protocol as well as successes.
            shutil.copytree(installed / "project", args.evidence / "project")
            (args.evidence / "protocol.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
            (args.evidence / "task.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            assert rows[0]["result"]["packaged"] is True
            assert result["status"] == "complete", result
            generated = result["result"]
            assert generated["exports_complete"] is True, generated
            output = installed / "project/revisions/verified"
            assert (output / "reducer_assembly.step").read_bytes().startswith(b"ISO-10303-21;")
            assert (output / "drawings/drawings.pdf").read_bytes().startswith(b"%PDF-")
            with zipfile.ZipFile(output / "report.docx") as archive:
                assert archive.testzip() is None and "word/document.xml" in archive.namelist()
            index = json.loads((output / "drawings/index.json").read_text())
            assert len(index) == 9
            assert all((output / "drawings" / sheet["dxf"]).is_file() and
                       (output / "drawings" / sheet["svg"]).is_file() for sheet in index)
            report = {"packaged": True, "outside_source_directory": True, "user_python_unavailable_on_path": True,
                      "task_status": result["status"], "calculation_ok": generated["calculation_ok"],
                      "exports_complete": generated["exports_complete"], "drawing_count": len(index),
                      "drawing_check": generated["drawing_check"], "formats": ["STEP", "DXF", "SVG", "PDF", "DOCX", "Markdown"],
                      "project": str((args.evidence / "project").resolve())}
            (args.evidence / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(report, ensure_ascii=False, indent=2))
        finally:
            timer.cancel()
            if process.poll() is None:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
