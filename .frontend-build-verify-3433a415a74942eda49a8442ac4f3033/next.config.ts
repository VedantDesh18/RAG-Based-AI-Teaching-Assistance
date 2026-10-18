import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_URL || "http://127.0.0.1:8000";
// Next.js buffers cloned request bodies before forwarding rewrites. Keep this
// just above the backend's 2 GiB file limit so multipart framing is not cut off.
const uploadProxyBodyLimit = 2 * 1024 * 1024 * 1024 + 1024 * 1024;

const nextConfig: NextConfig = {
  experimental: {
    proxyClientMaxBodySize: uploadProxyBodyLimit,
  },
  rewrites: async () => {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
