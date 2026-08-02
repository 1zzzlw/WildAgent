# 阶段十六：Presence 在线列表扩展解耦总结

## 本阶段目标

将在线人数、连接列表和 IP 地区展示从 Agent 会话逻辑中拆出，形成可独立关闭、可降级运行的 Presence 扩展，避免该辅助功能与建筑生成、会话恢复和蓝图渲染相互影响。

## 完成内容

### 后端扩展

- 新增 `app/extensions/presence`，独立负责 WebSocket 连接登记、离线清理、在线快照广播和 IP 地区解析。
- Agent WebSocket 入口只保留 `connect`、`disconnect` 两个扩展挂载点。
- Presence 内部只保存临时连接编号、脱敏 IP、地区和连接时间，不把完整 IP 发送到前端。
- 通过 `PRESENCE__ENABLED=false` 可以完全关闭在线统计与广播。

### 前端扩展

- 新增 `src/extensions/presence`，独立维护 Presence 状态、协议类型和在线列表界面。
- 顶部栏只挂载 `OnlinePresence` 组件，不直接实现列表业务。
- 后端未启用 Presence 或未发送 `presence_update` 时，入口不会显示。
- WebSocket 桥接层只负责把 Presence 消息转交给扩展 Store。

### GeoLite2 降级策略

- `GeoLite2-City.mmdb` 不是在线列表运行的必要条件。
- 未配置数据库时，在线人数、脱敏 IP 和连接时间仍可使用，公网 IP 的地区显示为“地区库未配置”。
- 配置数据库后，扩展会补充国家、省份和城市信息。
- 默认数据库路径为 `wild-server/storage/geoip/GeoLite2-City.mmdb`，也可通过 `PRESENCE__GEOIP_DB` 指定。
- 只有来自 `PRESENCE__TRUSTED_PROXY_CIDRS` 的可信反向代理连接，才会读取转发的真实 IP 请求头。

## 模块边界

Presence 只依赖 WebSocket 连接生命周期，不依赖 Agent、RAG、会话文件、蓝图编译器或渲染引擎。关闭或移除 Presence 时，核心聊天与建模流程仍可正常运行。

## 当前限制

- 当前统计口径是 WebSocket 连接数，不是登录账号数；一个用户打开多个页面会形成多个连接。
- 当前连接表保存在单个后端进程的内存中。以后部署多个后端实例时，需要使用 Redis 等共享 Presence 存储才能得到全局在线数。
- IP 定位只能提供近似地区，不能作为精确住址或安全认证依据。

## 配置入口

配置示例见 `wild-server/.env.example`，GeoLite2 新手配置说明见 `wild-server/storage/geoip/README.md`。
