/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Layer 1 runs the API as a separate service (apps/api); this rewrite
  // lets the browser call same-origin `/api/*` in dev instead of hard-
  // coding the API's host/port into every fetch call.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
