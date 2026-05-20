/** @type {import('next').NextConfig} */
const isDev = process.env.NODE_ENV === 'development';

const nextConfig = {
  // Static export for production (served by FastAPI). Skipped in dev so
  // `rewrites()` can proxy /api/* to the running backend.
  ...(isDev ? {} : { output: 'export' }),
  reactStrictMode: true,
  images: { unoptimized: true },
  trailingSlash: false,
  async rewrites() {
    if (!isDev) return [];
    const target = process.env.BACKEND_URL ?? 'http://localhost:8000';
    return [
      { source: '/api/:path*', destination: `${target}/api/:path*` },
    ];
  },
};

export default nextConfig;
