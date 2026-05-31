# 部署到腾讯云轻量服务器(Docker · CPU)

服务器: Ubuntu 22.04 + Docker, 公网 IP `111.229.172.176`, 4核4G。无显卡 → CPU 运行。
样本已预渲染, 点开即播; "上传视频分析"在 CPU 上很慢, 仅演示用内置样本即可。

部署包(本地已生成, 约 163M): `deploy/cms_deploy.tar.gz`
> 已剔除: 邮箱密钥 alerting.yaml、源样本大视频、annotated.mp4 原始标注视频。

## 1. 开放端口(腾讯云控制台 · 网页操作)
轻量云 → 点进实例 → **防火墙** 标签 → **添加规则**:
- 应用类型: 自定义 ; 协议: TCP ; 端口: **8000** ; 来源: 0.0.0.0/0 → 确定。

## 2. 上传部署包(FinalShell)
1. FinalShell 新建连接: 主机 `111.229.172.176`, 端口 22, 用户 `root`, 密码=腾讯云控制台里设的(忘了就在控制台"重置密码")。
2. 连接成功后, 用左侧/下方的**文件(SFTP)面板**进入 `/root/`。
3. 把本机 `E:\code\construction_monitoring_system\deploy\cms_deploy.tar.gz` 拖进 `/root/`, 等上传完(约几分钟)。

## 3. 构建并运行(FinalShell 终端, 逐条粘贴)
```bash
cd /root
tar xzf cms_deploy.tar.gz
cd cms
docker build -t cms .          # 首次约 5-10 分钟(下载 PyTorch 等)
docker run -d --name cms --restart unless-stopped -p 8000:8000 cms
docker logs -f cms             # 看到 "Application startup complete" 即成功; Ctrl+C 退出查看
```

## 4. 访问
浏览器打开: **http://111.229.172.176:8000**

## 常用运维
```bash
docker ps                 # 看容器是否在跑
docker logs cms           # 看日志
docker restart cms        # 重启
docker stop cms && docker rm cms   # 停止并删除(更新前先做这步)
```

## 更新到新版本
本地重新生成 `cms_deploy.tar.gz` → 上传覆盖 → 服务器:
```bash
cd /root && rm -rf cms && tar xzf cms_deploy.tar.gz && cd cms
docker stop cms && docker rm cms
docker build -t cms . && docker run -d --name cms --restart unless-stopped -p 8000:8000 cms
```

## 说明 / 限制
- 想用 80 端口(免输 :8000): 把 `-p 8000:8000` 改成 `-p 80:8000`, 并在防火墙开放 80。
- 邮件告警在云端默认关闭(未上传密钥); 事故报告 PDF 正常。
- 上传视频分析 = CPU 推理, 很慢且占内存, 4G 机器谨慎使用; 演示请用内置样本。
