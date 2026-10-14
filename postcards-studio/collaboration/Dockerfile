FROM node:22-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev --no-audit --no-fund --fetch-retries=10 --fetch-timeout=120000
COPY src ./src
RUN mkdir -p /data
EXPOSE 1234
CMD ["npm", "start"]
