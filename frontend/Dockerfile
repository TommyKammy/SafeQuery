FROM node:20-alpine

WORKDIR /app

ARG API_INTERNAL_BASE_URL
ARG NEXT_PUBLIC_API_BASE_URL

ENV API_INTERNAL_BASE_URL=${API_INTERNAL_BASE_URL}
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

COPY frontend/ ./
RUN npm run build \
    && addgroup -S app \
    && adduser -S app -G app \
    && chown -R app:app /app

EXPOSE 3000

USER app

CMD ["npm", "run", "start", "--", "-H", "0.0.0.0", "-p", "3000"]
