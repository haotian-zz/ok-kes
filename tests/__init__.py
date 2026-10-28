# 单测统一把 dev_out 指到临时目录（ok_tasks/dev_paths.py）：测试里走到的流程追踪、局内状态落盘、每局记录都写这里，
# 不写也不删实机 dev_out 下的文件（实录 2026-10-27 17:58:50 实机追踪里混进一条测试的「escape」）。
# 要在任何 ok_tasks 模块导入前设好：python -m unittest tests.Xxx 会先执行这个文件。
import atexit
import os
import shutil
import tempfile

if not os.environ.get("OKKES_DEV_OUT"):
    _tmp = tempfile.mkdtemp(prefix="okkes_test_dev_out_")
    os.environ["OKKES_DEV_OUT"] = _tmp
    atexit.register(shutil.rmtree, _tmp, True)
