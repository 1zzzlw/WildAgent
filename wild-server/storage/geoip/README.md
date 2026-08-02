# GeoIP 数据目录

GeoIP 是 Presence 在线列表的可选增强，不属于 Agent、RAG 或 Blueprint 主链路。没有数据库时不需要做任何配置：在线人数、脱敏 IP 和连接时间仍然正常，公网地区显示“地区库未配置”。

如果需要显示省份：

1. 在 MaxMind 官网注册免费账号并接受 GeoLite 许可。
2. 进入下载页面，下载 GeoLite2 City 的 MMDB 压缩包。
3. 解压并找到 `GeoLite2-City.mmdb`，复制到本目录。
4. 重启后端；默认路径无需再修改 `.env`。
5. 如果想把数据库放在其他目录，通过 `PRESENCE__GEOIP_DB` 指向它。
6. 按 GeoLite 许可要求定期更新数据库。

`.mmdb` 不提交 Git，客户端 IP 也不会发送给第三方查询服务。设置 `PRESENCE__ENABLED=false` 可以连同后端统计和前端入口一起关闭整个扩展。

## Jenkins 远程部署

生产部署默认从宿主机 `/opt/wild-agent/storage/geoip/GeoLite2-City.mmdb` 读取数据库。Jenkins 会把该目录只读挂载到容器的 `/app/storage/geoip`，并向后端注入：

```env
PRESENCE__GEOIP_DB=/app/storage/geoip/GeoLite2-City.mmdb
```

因此首次启用地区显示时，只需要把下载并解压后的文件上传到远程服务器：

```text
/opt/wild-agent/storage/geoip/GeoLite2-City.mmdb
```

如果修改了 Jenkins 参数 `DEPLOY_DATA_DIR`，宿主机目录会跟随它变化；如果修改了 `PRESENCE_GEOIP_DB`，应确保它仍与容器挂载目录中的实际文件位置一致。
