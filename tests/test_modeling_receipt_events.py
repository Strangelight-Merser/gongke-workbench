"""建模观看流的工程归属与持久化回执，不操作真实宿主。"""
from gongke_app.tasks import Tasks


def test_receipt_events_identify_project_and_update_same_receipt(tmp_path):
    events = []
    manager = Tasks(tmp_path, events.append)
    try:
        def action(ctx):
            receipt = ctx.begin('host.feature', {'host_id': 'freecad'})
            ctx.finish(receipt, {'outcome': 'committed'})
            return {'outcome': 'committed'}
        manager.start('mcp', tmp_path / 'project', action, inline=True)
        receipts = [e for e in events if e['event'] == 'task.receipt']
        assert len(receipts) == 2
        assert receipts[0]['task_id'] == receipts[1]['task_id']
        assert receipts[0]['receipt']['at'] == receipts[1]['receipt']['at']
        assert all(e['project'] == str(tmp_path / 'project') for e in receipts)
        assert [e['receipt']['phase'] for e in receipts] == ['prepared', 'finished']
        saved = manager.get(receipts[0]['task_id'])
        assert saved['receipts'][0]['result'] == {'outcome': 'committed'}
    finally:
        manager.close()
