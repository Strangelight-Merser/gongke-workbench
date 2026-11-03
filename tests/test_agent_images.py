"""真实服务和 MCP SDK 验证图片内容块与工程绑定；不调用模型或 GUI。"""
import asyncio
import base64
import hashlib
import json
import sys
from io import BytesIO

from PIL import Image

from mcp import Client, StdioServerParameters
from tests.mcp_helpers import ROOT, ServiceProcess

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl6nGAAAAAASUVORK5CYII=")


def test_bound_image_is_an_image_block_not_base64_text(tmp_path):
    service = ServiceProcess(tmp_path)
    (service.project / "drawing.png").write_bytes(PNG)
    pixels = Image.new("RGB", (20, 12), "white")
    pixels.putpixel((4, 3), (0, 0, 0))
    pixels.save(service.project / "labels.png")
    original = (service.project / "labels.png").read_bytes()
    outside = tmp_path / "outside.png"
    outside.write_bytes(PNG)
    (service.project / "escape.png").symlink_to(outside)

    async def run():
        params = StdioServerParameters(command=sys.executable, args=["-m", "gongke_app", "mcp", "--state-dir", str(service.state),
            "--project", str(service.project)], cwd=str(ROOT))
        async with Client(params) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            assert tools["project.read_image"].annotations.read_only_hint
            response = await client.call_tool("project.read_image", {"path": "drawing.png"})
            assert not response.is_error
            image = next(c for c in response.content if c.type == "image")
            assert base64.b64decode(image.data) == PNG
            assert image.mime_type == "image/png"
            metadata = response.structured_content["result"]
            assert metadata["sha256"] == hashlib.sha256(PNG).hexdigest()
            assert "data" not in metadata
            assert "data" not in json.loads(response.content[0].text)["result"]
            task = service.request("task.get", {"task_id": response.structured_content["task_id"]})
            assert task["receipts"][0]["command"] == "project.read_image"
            crop = await client.call_tool("project.read_image", {"path": "labels.png", "crop": [4, 3, 8, 6], "scale": 3})
            assert not crop.is_error
            crop_meta = crop.structured_content["result"]
            assert crop_meta["sha256"] == hashlib.sha256(original).hexdigest()
            assert crop_meta["source_pixels"] == [20, 12] and crop_meta["pixels"] == [12, 9]
            cropped = base64.b64decode(next(c for c in crop.content if c.type == "image").data)
            assert crop_meta["content_sha256"] == hashlib.sha256(cropped).hexdigest()
            assert Image.open(BytesIO(cropped)).getpixel((2, 2)) == (0, 0, 0)
            assert (service.project / "labels.png").read_bytes() == original
            for patch in ({"crop": [4, 3, 21, 6]}, {"crop": [4, 3, 4, 6]}, {"scale": 5}):
                invalid_crop = await client.call_tool("project.read_image", {"path": "labels.png", **patch})
                assert invalid_crop.is_error and all(c.type != "image" for c in invalid_crop.content)
            for file in ("../outside.png", str(outside), "escape.png", "missing.png"):
                result = await client.call_tool("project.read_image", {"path": file})
                assert result.is_error and all(c.type != "image" for c in result.content)
            service.request("project.create", {"path": str(tmp_path / "other")})
            invalidated = await client.call_tool("project.read_image", {"path": "drawing.png"})
            assert invalidated.is_error and "绑定已失效" in invalidated.content[0].text
    try:
        asyncio.run(run())
    finally:
        service.close()
