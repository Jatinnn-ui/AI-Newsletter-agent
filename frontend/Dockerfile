# Build static assets, serve with nginx. VITE_API_URL is baked in at build time.
FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# Primary var is VITE_API_BASE_URL; VITE_API_URL is kept as a fallback.
ARG VITE_API_BASE_URL=http://127.0.0.1:8000
ARG VITE_API_URL=$VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:1.29-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s CMD wget -q -O - http://127.0.0.1/health || exit 1
