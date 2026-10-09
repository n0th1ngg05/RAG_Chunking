FROM node:20-slim

WORKDIR /app

COPY package.json ./
RUN npm install --omit=dev

COPY . .

RUN mkdir -p /app/uploads

EXPOSE 3000

CMD ["node", "src/server.js"]
