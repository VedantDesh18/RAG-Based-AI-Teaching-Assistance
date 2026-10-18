FROM node:20-slim

WORKDIR /app

# Install dependencies using package-lock.json for reproducible builds
COPY package.json package-lock.json ./
RUN npm ci

# Copy application source files
COPY . .

# Set environment variables for Next.js dev server
ENV PORT=3000 \
    HOSTNAME="0.0.0.0"

# Expose Next.js port
EXPOSE 3000

# Start development server binding to 0.0.0.0
CMD ["npm", "run", "dev", "--", "-H", "0.0.0.0"]
