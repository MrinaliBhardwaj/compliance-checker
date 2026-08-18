# Regis frontend — Next.js standalone server.
FROM node:20-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:20-slim AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# next.config.mjs keeps TypeScript checking on, so a type error fails the image
# build rather than surfacing in the browser.
RUN npm run build

FROM node:20-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production PORT=3000
RUN useradd --create-home --uid 10001 regis
# `standalone` carries its own minimal node_modules; static/ and public/ are not
# included in it and must be copied alongside.
COPY --from=build --chown=regis:regis /app/.next/standalone ./
COPY --from=build --chown=regis:regis /app/.next/static ./.next/static
USER regis
EXPOSE 3000
CMD ["node", "server.js"]
