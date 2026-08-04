# ---- Build stage ----
FROM node:24-alpine AS build

WORKDIR /app

# Install dependencies (layer caching)
COPY package.json package-lock.json ./
RUN npm ci

# Copy source and build
COPY . .
RUN npm run build

# Prune to production deps only
RUN npm prune --omit=dev

# ---- Production stage ----
FROM node:24-alpine AS production

WORKDIR /app

ENV NODE_ENV=production
ENV PORT=4300

# Copy only what's needed to run
COPY --from=build /app/dist ./dist
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/package.json ./

USER node

EXPOSE 4300

CMD ["node", "dist/server/index.js"]
