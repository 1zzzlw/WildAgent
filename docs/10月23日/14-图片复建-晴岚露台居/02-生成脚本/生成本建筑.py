from pathlib import Path
import subprocess, sys
folder=Path(__file__).resolve().parents[1]
raise SystemExit(subprocess.call([sys.executable,'-X','utf8',str(folder.parent/'参考图创作工具/生成参考建筑.py'),'--case',folder.name.split('-')[0]]))
