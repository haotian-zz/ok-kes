# dev_out 下的运行时文件（流程追踪、局内状态落盘、每局记录、首领连败计数）统一从这里取目录。
# 单测在 tests/__init__.py 里把环境变量 OKKES_DEV_OUT 指到临时目录，测试调用到的落盘/追踪都写那里，不碰实机的 dev_out
# （实录 2026-10-27 17:58:50：TestRouteClickSettle 走到 audit_escape → chaos_trace.step，往实机追踪里写了一条「escape」，
# 还会按 KEEP_RUNS 删掉实机的旧追踪）。
import os

ENV = "OKKES_DEV_OUT"


def dev_out(*parts):
    return os.path.join(os.environ.get(ENV) or "dev_out", *parts)
