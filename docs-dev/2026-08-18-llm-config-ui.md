# LLM 配置管理功能实施报告

**日期**: 2026-08-18  
**功能**: 动态配置 LLM 模型名称、API Key 和 Base URL  
**状态**: ✅ 已完成

---

## 功能概述

添加了一个可视化的 LLM 配置界面，允许用户在运行时动态修改大语言模型的连接参数，无需重启服务器或编辑配置文件。

### 主要功能

1. **动态配置 LLM 参数**
   - 模型名称（例如：qwen-plus, gpt-4, deepseek-chat）
   - API Key（加密输入，不显示完整密钥）
   - Base URL（自建或第三方服务地址）

2. **实时生效**
   - 配置保存后立即更新全局配置
   - 下次 AI 生成时自动使用新配置
   - 无需重启服务器

3. **连接测试**
   - 一键测试当前配置是否可用
   - 显示模型真实响应内容
   - 快速诊断连接问题

4. **安全性**
   - API Key 输入框使用密码模式
   - 获取配置时只显示"已设置/未设置"状态
   - 不在前端暴露完整密钥

---

## 实施细节

### 后端 API

**文件**: `wild-server/app/api/config_api.py`

**接口列表**:

1. `GET /api/config/llm` - 获取当前配置（隐藏 API Key）
   ```json
   {
     "name": "qwen-plus",
     "api_key_set": true,
     "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"
   }
   ```

2. `POST /api/config/llm` - 更新配置
   ```json
   {
     "name": "gpt-4",
     "api_key": "sk-xxx",
     "base_url": "https://api.openai.com/v1"
   }
   ```
   
   响应:
   ```json
   {
     "success": true,
     "message": "LLM 配置已更新，将在下次生成时生效",
     "config": {
       "name": "gpt-4",
       "api_key_set": true,
       "base_url": "https://api.openai.com/v1"
     }
   }
   ```

3. `POST /api/config/llm/test` - 测试连接
   ```json
   {
     "success": true,
     "message": "LLM 连接测试成功",
     "response": "测试成功"
   }
   ```

**特性**:
- 只更新用户提供的字段（支持部分更新）
- 异步 LLM 调用测试
- 完整的错误处理和日志记录

### 前端界面

**文件**: `wild-web/src/components/layout/LLMConfigDialog.vue`

**界面元素**:
- 模型名称输入框（带提示）
- API Key 密码输入框（带显示/隐藏切换）
- Base URL 输入框（可选）
- 当前配置展示区
- 测试连接按钮
- 保存/取消按钮

**交互流程**:
1. 用户点击顶部工具栏"配置"按钮
2. 对话框打开，自动加载当前配置
3. 用户修改需要更新的字段
4. 可选：点击"测试连接"验证配置
5. 点击"保存"提交更新
6. 显示成功提示，配置立即生效

### 集成点

**文件**: `wild-server/main.py`
- 注册 `config_router` 到 FastAPI 应用

**文件**: `wild-web/src/components/layout/EditorTopBar.vue`
- 在工具栏添加"配置"按钮
- 集成 `LLMConfigDialog` 组件

---

## 使用说明

### 1. 启动服务

```bash
# 后端
cd wild-server
.\.venv\Scripts\activate
uvicorn main:app --reload

# 前端
cd wild-web
npm run dev
```

### 2. 打开配置界面

点击顶部工具栏的"配置"按钮。

### 3. 配置 LLM

#### 示例 1：使用阿里云通义千问
```
模型名称: qwen-plus
API Key: sk-your-dashscope-api-key
Base URL: https://dashscope.aliyuncs.com/compatible-mode/v1
```

#### 示例 2：使用 OpenAI GPT-4
```
模型名称: gpt-4
API Key: sk-your-openai-api-key
Base URL: https://api.openai.com/v1
```

#### 示例 3：使用 DeepSeek
```
模型名称: deepseek-chat
API Key: sk-your-deepseek-api-key
Base URL: https://api.deepseek.com/v1
```

#### 示例 4：本地 Ollama
```
模型名称: qwen2.5:14b
API Key: (留空或填任意值)
Base URL: http://localhost:11434/v1
```

### 4. 测试连接

点击"测试连接"按钮，系统会发送一个简单的测试请求到 LLM 服务。

成功示例：
```
✅ 连接测试成功！
模型回复: 测试成功
```

失败示例：
```
❌ 连接测试失败
Error: Connection timeout
```

### 5. 保存配置

点击"保存"按钮，配置会立即更新到后端，下次 AI 生成时自动使用新配置。

---

## 配置持久化

当前实现中，配置只存储在内存中（`config` 对象）。服务器重启后会恢复到环境变量或 `.env` 文件中的配置。

### 启动时的配置优先级

1. **环境变量** (最高优先级)
   ```bash
   CHAT__NAME=qwen-plus
   CHAT__API_KEY=sk-xxx
   CHAT__BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
   ```

2. **`.env` 文件**
   ```env
   CHAT__NAME=qwen-plus
   CHAT__API_KEY=sk-xxx
   CHAT__BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
   ```

3. **代码默认值** (最低优先级)
   ```python
   name: str = "qwen-plus"
   api_key: str = ""
   base_url: str = ""
   ```

### 运行时配置

通过界面修改的配置会覆盖启动时的配置，但不会写回 `.env` 文件。

---

## 安全注意事项

### 1. API Key 保护

- ✅ 前端输入框使用 `type="password"`
- ✅ GET 接口只返回 `api_key_set: true/false`
- ✅ 不在日志中打印完整 API Key
- ⚠️ POST 请求仍然通过 HTTP 传输（需要 HTTPS）

### 2. 生产环境建议

1. **启用 HTTPS**
   ```nginx
   server {
     listen 443 ssl;
     ssl_certificate /path/to/cert.pem;
     ssl_certificate_key /path/to/key.pem;
   }
   ```

2. **添加认证保护**
   ```python
   from fastapi import Depends, HTTPException
   from fastapi.security import HTTPBearer
   
   security = HTTPBearer()
   
   @router.post("/llm")
   async def update_llm_config(
       update: ModelConfigUpdate,
       credentials = Depends(security)
   ):
       # 验证 token
       if not verify_token(credentials.credentials):
           raise HTTPException(401, "Unauthorized")
       # ...
   ```

3. **环境变量管理**
   - 使用 `.env.local`（不提交到 Git）
   - 生产环境使用密钥管理服务（如 AWS Secrets Manager）

---

## 扩展功能（未来可选）

### 1. 配置持久化到数据库

```python
from sqlalchemy import create_engine, Column, String
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class LLMConfig(Base):
    __tablename__ = 'llm_config'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    api_key = Column(String)  # 加密存储
    base_url = Column(String)
```

### 2. 多模型配置切换

支持配置多个 LLM 模型，运行时动态切换：

```python
@router.get("/llm/profiles")
async def list_profiles():
    return {
        "profiles": [
            {"id": "qwen", "name": "通义千问", "active": True},
            {"id": "gpt4", "name": "GPT-4", "active": False},
        ]
    }

@router.post("/llm/profiles/{profile_id}/activate")
async def activate_profile(profile_id: str):
    # 切换到指定配置
    pass
```

### 3. 配置导入/导出

允许用户导出配置文件并在其他环境导入。

### 4. 配置模板

提供常见 LLM 服务的预设模板，用户只需填写 API Key。

---

## 测试验证

### 手动测试步骤

1. ✅ 打开配置对话框，查看当前配置
2. ✅ 修改模型名称，保存并验证生效
3. ✅ 修改 API Key，测试连接成功
4. ✅ 修改 Base URL，保存并生成建筑
5. ✅ 测试连接失败场景（错误 API Key）
6. ✅ 部分更新（只修改一个字段）

### API 测试

```bash
# 获取配置
curl http://localhost:8000/api/config/llm

# 更新配置
curl -X POST http://localhost:8000/api/config/llm \
  -H "Content-Type: application/json" \
  -d '{"name": "gpt-4", "api_key": "sk-xxx"}'

# 测试连接
curl -X POST http://localhost:8000/api/config/llm/test
```

---

## 文件清单

### 新增文件
1. `wild-server/app/api/config_api.py` - 配置管理 API
2. `wild-web/src/components/layout/LLMConfigDialog.vue` - 配置对话框组件
3. `docs-dev/2026-08-18-llm-config-ui.md` - 本文档

### 修改文件
4. `wild-server/main.py` - 注册配置路由
5. `wild-web/src/components/layout/EditorTopBar.vue` - 添加配置按钮

---

## 总结

成功添加了 LLM 配置管理功能，用户现在可以：

- ✅ 通过可视化界面动态配置 LLM 参数
- ✅ 实时测试连接状态
- ✅ 无需重启服务器即可切换模型
- ✅ 安全地管理 API Key

这大大提升了系统的易用性和灵活性，特别适合需要频繁切换 LLM 服务或测试不同模型的场景。
