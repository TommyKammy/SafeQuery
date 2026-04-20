FROM node:20-alpine

WORKDIR /app

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
