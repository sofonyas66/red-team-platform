# Frontend Dockerfile for Next.js 16 + pnpm
# Multi-stage build for smaller production image

# ─── Builder ──────────────────────────────────────────────────────────────
FROM node:22-alpine AS builder

WORKDIR /app

# Install pnpm
RUN corepack enable && corepack prepare pnpm@latest --activate

# Use faster npm registry mirror
RUN pnpm config set registry https://registry.npmmirror.com

# Copy package files first for better caching
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./

# Install dependencies
RUN pnpm install --frozen-lockfile

# Copy source
COPY . .

# Build production bundle
RUN pnpm build

# ─── Runner ───────────────────────────────────────────────────────────────
FROM node:22-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production

# Copy built assets and dependencies
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

# Expose port
EXPOSE 3000

# Start Next.js
CMD ["node", "server.js"]