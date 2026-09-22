ARG NODE_BASE_IMAGE=node:22-alpine
ARG NGINX_BASE_IMAGE=nginx:alpine

FROM ${NODE_BASE_IMAGE} AS builder
ARG NPM_REGISTRY=https://registry.npmmirror.com

WORKDIR /app

# 构建上下文是仓库根（见 Jenkinsfile：docker build -f wild-web/Dockerfile .）。
# wild-web 依赖 wild-core（package.json: "wild-core": "file:../wild-core"），
# 必须先把它 COPY 到 /app 的父目录（/wild-core），否则 npm ci 解析不到。
COPY wild-web/package.json wild-web/package-lock.json ./
COPY wild-core/ /wild-core/
RUN npm ci --registry=${NPM_REGISTRY}

COPY wild-web/ ./
RUN npm run build

FROM ${NGINX_BASE_IMAGE}

COPY wild-web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
EXPOSE 443
