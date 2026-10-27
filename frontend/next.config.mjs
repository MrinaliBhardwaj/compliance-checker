/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
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
