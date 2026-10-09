"""Real UI purchase once, controlled locator failure, read-only recovery and clean rerun."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from airtest.core.api import Template
from gameqa.bridge import Bridge, TransientError, redact
from gameqa.config import load_config, resolve_path
from gameqa.device import AndroidDevice
from gameqa.evidence import Evidence, write_report
from gameqa.stendhal import Stendhal, quantity
from gameqa.stendhal_ui import ASSETS, StendhalUI

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from cases.test_stendhal_ui import test_android_purchase_has_correct_money_and_inventory


def main():
    parser = argparse.ArgumentParser(description='可控定位失败演练；不会重复购买')
    parser.add_argument('--config')
    parser.add_argument('--report-dir', type=Path, required=True)
    args = parser.parse_args()
    root = args.report_dir.resolve()
    root.mkdir(parents=True, exist_ok=False)
    config = load_config(args.config)
    game = config['games']['stendhal']
    qa = Evidence('CONTROLLED-LOCATE-FAILURE', root / 'controlled/CONTROLLED-LOCATE-FAILURE')
    qa.data['diagnostics']['controlled_experiment'] = {
        'fault': 'one intentional wrong template after an actual purchase',
        'normal_case_count': 0, 'recovered_report': '../../recovered/summary.json'}
    android = AndroidDevice(config['device']['uri'], qa)
    ui = StendhalUI(android, game)
    connection = Bridge(game['bridge_command'], cwd=resolve_path(config, game['bridge_cwd']), timeout=30)
    observer, snapshot = None, None
    attempts = 0

    def prepare(**fields):
        nonlocal snapshot
        if snapshot: raise ValueError('one snapshot per exercise')
        result = observer.prepare(**fields)
        snapshot = result['snapshot_id']
        return result['after']

    try:
        ui.ensure_login()
        observer = Stendhal(connection, game, qa)
        test_android_purchase_has_correct_money_and_inventory(qa, ui, observer, prepare)
        before = observer.inspect()

        def locate_readonly():
            nonlocal attempts
            attempts += 1
            # First try deliberately uses a quest-window template on the actual map.
            # Recovery changes only the locator, with no chat/touch/purchase inside it.
            name, roi = ('quest-completed', (96, 203, 565, 555)) if attempts == 1 else (
                'send', (96, 555, 565, 578))
            x1, y1, x2, y2 = roi
            screen = android.device.snapshot()
            match = Template(str(ASSETS / (name + '.png')), threshold=.9).match_in(screen[y1:y2, x1:x2])
            qa.data['diagnostics'].setdefault('fault_locator', []).append(
                {'attempt': attempts, 'template': name, 'region': roi, 'matched': bool(match)})
            android.screenshot('主动定位失败：错误模板' if attempts == 1 else '观察恢复：正确发送按钮模板')
            if not match: raise TransientError('controlled wrong-template location failure')
            return match

        qa.observe('可控定位失败后只重试观察', locate_readonly, retries=1)
        after = observer.inspect()
        qa.check('恢复过程不重复扣款或发货', [before['money'], quantity(before, 'cheese'),
                                                  after['money'], quantity(after, 'cheese')], [60, 2, 60, 2],
                 '原版cheese单价20；100金币购买2件仅一次')
        yes = [s for s in qa.data['steps'] if s.get('kind') == 'business_action'
               and s['title'] == '在游戏界面提交对话：yes']
        qa.check('真实购买确认仅提交一次', len(yes), 1, '业务操作不在Evidence.observe重试闭包中')
        fault = next(s for s in qa.data['steps'] if s['title'] == '可控定位失败后只重试观察')
        qa.check('报告保留首次失败与第二次恢复', [a['outcome'] for a in fault['attempts']],
                 ['failed', 'passed'], 'Evidence.observe逐次保留尝试')
        qa.check('恢复仍标记不稳定', qa.data['unstable'], True, 'Evidence.observe保留unstable，不计正常验收')
        qa.data['outcome'] = 'passed'
    except BaseException as exc:
        qa.data['outcome'] = 'failed'
        qa.data['error'] = str(exc)
        raise
    finally:
        try:
            if snapshot: observer.restore(snapshot)
        except BaseException as exc:
            qa.data['outcome'] = 'error'
            qa.data['restoration_error'] = str(exc)
            raise
        finally:
            try: ui.close()
            finally:
                connection.close()
                qa.data['diagnostics']['interface_messages'] = redact(connection.messages)
                qa.write()
                write_report(root / 'controlled', [qa.data],
                             {'experiment': 'controlled-locator-failure', 'normal_case_count': 0})
    # A fresh process, fresh snapshot and original locator prove independent rerun.
    command = [sys.executable, '-m', 'gameqa', 'run', '--config', config['_path'],
               '--case', 'ST-SHOP-UI-001', '--rounds', '1', '--experiment', 'fault-recovery-rerun',
               '--report-dir', str(root / 'recovered')]
    result = subprocess.run(command, cwd=PROJECT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (root / 'rerun.log').write_text(redact(result.stdout))
    summary = json.loads((root / 'recovered/summary.json').read_text())
    assert result.returncode == 0 and summary['all_passed'] and summary['consistent']
    (root / 'verification.json').write_text(json.dumps({
        'controlled_first_attempt': 'failed', 'controlled_second_attempt': 'passed',
        'controlled_unstable': True, 'business_confirmation_count': 1, 'money': 60, 'cheese': 2,
        'normal_case_count_added': 0, 'restored': True, 'independent_rerun_passed': True},
        ensure_ascii=False, indent=2) + '\n')
    print('演练完成：首次失败已保留；只购买一次；恢复后独立复跑通过。')


if __name__ == '__main__':
    main()
