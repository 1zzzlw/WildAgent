<template>
<div class="business-plan-page" ref="pageRoot" @scroll.passive="updateReading">
<a class="skip" href="#main">跳到正文</a>
  <header class="topbar">
    <a class="brand" href="#cover" aria-label="WILD 旷野商业计划书首页"><span class="brand-mark" aria-hidden="true">W</span><span class="brand-name">WILD <span class="brand-cn">/ 旷野</span></span></a>
    <span class="top-meta">BUSINESS PLAN / 商业计划书</span>
    <div class="top-actions"><button class="export-pdf" type="button" :disabled="preparingPdf" @click="exportPdf">{{ preparingPdf ? '准备中…' : '导出 PDF' }}</button><RouterLink class="home-link" to="/">回到主页 ↗</RouterLink></div>
    <div class="reading-progress" id="reading-progress" aria-hidden="true" :style="{ width: readingProgress + '%' }"></div>
  </header>
  <p v-if="pdfError" class="pdf-error" role="alert">{{ pdfError }}</p>
  <div class="layout">
    <aside class="sidebar" aria-label="计划书目录">
      <div class="nav-title">CONTENTS / 阅读导航</div>
      <nav>
        <a href="#summary" :aria-current="activeChapter === '#summary' ? 'location' : undefined"><span>01</span>项目摘要</a><a href="#problem" :aria-current="activeChapter === '#problem' ? 'location' : undefined"><span>02</span>问题与机会</a><a href="#product" :aria-current="activeChapter === '#product' ? 'location' : undefined"><span>03</span>产品与核心价值</a><a href="#showcase" :aria-current="activeChapter === '#showcase' ? 'location' : undefined"><span>04</span>近期成果展示</a><a href="#customers" :aria-current="activeChapter === '#customers' ? 'location' : undefined"><span>05</span>客户与市场切口</a><a href="#business" :aria-current="activeChapter === '#business' ? 'location' : undefined"><span>06</span>商业模式</a><a href="#advantage" :aria-current="activeChapter === '#advantage' ? 'location' : undefined"><span>07</span>竞争与长期壁垒</a><a href="#growth" :aria-current="activeChapter === '#growth' ? 'location' : undefined"><span>08</span>获客与验证</a><a href="#roadmap" :aria-current="activeChapter === '#roadmap' ? 'location' : undefined"><span>09</span>发展规划</a><a href="#finance" :aria-current="activeChapter === '#finance' ? 'location' : undefined"><span>10</span>收入与成本试算</a><a href="#team" :aria-current="activeChapter === '#team' ? 'location' : undefined"><span>11</span>团队与合作需求</a><a href="#risks" :aria-current="activeChapter === '#risks' ? 'location' : undefined"><span>12</span>能力边界</a>
      </nav>
      <div class="sidebar-foot">AI 是新的土地。<b>WILD 蓝图，是种子。</b>建筑创作 · 轻量蓝图 · 持续编辑</div>
    </aside>
    <main class="main" id="main">
      <section class="hero" id="cover" aria-labelledby="cover-title">
        <div class="hero-meta"><div class="eyebrow">A blueprint for what comes next</div><div class="edition">建筑创作 / 产品与发展</div></div>
        <div class="hero-grid">
          <div>
            <h1 id="cover-title">让建筑，像文字一样<br><em>被创造与修改。</em></h1>
            <p class="hero-copy">成熟智能体读懂设计语言，写下细节丰富的小体积蓝图。自研参数化引擎重建建筑，网页工作台完成渲染、编辑与交付。让一份设计可以被理解、修改和复用。</p>
            <div class="hero-links"><a class="primary-link" href="#summary">阅读项目摘要 ↓</a><a class="text-link" href="#showcase">查看近期真实渲染 ↗</a></div>
          </div>
          <figure class="hero-visual"><button class="image-open" type="button" data-zoom @click="openImage" aria-label="放大岚石光庭完整渲染图"><img src="/business-plan/lanshi-01.jpg" width="1600" height="1000" alt="岚石光庭：完整建筑、木格栅与水庭"></button><figcaption><span>岚石光庭 / 参数化建筑实景</span><span>点击查看完整大图 ↗</span></figcaption></figure>
        </div>
        <div class="hero-note"><div><b>轻量蓝图</b>交付设计参数，按需重建几何</div><div><b>持续编辑</b>AI 对话与直接操作共同创作</div><div><b>开放生态愿景</b>从建筑工作台走向内容与应用</div></div>
      </section>

      <section class="chapter" id="summary">
        <div class="chapter-heading"><span class="chapter-num">01</span><div><div class="eyebrow">Executive summary</div><h2>用一份蓝图，连接创作与交付</h2></div></div>
        <p class="lead">WILD（旷野）基于现有 WildAgent 项目，围绕“小体积蓝图表达丰富建筑”提供建筑资产的生成、编辑与交付工具。成熟智能体可以依据文档、蓝图语言和示例编写 WILD，由自研几何引擎重建，在网页工作台中预览和持续修改。游戏与互动项目是首期试点方向：通过模型文件及后续原生插件接入客户现有工具链，最终画面由客户的引擎渲染。近期验证制作、修改与复用效率，轻量蓝图的游戏内分发作为后续 SDK 方向验证。</p>
        <div class="brand-story"><div class="eyebrow">WILD / Wild Iterative Language for Design</div><h3>旷野 · 迭代 · 设计语言</h3><p>“旷野”代表不被模板固化的自由创作：让 AI 提出独立的建筑设计，让人可以持续修改与完善。<span class="mono">.wild</span> 是承载设计的蓝图文件后缀。</p><div class="brand-letters"><div><b>W</b><span><strong>Write</strong> 写蓝图</span></div><div><b>I</b><span><strong>Iterate</strong> 迭代 · 联动重算</span></div><div><b>L</b><span><strong>Learn</strong> 读入 · 学习与校验</span></div><div><b>D</b><span><strong>Design</strong> 设计</span></div></div><p class="brand-footnote">四个词表达品牌理念；实际创作先明确设计，再写入蓝图、校验和迭代。</p></div>
        <div class="three-col">
          <article class="panel"><div class="eyebrow">The foundation</div><h3>核心资产是什么</h3><p>WILD 蓝图语言、自研参数化几何与编译引擎，以及网页渲染编辑工作台。成熟智能体、人工与脚本都可依据规范创作，自研 Agent 同步迭代。 </p></article>
          <article class="panel"><div class="eyebrow">The first market</div><h3>先服务谁</h3><p>面向独立开发者、小型场景团队与网页互动项目开展首期试点，先验证一栋建筑的制作、多轮修改与目标应用接入。客户选择取决于实际任务收益和支付意愿，游戏内加载与街区规模按后续验证推进。</p></article>
          <article class="panel"><div class="eyebrow">The business</div><h3>如何形成收入</h3><p>以蓝图体验和基础编辑降低采用门槛，先验证有额度的托管 AI 订阅与明确范围的项目试点。收费依据是节省制作、修改和接入时间；待复用与续费成立，再拓展团队服务、API 和内容交易。价格与转化仍需实测。</p></article>
        </div>
        <div class="statement"><p>土地是 AI 时代，种子是 WILD 蓝图。<br>近期让种子可用，长期让更多人参与创造。</p><div class="small">从可编辑的建筑出发，逐步探索内容社区、互动场景与更开放的创作生态。</div></div>
        <p class="small muted"><span class="label proof">已有项目基础</span> 三包架构、蓝图与编辑工作台、近期渲染和交互证据。<span class="label idea">待商业验证</span> 目标客户需求、付费转化、留存与规模化交付。同类产品的采用数据为市场判断提供参照，WILD 的商业表现由自身试点验证。</p>
      </section>

      <section class="chapter" id="problem">
        <div class="chapter-heading"><span class="chapter-num">02</span><div><div class="eyebrow">Problem & opportunity</div><h2>结果能看见，资产还要用得起来</h2></div></div>
        <div class="three-col">
          <article class="panel"><span class="eyebrow">01 / Delivery</span><h3>建筑越来越细，交付越来越重</h3><p>高细节建筑往往伴随更多网格与纹理。网页展示、版本传递和多次复用需要同时管理资源大小与加载成本。WILD 选择让蓝图保存参数，由引擎重建支持的几何。</p></article>
          <article class="panel"><span class="eyebrow">02 / Iteration</span><h3>生成之后，还有很多轮修改</h3><p>换屋顶、调窗宽、改材质、移动构件，才是连续创作中的日常。产物若保留类型、尺寸与依附关系，就能围绕设计对象修改，而不必每次重做整座建筑。</p></article>
          <article class="panel"><span class="eyebrow">03 / Reliability</span><h3>能表达，不等于能正确落地</h3><p>门窗需要宿主，楼梯需要对齐，参数需要合法。项目把可计算的几何与关系检查交给代码，让 AI 集中处理设计意图，并提供明确的错误反馈。</p></article>
        </div>
        <div class="note">商业机会假设：对需要频繁改方案的用户，价值可能更多来自“生成后仍然好改”，而非单次生成的新鲜感。首轮访谈应验证修改频率、现有流程耗时、返工原因与实际支付意愿。</div>
        <div class="subsection-heading"><div class="eyebrow">Market evidence · Pascal Editor</div><h3>同类产品已吸引用户尝试，持续付费仍需验证</h3><p>Pascal Editor 是可供参考的浏览器建筑编辑产品，支持人与 AI 编辑同一份建筑模型。其公开数据为低门槛建筑创作提供了采用和收费方式的参照；WILD 进一步聚焦游戏与互动场景中的轻量资产交付。</p></div>
        <p class="small muted">资料核查：2026 年 10 月 28 日。以下区分官方历史披露、查询时的社区快照和公开标价；均非 WILD 的经营数据。</p>
        <div class="table-wrap"><table><thead><tr><th scope="col">观察维度</th><th scope="col">可核实的公开信息</th><th scope="col">对 WILD 的商业启示</th></tr></thead><tbody>
          <tr><td data-label="观察维度">早期采用</td><td data-label="可核实的公开信息">Pascal 官方于 2026 年 4 月 14 日披露：上线三周，近 3 万人用其创建过内容。这是官方历史累计使用口径，未披露活跃、留存和付费人数。<a href="https://editor.pascal.app/changelog/2026-04-14-editor-evolution" target="_blank" rel="noopener noreferrer">来源：官方更新公告 ↗</a></td><td data-label="对 WILD 的商业启示">建筑创作工具能够吸引用户尝试。首期应进一步核实游戏与互动团队是否愿意用它完成自己的真实任务。</td></tr>
          <tr><td data-label="观察维度">开发者关注</td><td data-label="可核实的公开信息">本次查询 GitHub 约 2.52 万 Stars、3,100 Forks；仓库以 MIT 许可证开放。关注和派生数量不等于实际使用或付费客户。<a href="https://github.com/pascalorg/editor" target="_blank" rel="noopener noreferrer">来源：官方仓库 ↗</a></td><td data-label="对 WILD 的商业启示">规范、可运行样例与接入文档可以成为获客入口；需要追踪从浏览样例到完成作品、再次使用和付费的转化。</td></tr>
          <tr><td data-label="观察维度">公开收费</td><td data-label="可核实的公开信息">基础建模、编辑与分享免费；Pro 为 100 美元 / 席位 / 月，含 25,000 credits；Max 为 200 美元 / 席位 / 月，含 100,000 credits。AI 工作消耗额度，标价不代表实际成交或收入。<a href="https://editor.pascal.app/" target="_blank" rel="noopener noreferrer">来源：产品官网 ↗</a></td><td data-label="对 WILD 的商业启示">参考“基础体验 + 有额度的 AI 服务”结构，以目标客户预算、完整任务成本和续费反馈确定自己的价格。</td></tr>
        </tbody></table></div>
        <div class="note"><strong>商业对照的适用范围。</strong>Pascal 公司同时布局扫描、编辑和建筑维护，官网突出数据中心等场景；公司整体价值涉及编辑器之外的业务。<a href="https://www.pascal.app/" target="_blank" rel="noopener noreferrer">来源：公司官网 ↗</a> 本次未核实到可归属 Pascal Editor / Pascal Group 的“两亿美元融资”公告，也未取得可靠的 MAU、付费人数或 ARR 数据，本稿不据此推算 WILD 的收入或估值。</div>
        <p class="decision">市场判断方式：用公开案例判断采用机会，用目标客户的任务、付费和续费判断 WILD 的商业价值；市场空间按可触达团队与可成交预算测算。</p>
      </section>

      <section class="chapter" id="product">
        <div class="chapter-heading"><span class="chapter-num">03</span><div><div class="eyebrow">Product & value</div><h2>蓝图是底座，工作台是产品</h2></div></div>
        <p class="lead">用户可以借助成熟智能体依据文档和规范创作，也可以直接编写蓝图，或在网页中操作构件。多种入口围绕同一份 WILD 资产持续迭代。</p><div class="subsection-heading"><div class="eyebrow">From language to workspace</div><h3>成熟智能体创作，自研底座承接</h3><p>把项目文档、WILD 语言规范、当前能力和成功示例交给成熟智能体，即可编写细节丰富、可读可改的小体积蓝图。设计入口可以多样，资产以同一份语言保留下来。</p></div><div class="three-col"><article class="panel"><h3>WILD 设计语言</h3><p>用构件、参数、材质与引用表达设计；重复细节可以由组合与参数展开。蓝图保存设计信息，网格在运行时重建，适合存档、版本比较和复用。</p></article><article class="panel"><h3>自研参数化引擎</h3><p>自研几何构建、组合编译与规则检查，统一解释蓝图中的建筑语义。显示与交互基于 Three.js 和 WebGL，实现浏览器中的实时呈现与持续编辑。</p></article><article class="panel"><h3>文档与构件知识</h3><p>规范、构件规则、成功作品与能力边界共同构成创作基础，可供外部成熟智能体阅读，也为自研 Agent 的按需检索和工具调用提供知识。</p></article></div><div class="note warm"><strong>自研 Agent · 同步开发中。</strong>目前资源投入有限，复杂创作的效果与成熟度仍落后于成熟智能体。当前可借助成熟智能体完成丰富蓝图创作，自研 Agent 持续完善任务编排、知识检索、校验反馈与编辑协作。</div><div class="subsection-heading"><div class="eyebrow">One asset, several ways to create</div><h3>从灵感，到可以继续使用的建筑</h3></div><div class="flowline"><strong>项目文档 + WILD 规范 + 示例</strong><span class="arrow">→</span><span>成熟智能体 / 人工创作</span><span class="arrow">→</span><strong>小体积 .wild</strong><span class="arrow">→</span><span>自研引擎重建</span><span class="arrow">→</span><strong>网页渲染与编辑</strong></div>
        <div class="step-list"><div class="step"><span class="mono">INPUT / 01</span><h4>描述与确认</h4><p>表达用途、体量和风格，审核设计方案。</p></div><div class="step"><span class="mono">BLUEPRINT / 02</span><h4>生成 WILD 蓝图</h4><p>保存构件、参数、引用与材质，执行规则检查。</p></div><div class="step"><span class="mono">WORKSPACE / 03</span><h4>实时编辑与预览</h4><p>拖拽、调参、改材质，或通过对话提出修改。</p></div><div class="step"><span class="mono">DELIVERY / 04</span><h4>保存与继续使用</h4><p>交付蓝图、重建场景，为后续复用提供基础。</p></div></div>
        <div class="subsection-heading"><div class="eyebrow">A building that keeps its meaning</div><h3>交付的不只是形状，还有建筑的设计信息</h3><p>一扇窗除了外观，还应保留它的构件类型、宽高、材质和依附墙体。WILD 将这些信息保存为结构化参数，窗框、玻璃和重复细节由引擎展开。轻量蓝图因此既能用于展示，也能作为下一轮修改的起点。</p></div>
        <div class="two-col">
          <article class="panel"><h3>把设计差异留在文件中</h3><p>蓝图保存构件、尺寸、位置、引用与材质描述，无需逐一保存重建后的顶点和三角面。对于参数化能力覆盖的建筑，丰富细节可以由组合构件与规则表达，便于传输、版本比较和批量复用。</p><p>蓝图体积、纹理等外部资源、展开后的网格与运行开销分别衡量。小文件的价值来自表达方式，最终加载和渲染表现仍需在目标设备上验证。</p></article>
          <article class="panel"><h3>让几何实现保持一致</h3><p>自研 Core 承担参数到几何的计算，Vue 承担编辑界面，Three.js 承担显示适配。将几何算法从界面和模型调用中独立出来，使同一套构件规则可以持续复用与测试。</p><p>在相同引擎版本、配置和资源下，同一蓝图可以重建一致的几何。新的设计仍有变化空间，跨版本使用则需要兼容规则与迁移支持。</p></article>
        </div>
        <div class="subsection-heading"><div class="eyebrow">Design · blueprint · change</div><h3>三份数据契约，贯通从想法到持续修改</h3><p>将设计判断、建筑资产与改动提案分别保存，让人能够确认意图，让程序能够计算与检查，也让每次修改有明确的范围。</p></div>
        <div class="table-wrap"><table><thead><tr><th scope="col">契约</th><th scope="col">保存什么</th><th scope="col">对创作的意义</th></tr></thead><tbody>
          <tr><td data-label="契约">DesignDocument · 设计文档</td><td data-label="保存什么">体量、层数、立面分格、屋顶、构件需求和材质意图</td><td data-label="对创作的意义">在落地前确认方案，区分设计意图与实际实现</td></tr>
          <tr><td data-label="契约">Blueprint · WILD 蓝图</td><td data-label="保存什么">构件身份、参数、位置、依附关系与材质</td><td data-label="对创作的意义">形成可保存、重建、版本管理和继续编辑的资产</td></tr>
          <tr><td data-label="契约">ScenePatch · 修改提案</td><td data-label="保存什么">增删改构件、调整材质等结构化操作</td><td data-label="对创作的意义">对话改动先经过预检与确认，应用失败时回退，减少无关变化</td></tr>
        </tbody></table></div>
        <div class="note"><strong>例如“把这扇窗加宽”。</strong>用户可以直接调整参数，也可以提出对话修改意图。程序根据支持的构件和宿主关系检查改动，再重建相应几何；改变的是已有资产中的设计参数，作品仍可继续编辑。涉及更复杂联动的场景，需要持续补齐约束与验证。</div>
        <div class="subsection-heading"><div class="eyebrow">Product foundation &amp; delivery</div><h3>已有能力如何进入可用的产品</h3></div>
        <div class="table-wrap"><table><thead><tr><th scope="col">产品层</th><th scope="col">已有基础</th><th scope="col">对应的客户价值</th><th scope="col">商业化仍需完成</th></tr></thead><tbody>
          <tr><td data-label="产品层">WILD 蓝图与引擎</td><td data-label="已有基础">结构化建筑描述、组合构件编译与参数化重建</td><td data-label="对应的客户价值">保存设计参数，便于版本管理与重复利用</td><td data-label="商业化仍需完成">兼容性承诺、版本迁移与外部接入文档</td></tr>
          <tr><td data-label="产品层">网页创作工作台</td><td data-label="已有基础">属性、场景树、构件库、拖拽、材质与光影操作，以及静态 GLB 模型导出</td><td data-label="对应的客户价值">小修改直接完成，保留 WILD 源资产并交付通用模型</td><td data-label="商业化仍需完成">新手引导、可靠保存、用户任务验证与目标应用导入验收</td></tr>
          <tr><td data-label="产品层">自研 AI 创作服务</td><td data-label="已有基础">开发中的设计审核、知识检索、执行编排与修改协作</td><td data-label="对应的客户价值">降低入门操作成本，组织多步骤创作</td><td data-label="商业化仍需完成">真实任务通过率、单次成本与付费额度管理</td></tr>
          <tr><td data-label="产品层">开放与内容生态</td><td data-label="已有基础">可复用协议、构件和材质能力提供技术基础</td><td data-label="对应的客户价值">未来可复用他人作品、构件与扩展包</td><td data-label="商业化仍需完成"><span class="label idea">规划</span> 分发、授权、交易、结算及生态治理</td></tr>
        </tbody></table></div>
        
      </section>

      <section class="chapter" id="showcase">
  <div class="chapter-heading"><span class="chapter-num">04</span><div><div class="eyebrow">Architecture, material &amp; space</div><h2>一套语言，承载不同建筑与空间</h2></div></div>
  <p class="lead">从住宅与合院，到展馆、雨夜店铺与海边电车站，WILD 将建筑体量、构件细节、材质与关系保留在可以阅读和修改的蓝图中。这里展示不同风格的完整建筑与微缩场景，点击图片可以放大，展开卡片可查看另一侧视角。</p>
  <div class="showcase-summary"><strong>{{ projects.length }} <small>项作品</small></strong><strong>{{ projects.length * 2 }} <small>幅完整视角</small></strong><strong>完整画幅 <small>保留原始比例</small></strong></div>
  <div class="project-grid">
    <article v-for="project in projects" :key="project.id" class="project-case">
      <div class="project-heading"><div><span class="eyebrow">{{ project.type }}</span><h3>{{ project.name }}</h3></div><span class="project-size mono">{{ project.size }}<small>蓝图</small></span></div>
      <p class="project-story">{{ project.story }}</p>
      <figure class="project-main"><button class="image-open" type="button" data-zoom :aria-label="'放大' + project.name" @click="showImage(project.images[0]!)"><img :src="project.images[0]!.src" :alt="project.images[0]!.alt" :width="project.imageWidth || 1600" :height="project.imageHeight || 1000" loading="lazy"></button><figcaption>作品全貌<span>点击放大 ↗</span></figcaption></figure>
      <details class="more-views"><summary>另一侧完整视角</summary><figure class="project-detail"><button class="image-open" type="button" data-zoom :aria-label="'放大' + project.name + '另一侧视角'" @click="showImage(project.images[1]!)"><img :src="project.images[1]!.src" :alt="project.images[1]!.alt" :width="project.imageWidth || 1600" :height="project.imageHeight || 1000" loading="lazy"></button></figure></details>
    </article>
  </div>
  <div class="subsection-heading"><div class="eyebrow">Interior &amp; materials</div><h3>走进建筑，看见材料与空间</h3><p>木作、石材、玻璃、家具与光照，延续在同一份蓝图和同一个编辑环境中。</p></div>
  <div class="interior-gallery"><figure v-for="image in interiors" :key="image.src" class="project-detail"><button class="image-open" type="button" data-zoom :aria-label="'放大' + image.alt" @click="showImage(image)"><img :src="image.src" :alt="image.alt" width="1600" height="1000" loading="lazy"></button><figcaption>{{ image.alt }}<span>点击放大 ↗</span></figcaption></figure></div>
  <div class="asset-metric"><strong>49,802 <span>bytes</span></strong><span>岚石光庭源蓝图 · 257 个原生元素 + 19 个组合构件<br>文件不内嵌网格或图片，体积不含引擎及外部资源。几何量与运行成本仍需独立衡量。</span></div>
  <div class="note">作品展示蓝图与引擎的表达能力。复杂建筑的生成稳定性、设计一致性与实际使用体验，仍是自研 Agent 和工作台持续完善的重点。</div>
</section>

      <section class="chapter" id="customers">
        <div class="chapter-heading"><span class="chapter-num">05</span><div><div class="eyebrow">Customers & market entry</div><h2>从建筑资产制作与迭代，进入游戏和互动项目</h2></div></div>
        <p class="lead">首期验证用户能否在 WILD 中更高效地制作、修改和复用建筑，再将产物接入自己的项目。网页工作台承担创作与预览，游戏中的渲染、物理和交互继续由客户现有引擎负责。GLB 导出已实现，实际游戏接入与付费需求仍需试点；原生插件和运行时 SDK 属于后续规划。</p>
        <div class="table-wrap"><table><thead><tr><th scope="col">客户与优先级</th><th scope="col">首个任务</th><th scope="col">可能的付费理由</th><th scope="col">需要验证的门槛</th></tr></thead><tbody>
          <tr><td data-label="客户与优先级">首期试点：独立游戏开发者<br>与小型游戏场景团队</td><td data-label="首个任务">制作一栋住宅、庭院或场景单体，完成多轮修改、模型导入与更新</td><td data-label="可能的付费理由">参数变体、持续修改与重复利用，节省资产制作和返工时间</td><td data-label="需要验证的门槛">材质、坐标、模型结构、碰撞和 LOD；接入与清理成本是否抵消制作效率收益</td></tr>
          <tr><td data-label="客户与优先级">优先：网页三维与<br>互动展示团队</td><td data-label="首个任务">在网页中呈现、修改与交付建筑场景</td><td data-label="可能的付费理由">轻量描述、浏览器重建，以及统一编辑入口</td><td data-label="需要验证的门槛">集成工作量、移动设备表现、版本兼容和资源总成本</td></tr>
          <tr><td data-label="客户与优先级">次优先：设计教育<br>与方案表达用户</td><td data-label="首个任务">学习构件与风格，比较概念方案，完成交流演示</td><td data-label="可能的付费理由">直观表达与迭代便利</td><td data-label="需要验证的门槛">使用频次、预算与采购周期；不依赖专业施工交付</td></tr>
          <tr><td data-label="客户与优先级">后续：企业平台<br>与互动世界开发者</td><td data-label="首个任务">把蓝图和生成服务接入自有应用</td><td data-label="可能的付费理由">可复用资产供给、定制构件和服务支持</td><td data-label="需要验证的门槛">真实接入项目、服务可靠性、授权、成本与维护责任</td></tr>
        </tbody></table></div>
        <div class="subsection-heading"><div class="eyebrow">Tasks people can actually use</div><h3>围绕完整任务，而非一次生成结果</h3></div>
        <div class="two-col">
          <article class="panel"><h3>方案交流与设计学习</h3><p>在相同视角和光照下，比较体量、立面节奏、屋顶与材料；保留每个方案的蓝图，继续调参和讲解。适合概念阶段的讨论、教学与创作演示，工程结构和施工图仍由专业流程承担。</p></article>
          <article class="panel"><h3>从单体建筑到游戏场景</h3><p>优先用住宅、咖啡空间、展馆和亭榭完成实际游戏接入，再验证街区、建筑变体与互动叙事。家具、器物与景观构件可以沿用参数化表达；场景规模、碰撞、导航与交互仍需分别建设和验收。</p></article>
        </div>
        <div class="subsection-heading"><div class="eyebrow">Create in WILD · render in the customer's engine</div><h3>接入现有引擎，按阶段验证交付方式</h3><p>WILD 的几何重建与网页显示适配已经分开。游戏团队可以先使用模型交付；后续插件或 SDK 将蓝图转换为目标引擎的原生网格与材质，由目标引擎统一绘制。原生接入仍需开发语言、材质和资源生命周期等适配。</p></div>
        <div class="table-wrap"><table><thead><tr><th scope="col">接入路线与状态</th><th scope="col">交付与渲染分工</th><th scope="col">客户价值与验证重点</th></tr></thead><tbody>
          <tr><td data-label="接入路线与状态">制作期模型导出<br><span class="label proof">GLB 导出已实现</span></td><td data-label="交付与渲染分工">在网页工作台制作和修改，保留 .wild 源文件，导出静态 GLB 后交给客户现有引擎导入和渲染；游戏运行时使用导入后的资产</td><td data-label="客户价值与验证重点">先验证制作、多轮修改、重导入和返工的总时间。已通过本地 GLB 下载与重新加载检查，目标游戏引擎、材质与实例化扩展兼容性仍待验证；程序化效果与交互需另外适配</td></tr>
          <tr><td data-label="接入路线与状态">编辑器原生导入插件<br><span class="label idea">规划</span></td><td data-label="交付与渲染分工">制作阶段读取 .wild，重建为目标编辑器中的原生网格与材质；最终游戏使用自身引擎，不需要运行网页渲染器</td><td data-label="客户价值与验证重点">在编辑器工作流中保留参数与更新关联。需验证导入和重导入规则、已有编辑如何保留、版本兼容及插件维护成本</td></tr>
          <tr><td data-label="接入路线与状态">游戏内蓝图重建 SDK<br><span class="label idea">后续验证</span></td><td data-label="交付与渲染分工">游戏加载蓝图，由重建模块生成原生几何并交给客户引擎绘制；共用重建规则、纹理等资源仍需随应用部署</td><td data-label="客户价值与验证重点">验证轻量数据分发、动态变体和按需重建。需实测完整下载量、重建耗时、首帧、内存显存、帧时间及目标平台兼容性，不纳入首期交付承诺</td></tr>
        </tbody></table></div>
        <p class="small muted gap-top">互通路径参照：<a href="https://docs.godotengine.org/en/stable/tutorials/assets_pipeline/importing_3d_scenes/available_formats.html" target="_blank" rel="noopener noreferrer">Godot 官方 glTF / GLB 导入说明 ↗</a>、<a href="https://dev.epicgames.com/documentation/en-us/unreal-engine/the-gl-transmission-format-gltf-in-unreal-engine" target="_blank" rel="noopener noreferrer">Unreal 官方 glTF 导入说明 ↗</a>。引擎支持格式提供了接入入口，WILD 产物在具体版本中的可用性仍需实际导入验证。</p>
        <div class="two-col gap-top"><article class="panel"><h3>首个试点验收完整制作流程</h3><p>选择一个目标引擎，完成“制作一栋建筑 → 多轮修改 → 模型导入 → 修改后重导入”，检查比例、坐标、材质、对象组织、碰撞和 LOD，以及目标设备的绘制次数和帧时间。</p><p>与客户原有流程记录相同范围和质量要求下的总耗时，计入资产清理、重导入与人工支持。由实际收益判断是否继续扩大游戏场景投入。</p></article><article class="panel"><h3>小蓝图的收益，按使用阶段衡量</h3><p>制作期的小文件价值在于保存设计参数、生成变体、持续修改和复用。若最终交付展开后的 GLB，应按模型与纹理的完整体积评估游戏资产成本，不能用 .wild 的体积推算安装包收益。</p><p>运行期的轻量分发需要 SDK 接入证明；展开后的网格、纹理和渲染开销仍然存在。资源共享、按需加载与细节分级需分别实现和实测。</p></article></div>
        <p class="decision">首个付费承诺建议：“在约定建筑类型与复杂度内，交付可继续编辑的 WILD 源资产与约定的模型产物。”目标应用的导入、材质和更新范围，按实际试点验收结果确定。</p>
        <div class="two-col gap-top"><article class="panel"><h3>可触达市场的测量方法</h3><p>先建立目标团队名录，核实每月相关任务量、现有工具费用、决策人和付费意愿。以“可触达团队数 × 可接受月费”形成首期收入空间测算，并记录访谈依据。</p></article><article class="panel"><h3>不把远景当作首期市场</h3><p>专业 BIM、施工图与结构计算要求更完整的专业能力和责任体系。自主数字世界需要额外的角色、行为与持续状态系统；本稿将其放在远期拓展阶段。</p></article></div>
      </section>

      <section class="chapter" id="business">
        <div class="chapter-heading"><span class="chapter-num">06</span><div><div class="eyebrow">Business model</div><h2>围绕持续创作收费，逐步验证收入</h2></div></div>
        <div class="section-label"><p class="small muted">以下为定价实验草案，尚未上线或验证；额度与服务范围须以实际成本及试点反馈确定。</p><span class="label idea">建议方案</span></div>
        <div class="three-col">
          <article class="panel price-card"><span class="label">基础体验</span><h3>看见价值</h3><div class="price">¥0 <small>/ 受控体验</small></div><ul class="compact-list"><li>样例浏览、本地蓝图体验与基础编辑。</li><li>托管 AI 试用设置严格额度。</li><li>用实际完成任务引导升级。</li></ul><p class="small">目的：降低学习门槛，验证激活与留存。</p></article>
          <article class="panel price-card featured"><span class="label proof">首期付费实验</span><h3>创作者 Pro</h3><div class="price">¥99 <small>/ 月 · 试探价</small></div><ul class="compact-list"><li>托管创作与保存服务。</li><li>包含明确上限的 AI 生成额度。</li><li>超额按用量收费，价格另行验证。</li></ul><p class="small">目的：验证独立用户的持续支付意愿。</p></article>
          <article class="panel price-card"><span class="label">团队与项目试点</span><h3>工作室 / API 合作</h3><div class="price">按范围 <small>/ 报价</small></div><ul class="compact-list"><li>以明确验收项开展有限付费试点。</li><li>后续评估团队空间、额度与 API。</li><li>定制维护成本单独核算。</li></ul><p class="small">目的：发现可重复需求，避免无限定制。</p></article>
        </div>
        <div class="note"><strong>价格实验如何使用竞品参照。</strong>Pascal 的美元席位价仅用于研究收费结构；WILD 的 ¥99 是面向自身目标用户的独立试探价，尚无价格优势或利润率结论。先记录完成一座建筑及多轮修改所需的模型、重试、存储和人工支持成本，再确定套餐额度与超额价格。成熟智能体可直接创作蓝图，托管服务需要以更省时、可靠的完整流程证明付费理由。</div>
        <div class="two-col gap-top"><article class="panel"><h3>开放降低采用门槛，服务承接收费</h3><p>建议公开稳定的蓝图规范、示例与接入文档，逐步评估引擎开放范围。让外部工具也能生成 WILD，以便扩大使用入口。具体开源范围、许可证与第三方资源授权需要确认。</p><p>收费价值放在托管计算、可靠存储、协作、运维支持和企业交付上。开放规范的商业作用，是降低采用成本并提高复用机会。</p></article><article class="panel"><h3>内容交易是后续收入选项</h3><p>当用户开始重复使用构件、风格或材质包，再验证付费内容与平台分成。抽成比例暂不设定，需要先有真实交易量、版权规则与结算能力。</p><p>初期保留少量高质量范例与官方内容，优先保障工作台可用性，不提前建设完整商城。</p></article></div>
        <div class="flowline"><strong>开放规范与样例</strong><span class="arrow">→</span><span>完成第一次创作</span><span class="arrow">→</span><span>持续编辑与复用</span><span class="arrow">→</span><strong>托管订阅 / 团队服务</strong><span class="arrow">→</span><span>内容生态（后续）</span></div>
      </section>

      <section class="chapter" id="advantage">
        <div class="chapter-heading"><span class="chapter-num">07</span><div><div class="eyebrow">Positioning & defensibility</div><h2>差异来自资产与工作流，价值要靠使用证明</h2></div></div>
        <div class="table-wrap"><table><thead><tr><th scope="col">用户可选路线</th><th scope="col">通常关注的结果</th><th scope="col">WILD 的选择</th><th scope="col">验证重点</th></tr></thead><tbody>
          <tr><td data-label="用户可选路线">成熟建模与专业建筑工具</td><td data-label="通常关注的结果">广泛的建模能力、专业工作流与成熟生态</td><td data-label="WILD 的选择">聚焦浏览器里的参数化建筑创作和轻量交付</td><td data-label="验证重点">在具体小型任务中能否减少操作与交接</td></tr>
          <tr><td data-label="用户可选路线">Pascal Editor 等浏览器建筑编辑产品</td><td data-label="通常关注的结果">结构化建筑模型、人与 AI 共同编辑，以及开放引擎、MCP 和 API 接入</td><td data-label="WILD 的选择">以紧凑的参数化蓝图承载细节，聚焦游戏与互动场景中的建筑变体、持续修改和资产分发</td><td data-label="验证重点">在相近视觉质量与编辑要求下，验证完整交付体积、修改耗时、生成与重建成本及目标场景接入</td></tr>
          <tr><td data-label="用户可选路线">AI 三维资产生成</td><td data-label="通常关注的结果">快速获得形体或可视化资产</td><td data-label="WILD 的选择">围绕建筑构件、参数与引用保留可修改信息</td><td data-label="验证重点">编辑与复用价值是否足以支持迁移成本</td></tr>
          <tr><td data-label="用户可选路线">通用编程 Agent + WILD / 场景代码</td><td data-label="通常关注的结果">读取规范和示例，创作蓝图或自定义三维场景</td><td data-label="WILD 的选择">将规范、引擎、校验和直接编辑沉淀在工作台</td><td data-label="验证重点">实际任务的成品质量、成本、耗时与修改准确性</td></tr>
        </tbody></table></div>
        <p class="small muted gap-top">Pascal 行依据其<a href="https://editor.pascal.app/" target="_blank" rel="noopener noreferrer">产品官网 ↗</a>与<a href="https://github.com/pascalorg/editor" target="_blank" rel="noopener noreferrer">官方仓库 ↗</a>的公开能力说明；本表讨论产品路线，未进行同条件质量或性能测试。通用 Agent 也能编写 WILD，采用专门工作流本身不能证明效果优于其他方案。</p>
        <div class="two-col gap-top"><article class="panel"><h3>把共同能力作为竞争起点</h3><p>浏览器建模、结构化建筑对象、AI 修改与开放接口在同类产品中已有实践。WILD 需要让用户在一个真实工作流中感受到差异：更快完成修改、以紧凑蓝图保留建筑变体，并通过约定的产物接入目标应用。</p><p>同类开源方案降低了进入门槛，也提高了替代压力。支持范围、兼容性、可复用内容和交付体验需要在持续使用中积累。</p></article><article class="panel"><h3>让“小文件”对应可计量的客户收益</h3><p>WILD 的核心方向是用小体积参数化描述重建精细建筑。近期验证源资产的修改、变体生成与复用效率，同时计入模型交付和接入成本；GLB 导出后的文件大小单独统计。</p><p>未来运行时 SDK 若能可靠重建，再验证蓝图分发的下载与更新收益。源文件紧凑、游戏安装包大小和运行帧率是不同指标，各自需要证据。</p></article></div>
        <div class="subsection-heading"><div class="eyebrow">Architectural modeling · feature mapping</div><h3>与现有建筑建模工作流，逐项对应功能</h3><p>以 SketchUp 的几何与组件工作流、Revit 的参数化与 BIM 工作流为参照，说明用户熟悉的操作在 WILD 中对应什么。不同工具各有侧重，下表区分已有基础、部分支持和后续工作。</p></div>
        <div class="table-wrap"><table><thead><tr><th scope="col">建模环节</th><th scope="col">现有建模工具的对应功能</th><th scope="col">WILD 当前对应能力</th><th scope="col">边界与后续工作</th></tr></thead><tbody>
          <tr><td data-label="建模环节">体量与建筑构件</td><td data-label="现有建模工具的对应功能">SketchUp 用几何与组件组织模型；Revit 提供墙、门窗等参数化建筑构件</td><td data-label="WILD 当前对应能力">已有墙、楼板、楼梯和通用几何基础；门窗等组合构件由参数编译展开，屋顶、柱梁和家具等仍为部分支持</td><td data-label="边界与后续工作">持续补齐构件与组合质量；任意曲面、扫描级造型及完整专业建筑体系超出当前覆盖</td></tr>
          <tr><td data-label="建模环节">精确定位与尺寸调整</td><td data-label="现有建模工具的对应功能">SketchUp 支持按轴、距离或坐标移动；参数化工具通过构件属性调整尺寸</td><td data-label="WILD 当前对应能力">已有三轴拖拽、属性调参，以及带宿主信息的构件放置基础</td><td data-label="边界与后续工作">对齐、阵列、批量替换、楼层复制和多选联动仍需完善</td></tr>
          <tr><td data-label="建模环节">组件复用与整体联动</td><td data-label="现有建模工具的对应功能">SketchUp 以组件定义和实例复用几何，修改定义可以同步到实例，支持替换组件</td><td data-label="WILD 当前对应能力">已有构件库、参数化构件和声明式重复展开基础，可用紧凑描述生成细节</td><td data-label="边界与后续工作">定义与实例联动、共享缓存及批量修改的产品体验仍需补齐；重复声明不等于 GPU 实例化</td></tr>
          <tr><td data-label="建模环节">材质与视觉表现</td><td data-label="现有建模工具的对应功能">SketchUp 可对面和组件赋予材质；Revit 可连接 Twinmotion 等表现工具</td><td data-label="WILD 当前对应能力">已有 PBR 参数与纹理、程序化材质、环境光影和网页实时预览</td><td data-label="边界与后续工作">完善可复用材质与光影方案，以及目标游戏引擎中的材质映射；实时预览不能代替各类离线渲染能力</td></tr>
          <tr><td data-label="建模环节">对象组织与关联修改</td><td data-label="现有建模工具的对应功能">SketchUp 用嵌套组与组件组织对象；Revit 通过同一建筑模型关联项目视图</td><td data-label="WILD 当前对应能力">蓝图保留构件 ID、参数和宿主引用；场景树组织对象，ScenePatch 提供结构化修改与预检</td><td data-label="边界与后续工作">继续完善跨构件约束和整体参数联动；当前语义关系不能等同于完整 BIM 数据体系</td></tr>
          <tr><td data-label="建模环节">剖切、图纸与工程统计</td><td data-label="现有建模工具的对应功能">Revit 可生成平面、立面、剖面、图纸及明细表，并进行数量与材料统计</td><td data-label="WILD 当前对应能力">已有可调高度的水平剖切预览，可查看建筑内部；同时提供三维蓝图、构件编辑、设计示意与渲染展示</td><td data-label="边界与后续工作">已有三维剖切查看能力；带尺寸标注与规范出图流程的专业平剖面图纸、工程算量、结构计算和施工交付仍不属于当前承诺</td></tr>
          <tr><td data-label="建模环节">文件交换与游戏接入</td><td data-label="现有建模工具的对应功能">成熟工具通过各自支持的模型格式、API 与插件交换数据，例如 Revit 的 BIM/CAD 格式与开发接口</td><td data-label="WILD 当前对应能力">本地 .wild 保存参数与关系，独立 Core 输出网格和材质参数；工作台已提供静态 GLB 导出与本地重新加载验证</td><td data-label="边界与后续工作">目标游戏引擎的材质、实例化扩展、碰撞、导航和重导入仍待实际验收；原生插件与运行时 SDK 属于规划</td></tr>
          <tr><td data-label="建模环节">项目协作与版本管理</td><td data-label="现有建模工具的对应功能">Revit 提供共享模型协作、同步和图纸修订管理</td><td data-label="WILD 当前对应能力">已有蓝图保存、场景版本检查、修改提案和本地过程记录基础</td><td data-label="边界与后续工作">团队空间、多用户并发、权限和完整版本协作仍属产品化工作，不能以单场景修改机制替代</td></tr>
        </tbody></table></div>
        <div class="note"><strong>对应功能，也说明产品定位。</strong>本地文件、组件复用、参数化和外部接入在成熟工具中也有实践。WILD 将轻量蓝图、智能体创作、确定性重建与网页编辑组织为面向游戏建筑资产的工作流，其价值需要通过具体任务的质量、修改效率和交付成本验证。</div>
        <div class="subsection-heading"><div class="eyebrow">Questions that shape the product</div><h3>三个问题，明确专用工作流的价值</h3></div>
        <div class="three-col"><article class="panel"><h3>有了规范，为什么还需要 Agent？</h3><p>规范和示例已经能帮助模型生成 WILD，偶尔创作一份文件可以直接使用成熟智能体。自研 Agent 要解决反复创作时的资料准备、任务组织、结果检查和连续修改，把这些步骤衔接起来。</p><p>这套流程也会增加调用、等待和维护成本，需要用人工操作是否减少、成功交付是否更稳定来判断价值。</p></article><article class="panel"><h3>成熟智能体也能做，差异在哪里？</h3><p>成熟智能体能够生成优秀蓝图，也能够组织类似工作流。WildAgent 将项目知识、构件规则、渲染与编辑沉淀为可以反复使用的产品，让用户在同一工作台完成创作、修改、保存和复用。</p><p>优势需要在真实任务中证明：成品质量、修改准确性、耗时和完整交付成本都要衡量；稳定兼容、优质内容和持续使用才能逐步形成壁垒。</p></article><article class="panel"><h3>模型继续进步，项目如何积累价值？</h3><p>保持模型可替换，持续积累统一协议、构件能力、校验规则、编辑体验和可复用资产。模型升级可以改善设计入口，已有蓝图也应继续可用。</p><p>WILD 保存构件、参数和关系，在加载时重建几何，使小体积蓝图能够承载丰富细节。其价值要通过持续修改与应用复用验证，资产总成本仍需计入纹理、展开后网格和运行资源。</p></article></div>
        <div class="subsection-heading"><div class="eyebrow">Knowledge, control &amp; reuse</div><h3>把经验沉淀进工具，让创作可以反复发生</h3></div>
        <div class="two-col">
          <article class="panel"><h3>按需提供专有知识</h3><p>构件知识库重点保存 WILD 规范、写法与引擎能力边界，按任务检索相关内容。成熟智能体可以直接阅读这些资料，自研 Agent 则继续完善检索与编排，减少每次会话重新理解整个项目的准备工作。</p><p>过程记录用于定位模型、检索、构件和装配的问题，帮助修正文档与实现；它们不会自动训练模型，也不能保证同类错误不再出现。</p></article>
          <article class="panel"><h3>把自动化消耗变得可管理</h3><p>生成粒度同时约束设计范围、构件任务、模型调用和修订预算；用户选择更精细内容时，也需要面对更高的调用与渲染成本。小改动可以通过直接编辑完成，避免每次都消耗模型调用。</p><p>已有设计审核、结构与空间检查以及有界修复的机制。失败草稿和诊断仍可保留，方便继续编辑；检查通过之后，还需要实际渲染与用户判断。</p></article>
          <article class="panel"><h3>表现层可以独立迭代</h3><p>材质、光影和世界外观不必绑定一次 AI 生成。用户可以在已有建筑上持续调整视觉表达，构件与表现能力也可以独立开发、调试和复用。</p></article>
          <article class="panel"><h3>给外部应用留下接入空间</h3><p>服务端封装模型调用、知识检索与生成编排，并有 REST 与 WebSocket 接入基础；几何重建独立于编辑界面。其他应用可以探索复用相应能力，商用接入仍需明确版本、授权、稳定性与支持责任。</p></article>
        </div>
        <div class="subsection-heading"><div class="eyebrow">Creator-held assets &amp; interoperability</div><h3>去中心化的建筑资产：由创作者持有，在不同应用中流转</h3></div>
        <p>WILD 希望让建筑成为创作者可以自行保存、管理和携带的数字资产。一份蓝图保留建筑的构件、参数、材质与关系，在兼容的引擎和资源条件下重建，并继续修改与复用。</p>
        <p>这里的去中心化，主要体现在建筑资产的持有、使用与流转：用户保存自己的蓝图，开发者依据统一规范构建兼容工具，游戏与应用按需接入建筑内容。项目的发展目标，是让创作成果能够跨工具、跨应用使用，减少对单一平台的依赖。</p>
        <p>小体积蓝图为这一方向提供了基础。建筑可以通过紧凑的参数描述进行保存和分发，共用的构件规则负责重建细节，有利于建筑变体、用户创作内容和游戏场景的持续更新。运行时的内存与渲染性能，则通过资源共享、按需加载和目标设备实测逐步优化。</p>
        <p>当前项目已具备本地蓝图文件和独立几何重建引擎的基础。后续将围绕规范开放、版本兼容、资源寻址、授权约定和第三方适配，逐步建设可独立使用、可自由流转的建筑资产生态。商业价值可围绕创作工具、托管计算、协作与优质内容服务形成。</p>
      </section>

      <section class="chapter" id="growth">
        <div class="chapter-heading"><span class="chapter-num">08</span><div><div class="eyebrow">Go-to-market & validation</div><h2>以真实任务验证增长，先找到愿意留下的人</h2></div></div>
        <p class="lead">首期采用创始人直接参与的用户开发：展示完整创作过程，邀请用户带自己的任务试用，再对明确有价值的使用方式收费。下面是建议的首轮实验目标，均非已取得结果。</p>
        <div class="table-wrap"><table><thead><tr><th scope="col">阶段与动作</th><th scope="col">建议样本 / 目标</th><th scope="col">怎样判断有效</th><th scope="col">不通过时怎么调整</th></tr></thead><tbody>
          <tr><td data-label="阶段与动作">访谈与问题确认</td><td data-label="建议样本 / 目标">访谈 20 位目标用户；覆盖创作者与小团队</td><td data-label="怎样判断有效">至少 10 位能描述真实近期任务及重复修改痛点</td><td data-label="不通过时怎么调整">缩小场景，重新确定用户与任务</td></tr>
          <tr><td data-label="阶段与动作">邀请制任务试用</td><td data-label="建议样本 / 目标">招募 10–20 位设计伙伴；任务中记录失败与人工介入</td><td data-label="怎样判断有效">能完成“创建 → 修改 → 保存 → 重开”的完整任务</td><td data-label="不通过时怎么调整">先修复阻塞，不以注册量替代完成率</td></tr>
          <tr><td data-label="阶段与动作">付费试点</td><td data-label="建议样本 / 目标">完成 3–5 个明确范围、实际付款的项目或订阅</td><td data-label="怎样判断有效">客户按约定验收付款，记录交付、支持和退款成本；意向单独统计</td><td data-label="不通过时怎么调整">检查价值、边界、定价或服务成本</td></tr>
          <tr><td data-label="阶段与动作">留存与可重复收入</td><td data-label="建议样本 / 目标">至少观察连续 2 个付费周期</td><td data-label="怎样判断有效">复用与续费发生，单位贡献为正，人工投入趋于可控</td><td data-label="不通过时怎么调整">暂缓扩大投放，优先修复留存原因</td></tr>
        </tbody></table></div>
        <div class="two-col gap-top"><article class="panel"><h3>首批用户从哪里来</h3><p>通过代码仓库、演示站、建筑与三维创作者社群发布任务型演示：展示“同一座建筑如何改三次”，同时提供可体验的蓝图和实际下载体积。面向独立开发者与网页展示团队，演示从样例到目标场景的接入过程。</p></article><article class="panel"><h3>公开演示怎样转为真实采用</h3><p>以 Pascal 的社区关注作为渠道参照，分别记录演示访问、样例下载、完整任务、重复使用和实际付款。Stars、观看量与注册量用于判断触达，产品决策依据用户完成自己的任务和后续使用情况。</p></article></div>
        <div class="subsection-heading"><div class="eyebrow">From interest to paid reuse</div><h3>把关注、任务价值和可持续收入分别衡量</h3><p>以下为试点记录口径，尚未形成实测结果。小样本同时报告人数与比例，按来源和开始使用的批次观察。</p></div>
        <div class="table-wrap"><table><thead><tr><th scope="col">指标</th><th scope="col">记录口径</th><th scope="col">要回答的问题</th></tr></thead><tbody>
          <tr><td data-label="指标">首次激活</td><td data-label="记录口径">首次试用后 7 天内，独立完成“创建 → 修改 → 保存 → 重开”的人数 / 已观察满 7 天的同批开始试用人数</td><td data-label="要回答的问题">用户能否把兴趣转为一份自己可用的作品？</td></tr>
          <tr><td data-label="指标">任务价值与交付成本</td><td data-label="记录口径">格式、空间关系、真实渲染与用户验收分别记录；统计制作、多轮修改和接入耗时，以及完整资源体积。每次验收成功任务的成本计入失败、重试和人工支持</td><td data-label="要回答的问题">轻量蓝图是否节省了用户的时间与交付成本？</td></tr>
          <tr><td data-label="指标">重复使用</td><td data-label="记录口径">首次激活后的第 8–30 天内，再次创作或修改的人数 / 已观察满 30 天的同批激活人数；另记资产被再次复用的情况</td><td data-label="要回答的问题">用户在新鲜感之后，是否仍需要这套工作流？</td></tr>
          <tr><td data-label="指标">付费与续费</td><td data-label="记录口径">试点邀请后 30 天内实际付款人数 / 已观察满 30 天的同批受邀试用人数；下一周期续费人数 / 已到续费期订阅人数。分别列出项目款、订阅、退款与取消</td><td data-label="要回答的问题">需求是否转为真实收入，且能够持续？</td></tr>
          <tr><td data-label="指标">单位贡献</td><td data-label="记录口径">每位付费用户的实际收入减 AI、失败重试、存储带宽、支付和随用户增长的支持成本；同时单列免费试用及渠道获客支出</td><td data-label="要回答的问题">更多使用与付费，能否带来可持续的经营贡献？</td></tr>
        </tbody></table></div>
      </section>

      <section class="chapter" id="roadmap">
        <div class="chapter-heading"><span class="chapter-num">09</span><div><div class="eyebrow">Roadmap & gates</div><h2>发展规划：从可用工作台到创作生态</h2></div></div>
        <div class="subsection-heading"><div class="eyebrow">Agent capability &amp; quality goals</div><h3>自研 Agent 的核心目标：缩小建筑成品的质量差距</h3><p>提升自研 Agent 的建筑创作与可靠执行能力，缩小不同底层模型在建筑任务中的实际成品差距，逐步接近 Codex 等成熟智能体在同类任务中的设计完整度、细节表达和修改质量。希望让更多可选模型在明确的范围与预算内，交付丰富、紧凑且可以继续编辑的 WILD 蓝图，减少人工补救。</p></div>
        <div class="note"><strong>研发目标与当前结果分开。</strong>知识、工具、约束和反馈可以减少流程中的信息遗漏与执行错误，底层模型的推理、设计判断和审美差异仍会影响结果。目前尚无同条件评测证明已达到成熟智能体的成品水平；进展需要由真实建筑任务验证。</div>
        <div class="subsection-heading"><div class="eyebrow">How capability improves</div><h3>从六个方面提升，让设计意图更可靠地落地</h3><p>项目已有设计文档、按需检索、参数展开、校验和过程记录等基础。下面列出继续完善的重点，按问题复现与任务影响安排投入。</p></div>
        <div class="table-wrap"><table><thead><tr><th scope="col">提升方向</th><th scope="col">下一步怎么做</th><th scope="col">验证重点</th></tr></thead><tbody>
          <tr><td data-label="提升方向">设计判断与需求保持</td><td data-label="下一步怎么做">在当前支持范围内，先明确体量比例、入口、屋面、立面层次与材质分工，再落实装饰和陈设。审核方案时同时保留用户硬性条件与可自由设计的部分</td><td data-label="验证重点">设计与成品是否一致，入口及屋面是否完整，比例和层次是否合理；更高粒度是否带来实际表达提升</td></tr>
          <tr><td data-label="提升方向">知识检索与提示组织</td><td data-label="下一步怎么做">按当前构件、宿主和任务阶段提供真实可用的字段规则与最小局部示例；核对知识与引擎能力，减少无关内容和整栋案例对设计的牵引</td><td data-label="验证重点">关键规则是否被召回并落实，字段误用和照搬是否减少；统计完整任务的上下文消耗</td></tr>
          <tr><td data-label="提升方向">参数化执行与构件复用</td><td data-label="下一步怎么做">模型选择形态、比例和材料，程序计算已确定的标高、宿主位置、重复分格与依赖关系。复用既有构造展开和编译入口，减少重复坐标输出，保持蓝图紧凑</td><td data-label="验证重点">改变跨度、层高、朝向和数量后，几何及关系仍符合设计；同时检查文件体积与展开后的资源成本</td></tr>
          <tr><td data-label="提升方向">跨阶段约束与局部修订</td><td data-label="下一步怎么做">让已批准的尺寸、楼层、洞口和材料要求贯穿设计、任务、装配与最终验收。反馈指出失败字段、宿主及预期值，定向修订失败范围并保留通过结果；缺失项明确报告</td><td data-label="验证重点">需求是否逐项落实，修改是否影响无关构件，失败与人工介入是否可追踪；节点完成与最终验收分别记录</td></tr>
          <tr><td data-label="提升方向">真实渲染与视觉反馈</td><td data-label="下一步怎么做">在结构检查之外固定多视图渲染与人工审图，检查遮挡、悬空、屋面交接、比例和材质。将可复现的视觉问题转为修订依据，逐步建设受约束的自动看图反馈</td><td data-label="验证重点">格式通过后是否仍有视觉缺陷，修订是否改善真实画面。当前主链尚无完整自动看图修订闭环，此项自动化仍属规划</td></tr>
          <tr><td data-label="提升方向">运行诊断与质量成本评测</td><td data-label="下一步怎么做">沿运行记录核对输入、检索、模型输出和校验反馈，定位首个偏差环节；按失败类型修正文档、检索或代码，在调用与时间预算内迭代，并回归固定任务集</td><td data-label="验证重点">分别统计解析、编译、空间关系、渲染和用户验收；计入失败、重试、人工修订后的成功交付率、Token、耗时及成本</td></tr>
        </tbody></table></div>
        <div class="note"><strong>怎样判断差距正在缩小？</strong>先在同一底层模型、固定任务集和一致预算下验证工作流带来的收益，再以成熟智能体在同类任务中的成品作为质量参照。使用一致的验收标准，并记录模型、可用工具、资料和预算差异；同时看建筑质量、修改准确性与交付成本。离线检查通过、单个样例成功或构件数量增加，都不足以证明整体质量已经提升。</div>
        <p class="small muted">相对周期自正式启动商业验证起算，属于建议计划；需按团队资源和试点结果调整。</p><div class="subsection-heading"><div class="eyebrow">Where this can grow</div><h3>发展前景：资产可以脱离一次生成，持续创造价值</h3></div><div class="two-col"><article class="panel"><h3>建筑与场景创作工作台</h3><p>将生成后的调参、拖拽、材质和光影操作做得可靠，逐步补齐批量替换、阵列和楼层复用。价值来自持续创作效率，需要通过实际任务验证。</p></article><article class="panel"><h3>面向应用的轻量资产供给</h3><p>向网页展示、互动叙事、教育和场景平台提供可编辑建筑。以版本化协议和引擎接入为基础，验证跨应用传递和重复使用的价值。</p></article><article class="panel"><h3>构件、风格与材质内容</h3><p>将已有材料与形态能力发展为可制作、预览、保存和分享的扩展包，让创作者积累可复用内容。交易和分发机制在真实复用形成后建设。</p></article><article class="panel"><h3>更开放的互动世界</h3><p>在建筑可编辑、操作可靠的基础上，探索漫游、互动设备、角色行为与持续变化的场景。长期价值依赖状态、权限、性能与内容治理能力逐步成熟。</p></article></div>
        <div class="subsection-heading"><div class="eyebrow">From built-in capability to creator tools</div><h3>让已有底层能力，逐步成为创作者可以使用的工具</h3><p>风格配置、材质运行时、光影参数和世界包提供了扩展基础。下一步的重点，是把这些能力整理成可制作、预览、保存和复用的内容流程。下表中的产品化工作仍属于规划。</p></div>
        <div class="table-wrap"><table><thead><tr><th scope="col">发展方向</th><th scope="col">已有基础</th><th scope="col">规划中的交付与验收重点</th></tr></thead><tbody>
          <tr><td data-label="发展方向">光影扩展包 <span class="label idea">规划</span></td><td data-label="已有基础">已有环境、时段、曝光、阴影与后期参数</td><td data-label="规划中的交付与验收重点">把调整结果保存为可命名、可版本化的方案；明确与世界包、当前设置的合并规则，支持导入后重现效果</td></tr>
          <tr><td data-label="发展方向">材质扩展包 <span class="label idea">规划</span></td><td data-label="已有基础">已有程序化材质、PBR 参数及独立渲染运行时</td><td data-label="规划中的交付与验收重点">将配方保存为可编辑资产；检查参数合法范围、蓝图引用和资源授权，使材质能在不同作品间复用</td></tr>
          <tr><td data-label="发展方向">扩展制作页面 <span class="label idea">规划</span></td><td data-label="已有基础">已有形态配置、材质与光影能力</td><td data-label="规划中的交付与验收重点">提供参数表单与独立预览，支持创建、保存、导入、导出与本地管理；制作过程不影响正在编辑的建筑</td></tr>
          <tr><td data-label="发展方向">世界导入与效果预览 <span class="label idea">规划</span></td><td data-label="已有基础">已有世界包解析、资源寻址与应用基础</td><td data-label="规划中的交付与验收重点">在相同机位下切换光影和材质方案；定义多包覆盖顺序、版本兼容与增量更新，便于比较和选择</td></tr>
          <tr><td data-label="发展方向">建筑编辑增强 <span class="label idea">规划</span></td><td data-label="已有基础">已有拖拽、参数调节、构件增删和结构化修改提案</td><td data-label="规划中的交付与验收重点">逐步补齐对齐、阵列、批量替换、楼层复制和多选联动；统一撤销与事务边界，让整体参数修改有一致的作用范围</td></tr>
          <tr><td data-label="发展方向">生成稳定性收敛 <span class="label idea">规划</span></td><td data-label="已有基础">已有生成记录、校验反馈与构件实现基础</td><td data-label="规划中的交付与验收重点">建立固定任务集和失败分类；优先用确定性算法接管宿主解析、立面分格和坐标推导，分别统计通过率、人工介入与交付成本</td></tr>
        </tbody></table></div>
        <div class="timeline">
          <article class="milestone"><span class="period">0–3 MONTHS</span><h3>验证可用与需求</h3><p>限定建筑范围，完善首次体验和保存重开。完成用户访谈与邀请试用，选择一个目标引擎验证单体模型导入和修改后重导入，记录制作、接入与返工总耗时。</p><div class="gate"><strong>进入下一阶段：</strong>关键任务可复现，3–5 个用户或项目实际付费；游戏试点明确资产验收结果与效率收益。</div></article>
          <article class="milestone"><span class="period">3–6 MONTHS</span><h3>验证持续付费</h3><p>按成本确定订阅额度，补齐稳定性与常用编辑操作。围绕重复需求沉淀构件、示例和模型交付规范，验证修改后再次接入、复用和客户续费。</p><div class="gate"><strong>进入下一阶段：</strong>观察到续费，订阅单位贡献为正，资产清理、支持和定制工作量保持可控。</div></article>
          <article class="milestone"><span class="period">6–12 MONTHS</span><h3>验证可复制交付</h3><p>完善 API 与版本兼容；在反复出现的接入需求支持下，评估制作期原生导入插件。运行时 SDK 依据客户需求、重建性能与完整资源成本另行验证。</p><div class="gate"><strong>继续扩展：</strong>形成可重复获客、续费和外部交付证据。游戏内蓝图重建不计入首期交付或收入承诺。</div></article>
        </div>
        <div class="statement"><p>长期方向：创作工具 → 内容社区 → 可交互场景 → 更开放的数字世界。</p><div class="small">互动建筑、角色生活与 Agent 自主演化是长期探索方向，需要角色行为、寻路、状态和权限等新能力。启动时间由前期验证决定，不纳入首期收入预测。</div></div>
      </section>

      <section class="chapter" id="finance">
        <div class="chapter-heading"><span class="chapter-num">10</span><div><div class="eyebrow">Unit economics · interactive assumptions</div><h2>先算清一位用户，再讨论规模</h2></div></div>
        <p class="lead">以下模型只测试个人订阅能否覆盖直接服务成本与固定运营费用。所有输入都是可修改的讨论假设，不代表实际成本、已售价格、客户数或收入预测。付费人数与价格须由 WILD 自身获客和试点推导；Pascal 的累计使用人数、Stars 与公开标价均不代入本模型。</p>
        <div class="calculator">
          <div class="calc-inputs"><h3>调整试算假设</h3>
            <div class="field"><label for="price">订阅单价（元 / 人 / 月）</label><input id="price" type="number" v-model.number="assumptions['price']" :aria-invalid="!validInput('price')" min="1" max="100000" step="1" inputmode="decimal"></div>
            <div class="field"><label for="users">付费用户数（人）</label><input id="users" type="number" v-model.number="assumptions['users']" :aria-invalid="!validInput('users')" min="0" max="10000000" step="1" inputmode="numeric"></div>
            <div class="field"><label for="model-cost">人均 AI 变动成本（元 / 月）</label><input id="model-cost" type="number" v-model.number="assumptions['model-cost']" :aria-invalid="!validInput('model-cost')" min="0" max="100000" step="1" inputmode="decimal"></div>
            <div class="field"><label for="service-cost">人均其他直接成本（元 / 月）</label><input id="service-cost" type="number" v-model.number="assumptions['service-cost']" :aria-invalid="!validInput('service-cost')" min="0" max="100000" step="1" inputmode="decimal"></div>
            <div class="field"><label for="fixed-cost">固定运营费用（元 / 月）</label><input id="fixed-cost" type="number" v-model.number="assumptions['fixed-cost']" :aria-invalid="!validInput('fixed-cost')" min="0" max="100000000" step="1000" inputmode="decimal"></div>
            <p class="calc-error" id="calc-error" role="status">{{ inputsValid ? '' : '请输入有效范围内的数字；人数须为整数。结果保留上一次有效试算。' }}</p><button class="reset" id="reset-calculator" type="button" @click="resetAssumptions">恢复初始假设 ↺</button>
          </div>
          <div class="calc-results" id="calc-results" aria-live="polite" aria-atomic="true">
            <p class="print-only" id="print-assumptions">{{ printAssumptions }}</p>
            <div class="result-grid"><div><div class="result-label">月度订阅收入 MRR</div><div class="result-value" id="mrr">{{ money(calculation.revenue) }}</div></div><div><div class="result-label">月度贡献 / 贡献率</div><div class="result-value" id="contribution">{{ money(calculation.contribution) }}</div><div class="small muted" id="margin-rate">贡献率 {{ calculation.rate.toFixed(1) }}%</div></div><div><div class="result-label">扣固定费用后的月结余</div><div class="result-value" :class="{ negative: calculation.balance < 0 }" id="balance">{{ money(calculation.balance) }}</div></div><div><div class="result-label">覆盖固定费用所需用户</div><div class="result-value" id="break-even">{{ calculation.breakEven === null ? '无法覆盖' : calculation.breakEven.toLocaleString('zh-CN') }}<span v-if="calculation.breakEven !== null" class="unit">人</span></div></div></div>
            <div class="calc-bar" aria-hidden="true"><span class="bar-model" id="bar-model" :style="{ width: percentages.model + '%' }"></span><span class="bar-service" id="bar-service" :style="{ width: percentages.service + '%' }"></span><span class="bar-margin" id="bar-margin" :style="{ width: percentages.margin + '%' }"></span></div>
            <div class="legend"><span><i style="background:#b76d4c"></i>AI 成本</span><span><i style="background:#b6bd9d"></i>其他直接成本</span><span><i style="background:#42694f"></i>贡献</span></div>
            <p class="calc-comment" id="calc-comment">{{ calculationComment }}</p>
          </div>
        </div>
        
        <div class="formula">月贡献 = 付费人数 ×（月费 − 人均 AI 成本 − 人均其他直接成本）<br>覆盖固定费用人数 = 固定费用 ÷ 单位月贡献，向上取整。单位贡献≤0 时，增加同类用户无法覆盖固定费用。<br>AI 成本应计入失败与重试；其他直接成本应覆盖支付、存储带宽与随用户增长的支持支出。免费试用的直接成本暂并入固定运营预算。未计税费、一次性投入、融资、渠道获客及团队/API/内容交易收入。</div>
        <div class="budget"><article class="panel"><h3>固定运营预算示例</h3><div class="budget-row"><span>核心研发与产品投入</span><b>¥30,000 / 月</b></div><div class="budget-row"><span>基础设施、工具与免费试用预算</span><b>¥5,000 / 月</b></div><div class="budget-row"><span>用户研究、内容与运营</span><b>¥10,000 / 月</b></div><div class="budget-row"><span>初始假设合计</span><b>¥45,000 / 月</b></div><p class="small gap-top">对应 12 个月固定运营费用 54 万元。这是规划示例，不是现有团队工资、融资需求或完整现金预算。</p></article><article class="panel"><h3>商业决策需要补齐的数据</h3><ul class="compact-list"><li>按粒度统计成功任务成本，计入失败、重试与退款。</li><li>记录新用户获得成本、免费用户消耗和人工支持时间。</li><li>按月付费批次统计续费，出现稳定留存后再估计生命周期价值。</li><li>将月度增长、回款、一次性投入和现金储备加入融资预算。</li></ul></article></div>
      </section>

      <section class="chapter" id="team">
        <div class="chapter-heading"><span class="chapter-num">11</span><div><div class="eyebrow">Team, capital & collaboration</div><h2>下一笔投入，要换来可验证的商业进展</h2></div></div>
        <div class="two-col"><article class="panel"><h3>团队现状与补位</h3><p>项目目前以独立开发为主，已经贯通蓝图语言、参数化引擎与网页工作台。后续需要根据产品和商业验证情况补充研发、设计及用户运营能力。</p><p>建议早期补齐两类能力：一类聚焦引擎、编辑体验与可靠交付；另一类聚焦创作者访谈、内容演示、渠道与试点转化。采用何种全职、兼职或合作方式，取决于现金与业务验证。</p></article><article class="funding"><h3>资金与融资口径</h3><p>拟围绕未来 6–12 个月的任务稳定性、付费试点、续费和外部接入里程碑配置资金。具体金额应由现金预算、团队安排与回款假设倒推。</p><p>融资金额与方式将结合团队计划、研发投入和现金预算确定。</p><span class="label">预算优先级：产品可靠性 → 真实试点 → 可复制收入</span></article></div>
        <div class="three-col gap-top"><article class="panel"><h3>寻找设计伙伴</h3><p>有实际建筑或三维场景任务，愿意提供过程反馈并按清晰范围试点的创作者、小型团队。</p></article><article class="panel"><h3>寻找应用合作方</h3><p>网页互动、数字展陈或场景平台团队，共同完成一个真正上线使用的接入案例。</p></article><article class="panel"><h3>寻找早期资金与资源</h3><p>认可可编辑资产方向，能提供研发周期、创作者渠道和商业化支持的早期合作伙伴。</p></article></div>
      </section>

      <section class="chapter" id="risks">
        <div class="chapter-heading"><span class="chapter-num">12</span><div><div class="eyebrow">Limitations & next steps</div><h2>能力边界：明确支持与交付范围</h2></div></div><div class="two-col gap-top"><article class="panel"><h3>自研 Agent 的效果与投入</h3><p>目前受研发资源限制，自研 Agent 在复杂设计、稳定执行和成品一致性上仍落后于成熟智能体。优先完善可计算的坐标、关系与校验，把模型能力集中在设计判断。</p></article><article class="panel"><h3>从单件编辑到生产效率</h3><p>工作台已有直接操作基础，批量对齐、阵列、楼层复制与参数层级仍需逐步补齐。完整工程图纸、结构计算和法规审查不在当前交付范围内。</p></article><article class="panel"><h3>实时画质与表达边界</h3><p>当前采用实时光栅化渲染。家具和植被仍有简化形体，程序纹理不等于真实几何起伏；全局照明、焦散与扫描级细节需要额外能力。小文件也不能直接保证低渲染成本。</p></article><article class="panel"><h3>产品化与生态仍需验证</h3><p>托管服务、计费、团队协作、外部兼容和内容授权需要完善。用户是否持续使用、是否愿意付费，以及支持成本能否控制，需要实际商业试点回答。</p></article></div>
        <div class="subsection-heading"><div class="eyebrow">Expression, reconstruction &amp; generation</div><h3>把表达能力与自动生成稳定性分开看</h3><p>WILD 蓝图能保存的细节、引擎能重建的形态，以及自研 Agent 能稳定完成的设计，是三个不同层面。成熟智能体、人工和脚本可以创作丰富蓝图；自研 Agent 的复杂任务仍在持续收敛，已有作品的渲染效果不能直接视为一次自动生成的成功率。</p></div>
        <div class="table-wrap"><table><thead><tr><th scope="col">自研 Agent 粒度</th><th scope="col">目标生成范围</th><th scope="col">当前边界与完善重点</th></tr></thead><tbody>
          <tr><td data-label="自研 Agent 粒度">低 · minimal</td><td data-label="目标生成范围">建筑主体、必要门窗、屋顶、楼梯与基础照明</td><td data-label="当前边界与完善重点">作为基础链路的优先交付范围，具体任务仍需校验、渲染和人工确认</td></tr>
          <tr><td data-label="自研 Agent 粒度">中 · simple</td><td data-label="目标生成范围">进一步加入阳台、露台、雨棚、栏杆和入口构件</td><td data-label="当前边界与完善重点">复杂体量中的附属构件宿主、位置和立面槽位仍可能冲突，尚需收敛稳定性</td></tr>
          <tr><td data-label="自研 Agent 粒度">高 · standard</td><td data-label="目标生成范围">开口分格、檐口、门廊、柱饰、屋面节点与分层材质</td><td data-label="当前边界与完善重点">设计字段与构件实现的对应关系需要继续完善，不能承诺所有细节组合都能稳定落地</td></tr>
          <tr><td data-label="自研 Agent 粒度">极高 · detailed</td><td data-label="目标生成范围">进一步表达室内空间、通行、家具陈设与室内外照明</td><td data-label="当前边界与完善重点">目标范围与实际支持能力分开判断；室内对象的坐标、归属与自动布局尚不足以作为稳定交付承诺</td></tr>
        </tbody></table></div>
        <div class="note"><strong>直接编辑已有基础。</strong>三轴拖拽、属性调参、场景树与构件库增删，以及对话触发的结构化修改提案，构成持续创作的现有入口。小修改可以直接操作；更复杂的批量、对齐和整体参数联动属于后续编辑增强规划。</div>
        <div class="subsection-heading"><div class="eyebrow">Explicit delivery boundaries</div><h3>当前暂不承诺的自动设计与交付类型</h3></div>
        <div class="table-wrap"><table><thead><tr><th scope="col">能力边界</th><th scope="col">当前说明</th></tr></thead><tbody>
          <tr><td data-label="能力边界">自动房间平面与功能布局</td><td data-label="当前说明">不承诺自动完成房间位置、功能分区和内部隔墙规划。蓝图能够表达室内构件与家具，不等于自研 Agent 已具备完整的房间布局能力</td></tr>
          <tr><td data-label="能力边界">自动场地语义规划</td><td data-label="当前说明">车库、后院、花园等空间的功能划分仍有缺口；庭院和景观构件可以在蓝图中表达，完整自动场地规划需要进一步建设</td></tr>
          <tr><td data-label="能力边界">专业二维平剖面图纸交付</td><td data-label="当前说明">前端已有可调高度的水平剖切预览，用于查看建筑内部；当前尚不提供带尺寸标注、图框与规范出图流程的专业二维平剖面图纸及施工交付</td></tr>
          <tr><td data-label="能力边界">任意有机造型与扫描级细节</td><td data-label="当前说明">任意复杂曲面、扫描网格和真实复杂人物超出当前参数化构件的通用覆盖；需要新增相应几何、资源与校验能力</td></tr>
        </tbody></table></div>
        <div class="subsection-heading"><div class="eyebrow">Risks &amp; validation</div><h3>把能力边界转化为明确的验证任务</h3></div>
        <div class="table-wrap"><table><thead><tr><th scope="col">关键风险</th><th scope="col">当前判断</th><th scope="col">控制与验证</th></tr></thead><tbody>
          <tr><td data-label="关键风险">复杂生成质量不稳定</td><td data-label="当前判断">精细渲染样例不等于复杂任务稳定自动交付</td><td data-label="控制与验证">限定支持范围；分别统计结构、空间、渲染和用户验收；记录人工介入</td></tr>
          <tr><td data-label="关键风险">需求与付费不足</td><td data-label="当前判断">同类产品的采用与定价提供参照，WILD 自身付费转化与跨周期留存尚未充分验证</td><td data-label="控制与验证">真实任务访谈、实际付款试点与跨周期续费；分别统计关注、使用、付费及人工支持成本</td></tr>
          <tr><td data-label="关键风险">同类产品与开源替代</td><td data-label="当前判断">浏览器编辑与 AI 接入已有开放方案，基础功能容易被替代</td><td data-label="控制与验证">聚焦轻量建筑资产的持续修改和实际接入，以目标任务的质量、耗时、完整成本及复用验证选择理由</td></tr>
          <tr><td data-label="关键风险">成本随用量上升</td><td data-label="当前判断">AI 调用、失败重试和支持会影响单位贡献</td><td data-label="控制与验证">按质量档设额度；监测成功交付成本；超额计费前验证价格接受度</td></tr>
          <tr><td data-label="关键风险">格式采用与兼容</td><td data-label="当前判断">自定义协议需要外部工具愿意接入</td><td data-label="控制与验证">版本化规范、兼容测试、迁移策略与首个真实外部应用</td></tr>
          <tr><td data-label="关键风险">游戏工具链接入成本</td><td data-label="当前判断">GLB 导出已实现，目标引擎中的材质、碰撞、LOD 和重导入仍待验收</td><td data-label="控制与验证">从制作期资产交付试点开始，由客户现有引擎渲染；将接入和返工计入总成本，再决定插件或 SDK 投入</td></tr>
          <tr><td data-label="关键风险">设备性能与资产总成本</td><td data-label="当前判断">蓝图小不代表展开后网格、贴图或运行成本小</td><td data-label="控制与验证">同时测文件体积、外部资源、首屏、内存与目标设备交互表现</td></tr>
          <tr><td data-label="关键风险">许可与内容权利</td><td data-label="当前判断">拟开放范围及第三方素材商业授权仍需核对</td><td data-label="控制与验证">上线前明确许可证、资源清单、作品授权及平台内容规则</td></tr>
          <tr><td data-label="关键风险">团队与范围失控</td><td data-label="当前判断">独立开发资源有限，远景容易分散投入</td><td data-label="控制与验证">先完成工作台与商业验证；社区交易、自主世界按里程碑启动</td></tr>
        </tbody></table></div>
        <div class="note"><strong>商业化前需要验证：</strong>负责人和公司主体、项目许可与资源授权、核心任务真实完成率、付费客户与留存、按任务统计的成本、月度现金预算及融资目标。相关指标将随试点与产品进展持续完善。</div>
        <div class="endline">从一份可编辑的蓝图，<br>长出更多可以被创造的世界。</div>
        <div class="footer"><span>WILD · 旷野 · 商业计划书</span><span>公开竞品资料核查：2026-10-28 / 产品持续开发中</span></div>
      </section>
    </main>
  </div>
<dialog class="image-viewer" id="image-viewer" ref="imageViewer" @click="closeOnBackdrop" @close="selectedImage = null" aria-label="完整渲染图"><button class="viewer-close" type="button" @click="imageViewer?.close()" aria-label="关闭大图">关闭 ×</button><figure><img id="viewer-image" :src="selectedImage?.src" :alt="selectedImage?.alt || ''"><figcaption id="viewer-caption">{{ selectedImage?.alt }}</figcaption></figure></dialog>
</div>

</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, shallowRef, watch } from 'vue'
import { calculateSubscription, money, type SubscriptionAssumptions } from './calculation'
import { RouterLink } from 'vue-router'

const projects = [
  {
    "id": "shiomi",
    "name": "汐見駅 · 海边暮色",
    "type": "海边交通微缩场景",
    "story": "横向站房、抬高的站台、短电车与海堤，组成层次清晰的海边一角。黄昏光照、动态海水与可推拉车门，在同一份轻量蓝图中呈现。",
    "size": "46.2 KiB",
    "imageWidth": 1440,
    "imageHeight": 1080,
    "images": [
      { "src": "/business-plan/shiomi-01.png", "alt": "汐見駅 · 站房、短电车与海岸全景" },
      { "src": "/business-plan/shiomi-02.png", "alt": "汐見駅 · 候车站台与电车另一侧完整视角" }
    ]
  },
  {
    "id": "tomokoji",
    "name": "灯巷らーめん · 雨夜街角",
    "type": "日式餐饮微缩场景",
    "story": "红灯笼与暖帘迎向雨夜，橱窗内是 L 形吧台、圆凳和拉面陈设。窄巷、贩卖机、踏板车与街角设施，把店铺延伸成一个完整的小场景。",
    "size": "40.1 KiB",
    "imageWidth": 1440,
    "imageHeight": 1080,
    "images": [
      { "src": "/business-plan/tomokoji-01.png", "alt": "灯巷拉面屋 · 店面、暖帘与转角街道" },
      { "src": "/business-plan/tomokoji-02.png", "alt": "灯巷拉面屋 · 贩卖机、窄巷与店铺另一侧" }
    ]
  },
  {
    "id": "yukiakari",
    "name": "雪灯ベーカリー · 雪夜面包店",
    "type": "日式雪夜微缩场景",
    "story": "覆雪山墙、红白遮棚与温暖橱窗，围绕一间有烤炉、面包架和咖啡台的小店展开。门扇带动把手与护板开合，细节延续到街角和后巷。",
    "size": "63.0 KiB",
    "imageWidth": 1440,
    "imageHeight": 1080,
    "images": [
      { "src": "/business-plan/yukiakari-01.png", "alt": "雪灯面包店 · 覆雪屋顶、暖色橱窗与街角" },
      { "src": "/business-plan/yukiakari-02.png", "alt": "雪灯面包店 · 松树、自行车与店铺另一侧完整视角" }
    ]
  },
  {
    "id": "amayadori",
    "name": "雨宿り · 雨夜便利店街角",
    "type": "日式雨夜微缩场景",
    "story": "便利店、玻璃橱窗、街角设施与积水反光，组成正方形底座上的雨夜微缩景观。画面为配套三渲二预览的真实截图。",
    "size": "117.4 KiB",
    "imageWidth": 1440,
    "imageHeight": 1080,
    "images": [
      {
        "src": "/business-plan/amayadori-01.png",
        "alt": "雨宿り · 雨夜便利店街角 · 店面、室内陈列与贩卖机"
      },
      {
        "src": "/business-plan/amayadori-02.png",
        "alt": "雨宿り · 雨夜便利店街角 · 转角街道与完整底座"
      }
    ]
  },
  {
    "id": "curated-linting",
    "name": "林庭石光馆",
    "type": "庭院展馆",
    "story": "庭院、连廊与石材界面共同组织建筑空间，展示较复杂的公共空间和构件细节。",
    "size": "780.1 KiB",
    "images": [
      {
        "src": "/business-plan/curated-linting-02.jpg",
        "alt": "林庭石光馆 · 建筑全貌"
      },
      {
        "src": "/business-plan/curated-linting-01.jpg",
        "alt": "林庭石光馆 · 另一侧视角"
      }
    ]
  },
  {
    "id": "curated-meiting",
    "name": "玫庭庄园 · 欧式别墅",
    "type": "欧式住宅",
    "story": "通过坡屋顶、门窗、柱廊与装饰层次，表达具有细节的欧式住宅。",
    "size": "518.9 KiB",
    "images": [
      {
        "src": "/business-plan/curated-meiting-02.jpg",
        "alt": "玫庭庄园 · 欧式别墅 · 建筑全貌"
      },
      {
        "src": "/business-plan/curated-meiting-01.jpg",
        "alt": "玫庭庄园 · 欧式别墅 · 另一侧视角"
      }
    ]
  },
  {
    "id": "curated-qiguang",
    "name": "栖光别墅 · 叠院露台住宅",
    "type": "叠院露台住宅",
    "story": "退台、露台与多层空间组合，展示住宅体量与院落关系的参数化表达。",
    "size": "149.0 KiB",
    "images": [
      {
        "src": "/business-plan/curated-qiguang-02.jpg",
        "alt": "栖光别墅 · 叠院露台住宅 · 建筑全貌"
      },
      {
        "src": "/business-plan/curated-qiguang-01.jpg",
        "alt": "栖光别墅 · 叠院露台住宅 · 另一侧视角"
      }
    ]
  },
  {
    "id": "curated-tinglan",
    "name": "听澜合院 · 新中式别墅",
    "type": "新中式合院",
    "story": "以合院、坡顶和木作细节表达新中式居住空间。",
    "size": "448.5 KiB",
    "images": [
      {
        "src": "/business-plan/curated-tinglan-02.jpg",
        "alt": "听澜合院 · 新中式别墅 · 建筑全貌"
      },
      {
        "src": "/business-plan/curated-tinglan-01.jpg",
        "alt": "听澜合院 · 新中式别墅 · 另一侧视角"
      }
    ]
  },
  {
    "id": "curated-tingguang",
    "name": "庭光别墅 · 双层庭院住宅",
    "type": "双层庭院住宅",
    "story": "围绕庭院组织双层居住体量，展示建筑形态与开口、材质的组合。",
    "size": "80.7 KiB",
    "images": [
      {
        "src": "/business-plan/curated-tingguang-02.jpg",
        "alt": "庭光别墅 · 双层庭院住宅 · 建筑全貌"
      },
      {
        "src": "/business-plan/curated-tingguang-01.jpg",
        "alt": "庭光别墅 · 双层庭院住宅 · 另一侧视角"
      }
    ]
  },
  {
    "id": "curated-yanlu",
    "name": "砚麓别墅",
    "type": "别墅与景观",
    "story": "以真实蓝图中的建筑体量和细部表达，展示持续迭代的建筑创作成果。",
    "size": "297.6 KiB",
    "images": [
      {
        "src": "/business-plan/curated-yanlu-02.jpg",
        "alt": "砚麓别墅 · 建筑全貌"
      },
      {
        "src": "/business-plan/curated-yanlu-01.jpg",
        "alt": "砚麓别墅 · 另一侧视角"
      }
    ]
  },
  {
    "id": "curated-forest",
    "name": "Forest Cafe",
    "type": "商业建筑",
    "story": "以丰富的商业空间、界面和构件细节，展示 WILD 在住宅之外的应用。",
    "size": "833.6 KiB",
    "images": [
      {
        "src": "/business-plan/curated-forest-02.jpg",
        "alt": "Forest Cafe · 建筑全貌"
      },
      {
        "src": "/business-plan/curated-forest-01.jpg",
        "alt": "Forest Cafe · 另一侧视角"
      }
    ]
  },
  {
    "id": "lanshi",
    "name": "岚石光庭",
    "type": "交互材质别墅",
    "story": "L 形体量与水庭组织居住空间，木格栅、洞石、玻璃与室内陈设共同参与表达。",
    "size": "48.6 KiB",
    "images": [
      {
        "src": "/business-plan/lanshi-01.jpg",
        "alt": "岚石光庭 · 建筑全貌"
      },
      {
        "src": "/business-plan/lanshi-02.jpg",
        "alt": "岚石光庭 · 另一侧视角"
      }
    ]
  },
  {
    "id": "songyu",
    "name": "松雨回廊",
    "type": "新中式合院",
    "story": "围合院落、屋面层次和回廊关系，体现蓝图对不同空间组织与建筑语言的承载。",
    "size": "39.4 KiB",
    "images": [
      {
        "src": "/business-plan/songyu-01.jpg",
        "alt": "松雨回廊 · 建筑全貌"
      },
      {
        "src": "/business-plan/songyu-02.jpg",
        "alt": "松雨回廊 · 另一侧视角"
      }
    ]
  },
  {
    "id": "qipo",
    "name": "栖坡陶院",
    "type": "地中海坡顶",
    "story": "陶土坡顶、拱廊、阳台与庭院，展示同一引擎下的风格变化与参数化复用。",
    "size": "52.8 KiB",
    "images": [
      {
        "src": "/business-plan/qipo-01.jpg",
        "alt": "栖坡陶院 · 建筑全貌"
      },
      {
        "src": "/business-plan/qipo-02.jpg",
        "alt": "栖坡陶院 · 另一侧视角"
      }
    ]
  }
]
const interiors = [
  {
    "src": "/business-plan/lanshi-04-interior.jpg",
    "alt": "岚石光庭 · 室内材质与空间"
  },
  {
    "src": "/business-plan/chengyu-04-interior.jpg",
    "alt": "澄屿叠院 · 室内材质与空间"
  },
  {
    "src": "/business-plan/qipo-04-interior.jpg",
    "alt": "栖坡陶院 · 室内材质与空间"
  }
]

const pageRoot = ref<HTMLElement>()
const imageViewer = ref<HTMLDialogElement>()
const selectedImage = ref<{ src: string; alt: string } | null>(null)
const preparingPdf = ref(false)
const pdfError = ref('')
async function exportPdf() {
  if (preparingPdf.value) return
  preparingPdf.value = true
  pdfError.value = ''
  try {
    imageViewer.value?.close()
    const images = Array.from(pageRoot.value!.querySelectorAll<HTMLImageElement>('img[src]'))
    await Promise.all([document.fonts.ready, ...images.map(image => {
      image.loading = 'eager'
      return image.decode()
    })])
    await nextTick()
    if (!pageRoot.value) return
    window.print()
  } catch {
    pdfError.value = '图片或打印准备失败，请刷新页面后重试。'
  } finally {
    preparingPdf.value = false
  }
}
const defaults: SubscriptionAssumptions = { price: 99, users: 300, 'model-cost': 18, 'service-cost': 8, 'fixed-cost': 45000 }
const assumptions = reactive({ ...defaults })
const lastValid = shallowRef({ ...defaults })
const limits: Record<string, [number, number, number]> = { price: [1, 100000, 1], users: [0, 10000000, 1], 'model-cost': [0, 100000, 1], 'service-cost': [0, 100000, 1], 'fixed-cost': [0, 100000000, 1000] }
function validInput(key: string) {
  const value = assumptions[key as keyof SubscriptionAssumptions]
  const [min, max, step] = limits[key]!
  return typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max && Number.isInteger((value - min) / step)
}
const inputsValid = computed(() => Object.keys(defaults).every(validInput))
watch(assumptions, () => { if (inputsValid.value) lastValid.value = { ...assumptions } }, { deep: true })
const calculation = computed(() => calculateSubscription(lastValid.value))
const percentages = computed(() => ({ model: lastValid.value['model-cost'] / calculation.value.scale * 100, service: lastValid.value['service-cost'] / calculation.value.scale * 100, margin: Math.max(calculation.value.unit, 0) / calculation.value.scale * 100 }))
const calculationComment = computed(() => '在当前假设下，每位付费用户月贡献 ' + calculation.value.unit.toLocaleString('zh-CN') + ' 元；' + (calculation.value.breakEven === null ? '同类用户的增长无法覆盖固定运营费用，需要提高单价或降低成本。' : '约需 ' + calculation.value.breakEven.toLocaleString('zh-CN') + ' 位同等用量的付费用户覆盖月固定费用。'))
const printAssumptions = computed(() => '本次试算输入：单价 ' + lastValid.value.price + ' 元；' + lastValid.value.users + ' 位付费用户；人均 AI 成本 ' + lastValid.value['model-cost'] + ' 元；其他直接成本 ' + lastValid.value['service-cost'] + ' 元；固定运营费用 ' + lastValid.value['fixed-cost'].toLocaleString('zh-CN') + ' 元 / 月。')
function resetAssumptions() { Object.assign(assumptions, defaults) }
async function openImage(event: MouseEvent) {
  const image = (event.currentTarget as HTMLElement).querySelector('img')
  if (!image) return
  await showImage({ src: image.src, alt: image.alt })
}
async function showImage(image: { src: string; alt: string }) {
  selectedImage.value = image
  await nextTick()
  imageViewer.value?.showModal()
}
function closeOnBackdrop(event: MouseEvent) { if (event.target === imageViewer.value) imageViewer.value?.close() }
const activeChapter = ref('#summary')
const readingProgress = ref(0)
let readingFrame = 0
function updateReading() {
  const root = pageRoot.value
  if (!root) return
  const total = root.scrollHeight - root.clientHeight
  readingProgress.value = total > 0 ? Math.min(100, Math.max(0, root.scrollTop / total * 100)) : 0
  const top = root.getBoundingClientRect().top
  for (const section of root.querySelectorAll<HTMLElement>('.chapter')) {
    if (section.getBoundingClientRect().top - top <= 180) activeChapter.value = '#' + section.id
  }
}
function scheduleReading() { cancelAnimationFrame(readingFrame); readingFrame = requestAnimationFrame(updateReading) }
onMounted(() => {
  pageRoot.value?.addEventListener('load', scheduleReading, true)
  window.addEventListener('resize', scheduleReading)
  updateReading()
})
onBeforeUnmount(() => {
  cancelAnimationFrame(readingFrame)
  pageRoot.value?.removeEventListener('load', scheduleReading, true)
  window.removeEventListener('resize', scheduleReading)
  imageViewer.value?.close()
})
</script>

<style scoped>

    .business-plan-page{--paper:var(--studio-bg);--on-accent:var(--studio-bg);--white:var(--studio-surface);--ink:var(--studio-text);--muted:var(--studio-muted);--green:var(--studio-accent);--soft:var(--studio-hover);--line:var(--studio-border);--orange:var(--studio-orange);--serif:"Noto Serif SC","Source Han Serif SC","Songti SC","SimSun",serif;--sans:"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
    *{box-sizing:border-box}.business-plan-page{scroll-behavior:smooth;scroll-padding-top:88px}.business-plan-page{margin:0;background:var(--paper);color:var(--ink);font:15px/1.85 var(--sans);-webkit-font-smoothing:antialiased}a{color:inherit;text-underline-offset:4px}button,input{font:inherit}button,a,input{touch-action:manipulation}button{cursor:pointer}button:focus-visible,a:focus-visible,input:focus-visible{outline:3px solid var(--orange);outline-offset:4px}img{display:block;max-width:100%}figure,p,ul,ol{margin:0}h1,h2,h3,h4{margin:0;line-height:1.4}h2{font-size:clamp(25px,3vw,37px);letter-spacing:-1px;font-weight:650}h3{font-size:19px;font-weight:650}h4{font-size:16px}p+p{margin-top:14px}strong{font-weight:650}small,.small{font-size:12px;line-height:1.8}.muted{color:var(--muted)}.mono{font-family:Consolas,"SFMono-Regular",monospace;font-variant-numeric:tabular-nums}.eyebrow{font-size:11px;letter-spacing:2.5px;text-transform:uppercase;font-weight:700;color:var(--green)}.label{display:inline-block;font-size:11px;line-height:1.5;padding:5px 9px;border:1px solid var(--line);border-radius:3px;vertical-align:middle;letter-spacing:.4px}.label.proof{background:var(--soft);border-color:var(--soft);color:var(--green)}.label.idea{color:var(--orange);background:var(--studio-warm);border-color:var(--studio-warm)}.nowrap{white-space:nowrap}
    .skip{position:fixed;left:20px;top:-70px;z-index:99;background:var(--green);color:var(--on-accent);padding:10px 20px}.skip:focus{top:10px}.topbar{height:70px;position:sticky;top:0;z-index:20;background:var(--paper);border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;padding:0 38px;gap:20px}.brand{text-decoration:none;display:flex;gap:12px;align-items:center}.brand-mark{width:33px;height:33px;background:var(--green);color:var(--paper);display:grid;place-items:center;font-family:var(--serif);font-size:26px;line-height:1}.brand-name{font-size:19px;letter-spacing:-.8px;font-weight:750}.top-meta{font-size:11px;letter-spacing:1.5px;color:var(--muted)}.top-actions{display:flex;align-items:center;gap:20px}.home-link{border:1px solid var(--studio-accent-border);background:transparent;padding:7px 13px;border-radius:3px;font-size:12px;color:var(--green)}.reading-progress{position:absolute;bottom:-1px;left:0;width:0;height:2px;background:var(--orange)}
    .layout{max-width:1600px;display:grid;grid-template-columns:225px minmax(0,1fr);margin:auto}.sidebar{position:sticky;top:70px;align-self:start;height:calc(100vh - 70px);padding:35px 20px 24px 30px;border-right:1px solid var(--line);display:flex;flex-direction:column;overflow:auto}.nav-title{font-size:10px;letter-spacing:2px;color:var(--muted);margin-bottom:16px}.sidebar nav{display:grid;gap:3px}.sidebar nav a{display:flex;gap:13px;padding:7px 10px;border-radius:3px;text-decoration:none;font-size:12px;color:var(--muted);line-height:1.6}.sidebar nav a span{color:var(--muted);font-size:10px;padding-top:2px}.sidebar nav a:hover,.sidebar nav a[aria-current="location"]{color:var(--green);background:var(--soft)}.sidebar nav a[aria-current="location"] span{color:var(--orange)}.sidebar-foot{margin-top:auto;padding-top:30px;font-size:10px;color:var(--muted);line-height:1.9}.sidebar-foot b{display:block;font-size:12px;color:var(--green);margin:4px 0}.main{min-width:0;padding:0 56px}.hero{padding:51px 0 40px}.hero-meta{display:flex;justify-content:space-between;gap:15px;align-items:center;margin-bottom:32px}.hero-grid{display:grid;grid-template-columns:1fr 1.15fr;gap:32px;align-items:center}.hero h1{font-family:var(--serif);font-size:clamp(39px,4.3vw,64px);font-weight:600;line-height:1.35;letter-spacing:-2px}.hero h1 em{font-style:normal;color:var(--green)}.hero-copy{font-size:14px;line-height:1.95;color:var(--muted);margin:23px 0;max-width:460px}.hero-links{display:flex;align-items:center;gap:22px;flex-wrap:wrap}.primary-link{background:var(--green);color:var(--on-accent);text-decoration:none;padding:10px 18px;font-size:12px;border-radius:2px}.text-link{font-size:12px;color:var(--green)}.hero-visual{position:relative;padding:14px 0 0 14px}.hero-visual:before{content:"";position:absolute;inset:0 15px 38px 0;border:1px solid var(--line);z-index:-1}.hero-visual img{display:block;width:100%;height:auto;aspect-ratio:auto;object-fit:contain;background:var(--soft)}.hero-visual figcaption{padding:10px 0;font-size:10px;color:var(--muted);display:flex;justify-content:space-between;gap:8px}.hero-note{padding:17px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line);display:grid;grid-template-columns:1.2fr 1fr 1fr;gap:20px;margin-top:34px;font-size:12px;color:var(--muted)}.hero-note b{display:block;color:var(--ink);font-size:15px;margin-bottom:2px}.hero-note>div+div{border-left:1px solid var(--line);padding-left:20px}.edition{font-size:11px;color:var(--muted);text-align:right;line-height:1.7}
    .chapter{padding:55px 0;border-top:1px solid var(--line);scroll-margin-top:20px}.chapter-heading{display:grid;grid-template-columns:38px 1fr;gap:17px;align-items:start;margin-bottom:28px}.chapter-num{font:12px/1.7 Consolas,monospace;color:var(--orange);padding-top:6px}.chapter-heading .eyebrow{margin-bottom:8px}.lead{font-size:16px;line-height:1.95;color:var(--muted);max-width:850px;margin:0 0 25px}.two-col{display:grid;grid-template-columns:1fr 1fr;gap:28px}.three-col{display:grid;grid-template-columns:repeat(3,1fr);gap:20px}.panel{background:var(--white);padding:24px;border:1px solid var(--line);border-radius:3px}.panel h3{margin-bottom:12px}.panel p{font-size:13px;color:var(--muted)}.panel .eyebrow{margin-bottom:13px}.statement{background:var(--green);color:var(--paper);padding:30px 34px;margin:25px 0;border-radius:3px}.statement p{font-family:var(--serif);font-size:clamp(20px,2.3vw,28px);line-height:1.8}.statement .small{color:var(--on-accent);font-family:var(--sans);font-size:12px;margin-top:11px}.compact-list{padding-left:19px;font-size:13px;color:var(--muted);line-height:1.95}.compact-list li+li{margin-top:7px}.note{border-left:3px solid var(--studio-accent-border);background:var(--soft);padding:15px 20px;font-size:12px;color:var(--muted);margin-top:20px}.note.warm{border-color:var(--orange);background:var(--studio-warm);color:var(--orange)}.section-label{display:flex;gap:10px;align-items:center;justify-content:space-between;margin-bottom:17px;flex-wrap:wrap}.gap-top{margin-top:24px}.step-list{display:grid;grid-template-columns:repeat(4,1fr);gap:0;border:1px solid var(--line);background:var(--white);margin:25px 0}.step{padding:20px;position:relative}.step+.step{border-left:1px solid var(--line)}.step .mono{color:var(--orange);font-size:11px}.step h4{margin:10px 0}.step p{font-size:12px;color:var(--muted)}.step:not(:last-child):after{content:"→";position:absolute;right:-9px;top:18px;z-index:1;background:var(--white);color:var(--muted);padding:0 2px}.table-wrap{width:100%;overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:12px;line-height:1.85;text-align:left}th{color:var(--green);font-weight:650;background:var(--soft);padding:12px 14px;white-space:nowrap}td{padding:14px;border-bottom:1px solid var(--line);vertical-align:top}td:first-child{font-weight:600;color:var(--ink)}td{color:var(--muted)}.table-wrap table{min-width:600px}.table-wrap.narrow table{min-width:480px}.decision{margin-top:20px;font-size:13px;color:var(--green)}.asset-metric{display:flex;align-items:baseline;gap:12px;margin-top:22px;padding:20px 0;border-top:1px solid var(--line);flex-wrap:wrap}.asset-metric strong{font-size:35px;font-family:Consolas,monospace;letter-spacing:-1.5px;color:var(--green)}.asset-metric span{font-size:12px;color:var(--muted)}.price{font:34px/1.5 Consolas,monospace;color:var(--green);letter-spacing:-1.5px;margin:10px 0}.price small{font-family:var(--sans);letter-spacing:0;font-size:12px}.price-card{position:relative}.price-card.featured{border-top:3px solid var(--green)}.price-card ul{min-height:116px;margin-top:16px}.price-card .label{margin-bottom:14px}.flowline{display:flex;align-items:center;gap:12px;flex-wrap:wrap;background:var(--soft);padding:21px 24px;margin-top:22px;font-size:12px;color:var(--green)}.flowline .arrow{color:var(--muted)}.timeline{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;margin-top:24px}.milestone{border-top:2px solid var(--studio-accent-border);padding-top:20px}.milestone .period{font:13px Consolas,monospace;color:var(--orange)}.milestone h3{margin:10px 0 14px}.milestone p{font-size:13px;color:var(--muted)}.milestone .gate{margin-top:17px;background:var(--soft);padding:12px;font-size:12px;color:var(--green)}
    .calculator{display:grid;grid-template-columns:.9fr 1.1fr;border:1px solid var(--line);background:var(--white);margin-top:24px}.calc-inputs{padding:26px 28px;border-right:1px solid var(--line)}.calc-inputs h3{margin-bottom:18px}.field{display:grid;grid-template-columns:1fr 116px;gap:16px;align-items:center;margin:15px 0}.field label{font-size:12px;color:var(--muted)}.field input{width:100%;min-width:0;padding:7px 9px;background:var(--paper);border:1px solid var(--line);color:var(--green);border-radius:2px;font-family:Consolas,monospace}.reset{background:transparent;color:var(--green);font-size:12px;border:0;border-bottom:1px solid var(--studio-accent-border);padding:2px 0;margin-top:9px}.calc-results{padding:26px 28px;display:flex;flex-direction:column}.result-grid{display:grid;grid-template-columns:1fr 1fr;gap:22px 20px}.result-label{font-size:11px;color:var(--muted)}.result-value{font-family:Consolas,monospace;font-size:29px;line-height:1.6;color:var(--green);letter-spacing:-1px}.result-value.negative{color:var(--studio-danger)}.unit{font:11px var(--sans);letter-spacing:0;margin-left:5px}.calc-bar{display:flex;min-height:12px;background:var(--soft);margin-top:23px}.calc-bar span{display:block}.bar-model{background:#b76d4c;width:18.18%}.bar-service{background:#b6bd9d;width:8.08%}.bar-margin{background:#42694f;width:73.74%}.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:10px;color:var(--muted);margin:9px 0 14px}.legend i{display:inline-block;width:7px;height:7px;margin-right:5px}.calc-comment{font-size:12px;color:var(--muted);border-top:1px solid var(--line);padding-top:16px;margin-top:auto}.formula{font-size:11px;color:var(--muted);background:var(--soft);padding:15px 20px;margin-top:16px;line-height:2}.calc-error{color:var(--studio-danger);min-height:20px;font-size:11px}.budget{display:grid;grid-template-columns:1fr 1fr;gap:22px;margin-top:24px}.budget-row{display:flex;justify-content:space-between;gap:20px;padding:9px 0;border-bottom:1px solid var(--line);font-size:12px}.budget-row b{color:var(--green);white-space:nowrap}.funding{padding:28px;background:var(--green);color:var(--paper)}.funding h3{margin-bottom:13px}.funding p{font-size:13px;color:var(--on-accent)}.funding .label{color:var(--on-accent);border-color:var(--on-accent);margin-top:17px}.endline{font-family:var(--serif);font-size:clamp(26px,3.5vw,44px);color:var(--green);padding:35px 0 28px;line-height:1.6}.footer{display:flex;justify-content:space-between;gap:20px;border-top:1px solid var(--line);padding:19px 0 30px;font-size:10px;color:var(--muted)}.print-only{display:none}
    @media(min-width:1550px){.main{padding:0 75px}.hero h1{font-size:66px}.hero{padding-top:64px}.hero-grid{gap:45px}}
    @media(max-width:1150px){.layout{grid-template-columns:190px minmax(0,1fr)}.main{padding:0 30px}.sidebar{padding-left:16px}.hero-grid{grid-template-columns:1fr;gap:26px}.hero h1{font-size:48px}.hero h1 br:nth-of-type(2){display:none}.hero-visual{max-width:700px}.hero-visual img{display:block;width:100%;height:auto;aspect-ratio:auto;object-fit:contain;background:var(--soft)}.three-col,.timeline{gap:13px}.panel{padding:20px}.hero-note{grid-template-columns:1fr 1fr 1fr}.top-meta{display:none}}
    @media(max-width:820px){.topbar{height:62px;padding:0 20px}.layout{display:block}.sidebar{position:sticky;top:62px;height:auto;padding:0;background:var(--paper);z-index:15;border-right:0;border-bottom:1px solid var(--line);overflow:visible}.nav-title,.sidebar-foot{display:none}.sidebar nav{display:flex;overflow-x:auto;gap:2px;padding:7px 13px;scrollbar-width:thin}.sidebar nav a{white-space:nowrap;padding:6px 10px;font-size:11px}.sidebar nav a span{display:none}.main{padding:0 24px}.hero{padding-top:30px}.hero-meta{margin-bottom:25px}.hero h1{font-size:43px}.hero-grid{grid-template-columns:1fr;gap:25px}.hero-visual{padding-top:10px}.hero-visual img{display:block;width:100%;height:auto;aspect-ratio:auto;object-fit:contain;background:var(--soft)}.hero-copy{font-size:12px}.hero-links{gap:15px}.hero-visual figcaption{display:block}.hero-visual figcaption span{display:block}.chapter{padding:40px 0}.chapter-heading{grid-template-columns:25px 1fr;gap:10px}.hero-note{gap:12px}.hero-note>div+div{padding-left:12px}.hero-note b{font-size:13px}.hero-note{font-size:11px}.three-col{grid-template-columns:1fr}.price-card ul{min-height:0}.step-list{grid-template-columns:1fr 1fr}.step:nth-child(3){border-left:0;border-top:1px solid var(--line)}.step:nth-child(4){border-top:1px solid var(--line)}.step:nth-child(2):after{display:none}.calculator{grid-template-columns:1fr}.calc-inputs{border-right:0;border-bottom:1px solid var(--line)}.timeline{grid-template-columns:1fr;gap:25px}.chapter{scroll-margin-top:80px}}
    @media(max-width:560px){.business-plan-page{font-size:14px}.topbar{padding:0 16px}.brand-name{font-size:17px}.top-actions{gap:8px}.top-actions .label{display:none}.main{padding:0 19px}.hero-meta .eyebrow{font-size:9px;letter-spacing:1px}.hero-grid{grid-template-columns:1fr}.hero h1{font-size:43px}.hero h1 br:nth-of-type(2){display:block}.hero-copy{font-size:13px;max-width:100%}.hero-visual img{display:block;width:100%;height:auto;aspect-ratio:auto;object-fit:contain;background:var(--soft)}.hero-visual figcaption{display:flex}.hero-meta{align-items:start}.hero-note{grid-template-columns:1fr;gap:13px}.hero-note>div+div{border-left:0;padding:11px 0 0;border-top:1px solid var(--line)}.hero-note b{display:inline;margin-right:12px}.two-col,.budget{grid-template-columns:1fr}.statement{padding:23px}.lead{font-size:14px}.chapter-heading{margin-bottom:23px}.field{grid-template-columns:1fr 104px}.calc-inputs,.calc-results{padding:21px}.result-value{font-size:25px}.result-grid{gap:18px 12px}.step{padding:17px}.step p{font-size:11px}.footer{display:block}.footer span{display:block;margin-top:4px}.endline{padding-top:25px}.edition{font-size:10px}.asset-metric strong{font-size:29px}}
    @media(prefers-reduced-motion:reduce){.business-plan-page{scroll-behavior:auto}}
    @page{size:A4;margin:16mm 14mm}
    @media print{.business-plan-page{scroll-behavior:auto}.business-plan-page{background:white;font-size:10pt;line-height:1.75;color:#172b20;-webkit-print-color-adjust:exact;print-color-adjust:exact}.topbar,.sidebar,.hero-links,.home-link,.reset,.calc-inputs,.calc-bar,.legend,.reading-progress,.skip{display:none!important}.layout{display:block;max-width:none}.main{padding:0}.hero{padding:0 0 20px}.hero-meta{margin-bottom:20px}.hero-grid{grid-template-columns:.9fr 1.1fr;gap:20px}.hero h1{font-size:28pt}.hero h1 br:nth-of-type(2){display:block}.hero-copy{font-size:9pt}.hero-visual img{display:block;width:100%;height:auto;aspect-ratio:auto;object-fit:contain;background:var(--soft)}.hero-note{margin-top:20px}.chapter{padding:25px 0;scroll-margin-top:0}.chapter-heading{margin-bottom:18px}h2{font-size:21pt}h3{font-size:13pt}h1,h2,h3,h4,.chapter-heading{break-after:avoid}.panel,figure,.step,.milestone,.budget,.statement,.calculator{break-inside:avoid}.three-col{grid-template-columns:repeat(3,1fr)}.two-col,.budget{grid-template-columns:1fr 1fr}.timeline{grid-template-columns:repeat(3,1fr)}.step-list{grid-template-columns:repeat(4,1fr)}.step:nth-child(3){border-left:1px solid var(--line);border-top:0}.step:nth-child(4){border-top:0}.panel{padding:15px}.panel p,.compact-list,.milestone p,td,.lead{font-size:9pt}.table-wrap{overflow:visible}.table-wrap table,.table-wrap.narrow table{min-width:0;font-size:8pt}thead{display:table-header-group}tr{break-inside:avoid}td,th{padding:9px}.lead{margin-bottom:17px}.calculator{display:block}.calc-results{padding:20px}.result-grid{grid-template-columns:repeat(4,1fr)}.result-value{font-size:19pt}.print-only{display:block;font-size:8pt;color:var(--muted);margin-bottom:10px}.footer{font-size:8pt}.endline{font-size:26pt}.note,.formula{font-size:8pt}.chapter a{color:inherit}.hero-visual figcaption{font-size:7pt}}

    .brand-cn{font-size:12px;letter-spacing:2px;font-weight:500;margin-left:5px}.brand-story{margin:0 0 25px;padding:26px 28px;border:1px solid var(--line);background:linear-gradient(115deg,var(--soft),var(--white))}.brand-story h3{margin:9px 0 10px;font-family:var(--serif);font-size:24px;letter-spacing:2px}.brand-story>p{font-size:13px;color:var(--muted)}.brand-letters{display:grid;grid-template-columns:repeat(4,1fr);margin-top:22px;border-top:1px solid var(--line);padding-top:16px;gap:14px}.brand-letters b{font:34px/1.3 var(--serif);color:var(--green);display:block}.brand-letters span{font-size:11px;color:var(--muted)}.brand-letters strong{font-weight:650;color:var(--green);margin-right:3px}.brand-story .brand-footnote{font-size:10px;margin-top:15px;color:var(--muted)}@media(max-width:560px){.brand-story{padding:22px}.brand-story .eyebrow{font-size:9px;letter-spacing:1px}.brand-letters{grid-template-columns:1fr 1fr}.brand-cn{font-size:10px}}@media print{.brand-story{break-inside:avoid;padding:18px}.brand-letters{grid-template-columns:repeat(4,1fr)}.brand-story>p{font-size:9pt}}
  
.business-plan-page{height:100dvh;overflow-y:auto;overflow-x:hidden;scroll-behavior:smooth;scroll-padding-top:88px}.business-plan-page h1,.business-plan-page h2,.business-plan-page h3,.business-plan-page h4,.business-plan-page p,.business-plan-page figure{margin:0}.hero-grid{grid-template-columns:minmax(0,1fr);gap:30px}.hero h1{font-size:clamp(36px,4.4vw,65px);line-height:1.4}.hero-copy{max-width:800px;font-size:15px}.hero-visual{max-width:none;padding:0}.hero-visual:before{display:none}.hero-visual img{width:100%;height:auto;aspect-ratio:auto}.hero-meta{margin-bottom:25px}.image-open{display:block;width:100%;border:0;padding:0;background:transparent;cursor:zoom-in;color:inherit;text-align:inherit}.showcase-summary{display:flex;gap:35px;flex-wrap:wrap;border-block:1px solid var(--line);padding:17px 0}.showcase-summary strong{font:26px/1.5 Consolas,monospace;color:var(--green)}.showcase-summary small{font:11px var(--sans);color:var(--muted);margin-left:5px}.project-case{padding:28px 0 35px;border-top:1px solid var(--line)}.project-heading{display:flex;justify-content:space-between;gap:20px;align-items:center}.project-heading h3{font-family:var(--serif);font-size:28px;margin:8px 0}.project-size{color:var(--green);font-size:21px;white-space:nowrap}.project-size small{font:10px var(--sans);color:var(--muted)}.project-story{font-size:13px;color:var(--muted);margin:8px 0 22px!important}.interior-gallery{display:grid;grid-template-columns:1fr 1fr;gap:18px}.project-main img,.project-detail img{display:block;width:100%;height:auto;aspect-ratio:auto;object-fit:contain}.project-main figcaption,.project-detail figcaption{display:flex;justify-content:space-between;gap:12px;padding:10px 0 18px;color:var(--muted);font-size:11px}.project-main figcaption span,.project-detail figcaption span{color:var(--green);white-space:nowrap}.subsection-heading{margin:30px 0 22px}.subsection-heading h3{font-size:23px;margin:8px 0 12px}.subsection-heading p{font-size:13px;color:var(--muted);line-height:1.95}.image-viewer{margin:auto;max-width:96vw;max-height:96dvh;border:1px solid var(--line);border-radius:4px;background:var(--paper);padding:16px;color:var(--ink)}.image-viewer::backdrop{background:#18251ee8}.viewer-close{display:block;margin-left:auto;background:transparent;border:1px solid var(--line);color:var(--green);padding:5px 12px;font-size:12px;margin-bottom:12px}.image-viewer img{display:block;max-width:calc(96vw - 34px);max-height:80dvh;width:auto;height:auto;object-fit:contain}.image-viewer figcaption{padding-top:10px;font-size:12px;color:var(--muted)}.home-link{text-decoration:none;display:inline-flex;align-items:center;white-space:nowrap}.project-case .eyebrow{font-size:10px}@media(max-width:560px){.interior-gallery{grid-template-columns:1fr}.showcase-summary{gap:18px}.showcase-summary strong{font-size:22px}.project-heading h3{font-size:25px}.project-size{font-size:17px}.hero h1{font-size:36px}.hero h1 br{display:none}.hero-copy{font-size:13px}.project-story{font-size:12px}.project-case{padding:22px 0}}@media print{.business-plan-page{height:auto;overflow:visible}.hero-grid{display:block}.hero-visual{margin-top:20px!important}.hero h1{font-size:27pt}.hero-copy{max-width:none}.image-viewer{display:none!important}.project-case{break-before:page}.project-main{break-inside:avoid}.project-main img{max-height:145mm;width:100%;object-fit:contain}.interior-gallery{grid-template-columns:1fr 1fr}.project-detail{break-inside:avoid}.project-heading h3{font-size:23pt}.project-main figcaption span,.project-detail figcaption span{display:none}.showcase-summary{gap:25px}.project-story{font-size:9pt}.image-open{cursor:default}.subsection-heading{break-after:avoid}}


.business-plan-page{color-scheme:inherit}.home-link{display:inline-flex;align-items:center;padding:7px 13px;border:1px solid var(--studio-accent-border);border-radius:3px;font-size:12px;color:var(--green);text-decoration:none;white-space:nowrap}.project-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:26px 22px;margin-top:28px}.project-case{min-width:0;padding:20px 0 22px}.project-heading{align-items:flex-start;gap:12px}.project-heading h3{font-size:20px;line-height:1.6}.project-size{display:flex;flex-direction:column;align-items:flex-end;font-size:15px;padding-top:5px}.project-story{font-size:12px;min-height:65px;margin:7px 0 15px!important}.project-main img,.project-detail img{width:100%;height:auto;object-fit:contain;aspect-ratio:auto}.project-main figcaption{padding:8px 0 11px}.more-views{border-top:1px solid var(--line);padding-top:9px}.more-views summary{font-size:11px;color:var(--green);cursor:pointer}.more-views[open] .project-detail{margin-top:12px}.interior-gallery{grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.interior-gallery figcaption{display:block;line-height:1.8}.interior-gallery figcaption span{display:block}@media(max-width:640px){.project-grid{grid-template-columns:1fr}.project-story{min-height:0}.interior-gallery{grid-template-columns:1fr}.project-heading h3{font-size:21px}}@media print{.project-grid{display:grid;grid-template-columns:1fr 1fr}.project-case{break-before:auto;break-inside:avoid}.more-views{display:none}.project-main img{max-height:80mm}.interior-gallery{grid-template-columns:1fr 1fr}}

@media print{.business-plan-page{--paper:#fff;--white:#fff;--ink:#202e2a;--muted:#64736c;--green:#294c3d;--soft:#e6ebe1;--line:#d7dcd2;--orange:#bf603c;--on-accent:#fff;color-scheme:light}.note.warm,.label.idea{background:#f5e9dc;color:#994d32}}

@media screen and (max-width:640px){
 .business-plan-page{scroll-padding-top:124px}
 .chapter{scroll-margin-top:0}
 .home-link{min-height:40px;padding:8px 12px}
 .sidebar nav a{min-height:40px;align-items:center}
 .project-heading>div{min-width:0}
 .table-wrap{overflow:visible}
 .table-wrap table,.table-wrap.narrow table{display:block;min-width:0;width:100%;font-size:12px}
 .table-wrap thead{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
 .table-wrap tbody{display:grid;gap:12px}
 .table-wrap tr{display:block;border:1px solid var(--line);border-radius:4px;background:var(--white);overflow:hidden}
 .table-wrap td{display:block;max-width:100%;padding:11px 14px;overflow-wrap:anywhere}
 .table-wrap td:first-child{background:var(--soft)}
 .table-wrap td:last-child{border-bottom:0}
 .table-wrap td::before{content:attr(data-label);display:block;margin-bottom:4px;color:var(--muted);font-size:10px;font-weight:500}
}
@media screen{.business-plan-page{position:fixed;inset:0}}
.export-pdf{display:inline-flex;align-items:center;white-space:nowrap;border:1px solid var(--studio-accent-border);background:var(--soft);padding:7px 13px;border-radius:3px;font-size:12px;color:var(--green)}
.export-pdf:disabled{opacity:.65;cursor:wait}
.pdf-error{padding:10px 20px;font-size:12px;color:var(--orange);border-bottom:1px solid var(--line)}
@media screen and (max-width:560px){.topbar{gap:8px}.top-actions{gap:6px}.home-link,.export-pdf{min-height:40px;padding:8px 9px;font-size:11px}}
@media screen and (max-width:380px){.brand-cn{display:none}.brand{gap:8px}}
@media print{
 :global(html:has(.business-plan-page)),:global(body:has(.business-plan-page)),:global(#app:has(.business-plan-page)){height:auto;overflow:visible;background:#fff;color-scheme:only light!important}
 .pdf-error{display:none!important}
 .business-plan-page{height:auto;overflow:visible}
 .chapter-heading,.subsection-heading,.note,.formula,.lead{break-inside:avoid}
 .hero-visual figcaption span:last-child{display:none}
 p{orphans:3;widows:3}
}
</style>
