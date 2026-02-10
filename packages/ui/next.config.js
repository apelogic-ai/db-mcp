/** @type {import("next").NextConfig} */
const nextConfig = {
  distDir: "dist",
  output: "export", // Static export for embedding in backend
  trailingSlash: true, // Ensures /config/ works as /config/index.html
  turbopack: {
    root: __dirname, // Fix monorepo workspace root inference
  },
  async rewrites() {
    // In CI/playwright mocked e2e, we intercept /bicp in the browser.
    // If Next proxies /bicp to localhost:8080, tests fail with ECONNREFUSED.
    if (process.env.DISABLE_BICP_PROXY === "1") return [];

    const target = process.env.BICP_PROXY_TARGET || "http://localhost:8080";

    return [
      {
        source: "/api/:path*",
        destination: `${target}/api/:path*`,
      },
      {
        source: "/bicp",
        destination: `${target}/bicp`,
      },
      {
        source: "/bicp/:path*",
        destination: `${target}/bicp/:path*`,
      },
    ];
  },
};
module.exports = nextConfig;
