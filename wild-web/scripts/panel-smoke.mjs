// 构件库面板的渲染冒烟：把 `LibraryPanel.vue` 真正渲染成 HTML，检查条目是否出现。
//
// 为什么需要它：类型检查只能证明「字段对得上」，证明不了「模板里那个 computed
// 真的渲染出了东西」。面板漏条目、分组空掉、把 undefined 当字符串渲染，
// 都不会让 vue-tsc 变红。
//
// 走 vite 的 SSR dev 通道（`ssrLoadModule`）而不是 build：SFC 由 @vitejs/plugin-vue
// 现场编译，不需要为一条冒烟测试维护第二份构建配置。
//
// 用法：node scripts/panel-smoke.mjs
import { rm, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const entryPath = join(root, '.panel-smoke-entry.ts');
const entryUrl = '/.panel-smoke-entry.ts';

const entry = `
import { createApp, h } from 'vue'
import { createPinia } from 'pinia'
import { renderToString } from 'vue/server-renderer'
import LibraryPanel from './src/components/panels/LibraryPanel.vue'

export async function render() {
  const app = createApp({ render: () => h(LibraryPanel) })
  app.use(createPinia())
  return await renderToString(app)
}
`;

let failures = 0;
let server;
try {
  await writeFile(entryPath, entry, 'utf8');
  // 不在这里再传一次 vue()：vite 会自动加载 vite.config.ts，那份里已经有插件。
  // 重复应用会让 plugin-vue 二次解析已编译产物，报「缺 template/script」这类假错。
  server = await createServer({
    root,
    logLevel: 'silent',
    server: { middlewareMode: true, hmr: false },
    appType: 'custom',
  });

  const module = await server.ssrLoadModule(entryUrl);
  const html = await module.render();

  // 「构件」页是默认页：基础构件 + 组合构件都该在。
  const expected = [
    '构件', '物品', '基础构件', '组合构件',
    '墙体', '屋顶', // 基础构件
    '门', '窗', '栏杆', '雨棚', '阳台', '坡道', '凸窗', '檐口',
    '灯泡', '台灯', '电梯', // 尚未迁移的手写构件
    '吊扇', '烟囱', '百叶格栅', // 配方构件（数据定义）
  ];
  const missing = expected.filter(text => !html.includes(text));
  if (missing.length > 0) {
    console.error(`✗ 面板没有渲染出: ${missing.join('、')}`);
    failures += 1;
  }

  // 渲染出 undefined / NaN 说明某个 computed 拿到空值还在往外吐。
  if (/>\s*(undefined|NaN)\s*</.test(html)) {
    console.error('✗ 面板里出现了 undefined / NaN 文本');
    failures += 1;
  }

  const blockCount = (html.match(/class="block-item/g) || []).length;
  if (blockCount < 19) {
    console.error(`✗ 构件格子只有 ${blockCount} 个，少于预期的 19（6 基础 + 13 组合）`);
    failures += 1;
  }

  if (failures === 0) {
    console.log(`✓ 面板渲染通过：${blockCount} 个构件格子，${expected.length} 个关键文案齐全`);
  }
} catch (error) {
  console.error(`✗ 面板渲染抛错: ${error?.stack || error}`);
  failures += 1;
} finally {
  if (server) await server.close();
  await rm(entryPath, { force: true });
}

process.exit(failures === 0 ? 0 : 1);
