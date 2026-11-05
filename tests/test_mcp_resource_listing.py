"""资源枚举不依赖模型；通过真实 stdio 服务验证 dsh 探测目标。"""
import asyncio
from mcp import Client
from tests.test_mcp_server import service, client_params


def test_resource_listing_and_reading_through_stdio(service):
    async def journey():
        async with Client(client_params(service, write=False)) as client:
            resources = (await client.list_resources()).resources
            assert {str(r.uri) for r in resources} == {
                "gongke://modeling", "gongke://drawing-input"
            }
            for resource in resources:
                result = await client.read_resource(resource.uri)
                assert result.contents[0].text
    asyncio.run(journey())
