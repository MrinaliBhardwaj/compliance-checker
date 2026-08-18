/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Emit a self-contained server bundle so the container image ships only the
  // files actually reachable at runtime, not the whole node_modules tree.
  output: "standalone",
  // Keep TypeScript type-checking ON during build (validates the typed API layer);
  // ESLint is style-only here, skip it so the build doesn't fail on lint opinions.
  eslint: { ignoreDuringBuilds: true },
  // Proxy API calls to the FastAPI backend in dev.
  async rewrites() {
    const api = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    return [{ source: "/api/:path*", destination: `${api}/:path*` }];
  },
};
export default nextConfig;
