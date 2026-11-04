"""Source-pinned official cam arguments shared by execution and inspection."""
from pathlib import Path


def capture_argv(executable):
    return [str(Path(executable)), '--camera', 'Virtual2', '--capture=3',
            '--stream', 'role=video,width=400,height=300,pixelformat=NV12']
