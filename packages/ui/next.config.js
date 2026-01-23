/** @type {import("next").NextConfig} */
const nextConfig = {
  distDir: "dist",
  output: "export", // Static export for embedding in backend
  trailingSlash: true, // Ensures /connectors/ works as /connectors/index.html
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8080/api/:path*",
      },
      {
        source: "/bicp",
        destination: "http://localhost:8080/bicp",
      },
      {
        source: "/bicp/:path*",
        destination: "http://localhost:8080/bicp/:path*",
      },
    ];
  },
};
module.exports = nextConfig;
