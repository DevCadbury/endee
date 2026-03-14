# =============================================================================
# frontend/Dockerfile — AI Customer Support Platform Frontend (Next.js)
# =============================================================================
# Multi-stage build. NEXT_PUBLIC_API_URL is baked in at build time.
# Override with: docker build --build-arg NEXT_PUBLIC_API_URL=http://your-api
# =============================================================================

FROM node:20-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci --prefer-offline

# ---------------------------------------------------------------------------
# Builder stage — compile Next.js app
# ---------------------------------------------------------------------------
FROM node:20-alpine AS builder
WORKDIR /app

# NEXT_PUBLIC_ vars are inlined at build time
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

COPY --from=deps /app/node_modules ./node_modules
COPY . .

RUN npm run build

# ---------------------------------------------------------------------------
# Production runner
# ---------------------------------------------------------------------------
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000

# Copy only what Next.js needs to run
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/public ./public

EXPOSE 3000

CMD ["npm", "start"]
