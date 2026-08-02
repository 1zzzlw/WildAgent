# 阶段十五：WebSocket 在线人数与地区列表总结

## 本阶段目标

在前端实时显示当前 Agent WebSocket 在线连接数，并允许用户展开查看经过隐私处理的在线连接列表。

## 已完成

1. 后端增加进程内 WebSocket 连接注册表，在连接建立、主动断开、异常断开和心跳超时后广播 `presence_update`。
2. 广播内容包括在线数量，以及每个连接的临时 ID、脱敏 IP、地区和连接时间；连接结束后立即从内存移除。
3. IP 直连时取 WebSocket 对端地址；经过可信 Nginx/Docker 代理时才接受 `X-Real-IP`，避免任意客户端伪造地区。
4. IPv4 只显示前两段，例如 `113.96.*.*`；IPv6 只显示前四组。完整 IP 不写入文件，也不发送给前端。
5. 地区通过服务端本地 `GeoLite2-City.mmdb` 查询，不调用第三方公网接口。内网、本机、数据库缺失和无法定位都有明确降级文本。
6. 前端顶部使用 Element Plus 状态标签显示“人数在线/连接中/重连中/离线”，点击后展示地区、脱敏 IP 和连接时间。
7. WebSocket 断开时在线人数和列表立即清空，重连成功后以后端最新广播为准。
8. Presence 已从主业务中拆出：后端位于 `app/extensions/presence`，前端位于 `src/extensions/presence`；`ws_agent` 只调用连接/断开入口，顶部栏只挂载独立组件。

## 配置

- 数据库默认路径：`wild-server/storage/geoip/GeoLite2-City.mmdb`
- 整体开关：`PRESENCE__ENABLED=false` 可完全关闭后端统计和前端入口。
- 自定义数据库：`PRESENCE__GEOIP_DB`
- 可信代理网段：`PRESENCE__TRUSTED_PROXY_CIDRS`
- `.mmdb` 不提交 Git，应按 GeoLite 许可定期更新。
- 不配置 `.mmdb` 不影响在线列表，只会把公网地区显示为“地区库未配置”。

## 边界

- 当前“人数”是 WebSocket 连接数，不是登录用户数；同一用户打开两个标签页会计算为两个连接。
- IP 地区只是近似结果，不能用于识别精确地址或作为安全授权依据。
- 注册表只在当前 Python 进程内有效。未来启用多 Worker 或多服务器时，需要 Redis 等共享 Presence 服务聚合人数。

## 回归覆盖

1. 两个连接依次进入时广播 `1 → 2`，其中一个离开后广播 `1`。
2. 验证前端只接收脱敏 IP，并在断线后清空人数和列表。
3. 验证可信代理读取真实 IP，非可信对端不能伪造代理头。
4. 验证本机、内网、数据库缺失和无效 IP 的降级行为。
