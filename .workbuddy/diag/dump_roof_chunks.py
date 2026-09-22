"""打印"屋顶构件能力"这组查询实际命中的分片正文，确认模型能看到多体量屋顶规则。"""
import sys
from pathlib import Path

WS = Path(r'E:\AgentProject\WildAgent\wild-server')
sys.path.insert(0, str(WS))

from app.spec.loader import MarkdownChunker  # noqa: E402

KB = WS / 'storage' / 'knowledge_base'
CFG = KB / 'config.yaml'

chunker = MarkdownChunker(metadata_config_path=CFG)
chunks = []
for p in sorted(KB.rglob('*.md')):
    chunks.extend(chunker.split_file(p, namespace='probe', doc_scope='generation'))

print(f'全部参与生成的分片: {len(chunks)}')

hits = [
    c for c in chunks
    if str(c.metadata.get('doc_type')) == 'component'
    and str(c.metadata.get('entity_type')) == 'roof'
]
print(f'"屋顶构件能力" 条件命中: {len(hits)} 片\n')


def body(c):
    for attr in ('text', 'content', 'page_content'):
        if hasattr(c, attr):
            return str(getattr(c, attr))
    return repr(c)[:400]


for i, c in enumerate(hits, 1):
    print('=' * 74)
    print(f'[{i}] 来源: {c.metadata.get("source_file")}   role={c.metadata.get("knowledge_role")}')
    head = c.metadata.get('heading') or c.metadata.get('section') or ''
    if head:
        print(f'    标题: {head}')
    print('    ---- 正文 ----')
    text = body(c)
    print('\n'.join('    ' + line for line in text.splitlines()[:28]))
    print(f'    ...（共 {len(text)} 字符）')
    print()

# 反向：全库里到底有没有"多体量"字样的分片，以及它们的 metadata
print('=' * 74)
print('含"多体量"字样的分片及其 metadata（判断能否被屋顶查询捞到）')
print('=' * 74)
for c in chunks:
    t = body(c)
    if '多体量' in t:
        print(f'  文件={c.metadata.get("source_file")}  '
              f'doc_type={c.metadata.get("doc_type")}  entity_type={c.metadata.get("entity_type")}  '
              f'role={c.metadata.get("knowledge_role")}')
