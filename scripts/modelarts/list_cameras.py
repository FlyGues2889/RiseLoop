"""List DirectShow camera indices so ``--camera N`` matches the right device."""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from pygrabber.dshow_graph import FilterGraph
    except ImportError:
        print(
            "pygrabber 未安装。执行："
            " python -m pip install pygrabber"
        )
        return 1

    for index, name in enumerate(FilterGraph().get_input_devices()):
        print(f"{index}\t{name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
