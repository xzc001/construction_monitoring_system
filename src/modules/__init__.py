"""功能模块集合 —— 每个业务功能一个独立子包, 互不耦合。

约定:
  每个模块自带 detector / rules / pipeline / config, 只复用 src 顶层的
  共享基建 (types / visualizer / detectors.person / rules.tracker 等),
  绝不互相 import 其它业务模块的逻辑。

已上线:
  panel  配电箱门"无人值守"告警
"""
