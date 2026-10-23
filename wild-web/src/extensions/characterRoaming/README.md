# 人物漫游扩展

视口右上角“人物漫游”启动程序化火柴机器人，默认第三视角。鼠标锁定后，WASD移动，空格跳跃，鼠标转向，F5切换第一/第三视角，准星瞄准后右键交互。Esc释放鼠标并暂停，再点击画面或“继续漫游”恢复。“退出漫游”恢复编辑相机与编辑操作。只有漫游开启时拦截普通F5，Ctrl+F5仍保留浏览器行为。

- `CharacterRoamingPanel.vue` / `store.ts`：入口、提示和临时体验状态，不保存进WILD或撤销栈。
- `CharacterRoamingRuntime.ts`：输入、胶囊体移动、跳跃、台阶尝试、视角与生命周期。由视口每帧调用`tick(delta)`，不创建额外RAF，不读取业务store、文档或后端。
- `RobotAvatar.ts`：程序几何机器人与行走/腾空姿态，无GLB、图片或外部模型。
- `RoamingCollisionWorld.ts`：实际显示几何的静态Octree与活动门窗碰撞体。展开InstancedMesh的实际世界矩阵；排除辅助物、文字、水面；玻璃参与碰撞。只借用源网格，退出时释放自己的索引，不释放建筑资源。

宿主接入在`App.vue`和`CanvasViewport.vue`：给运行时提供scene、worldRoot、camera、canvas及交互回调；暂停OrbitControls和编辑选取/变换；临时显示完整实体、关闭剖切，退出恢复原设置。场景重建或切换会话会退出漫游，避免保留已被替换的网格。门窗/灯/电梯交互仍由现有`toggleRuntimeInteraction`执行，不另建状态或改写WILD。

当前人物高1.75m、胶囊半径0.24m、步速3.2m/s；台阶尝试上限0.32m，仍检查头部空间与落脚。按真实几何碰撞，不把整个建筑包围盒当墙；无法通行的窄门、封闭楼板或缺失楼梯不会自动修复。水面不当实体平台，未实现游泳；移动电梯没有专门的乘客跟随约束。Core的door/window/bay_window省略interaction也默认可开合，interaction:false显式固定；普通原语拼出的装饰门窗不自动识别为语义构件。

本次按用户要求未运行测试、构建或浏览器体验；移动、楼梯、门窗、F5和退出恢复的实际表现由用户验收。
