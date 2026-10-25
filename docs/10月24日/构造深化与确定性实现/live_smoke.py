"""一次有界真实生成；复用前一轮的生产流程验证器，不改生产审核流程。"""
import asyncio
import importlib.util
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
source = HERE.parent / "Agent参数化执行/live_smoke.py"
spec = importlib.util.spec_from_file_location("generation_smoke", source)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)
# 上游验证器只创建了空输出目录；尚未发生调用或写入证据。
smoke.out.rmdir()
smoke.request = """设计并生成一栋单层现代庭院小别墅。两个矩形翼体组成L形围院，总范围控制在14×12米内。
体量、开间和材料构图要有秩序，客厅、卧室与入口关系清楚。浅色墙面配深灰框和木色檐底。
重点深化入口遮蔽、檐口层次与窗的框扇分格：给出有设计理由的尺寸、层次和材料分工，
让这些细节成为可落实的构造，保持墙顶、屋面、洞口之间的真实关系。需要的构件显式列出，不能重复委派。
围院保留空地，不增加道路、车辆、家具或复杂植栽。采用当前构造协议能表达的形式；不适用处保持原创自定义形态。
图纸重复尺寸可用parameters，主体直墙和矩形楼板可用walls/slabs声明。"""
smoke.session = "construction_smoke_" + time.strftime("%Y%m%d_%H%M%S")
smoke.out = HERE / smoke.session
smoke.out.mkdir(exist_ok=False)
smoke.state.update(session_id=smoke.session, request_id=smoke.session, user_message=smoke.request, detail_level="detailed")
smoke.started = time.monotonic()

if __name__ == "__main__":
    asyncio.run(smoke.main())
