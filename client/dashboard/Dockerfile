# VITE_* values are baked in at build time (they are public URLs, never secrets).
FROM node:20-alpine AS build
WORKDIR /app
COPY module4-dashboard-react/package*.json ./
RUN npm ci
COPY module4-dashboard-react/ ./
ARG VITE_AUTH_API_BASE=http://localhost:8001
ARG VITE_ADMIN_API_BASE=http://localhost:8005
ARG VITE_SYNTHESIS_API_BASE=http://localhost:8006
ENV VITE_AUTH_API_BASE=$VITE_AUTH_API_BASE VITE_ADMIN_API_BASE=$VITE_ADMIN_API_BASE VITE_SYNTHESIS_API_BASE=$VITE_SYNTHESIS_API_BASE
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
