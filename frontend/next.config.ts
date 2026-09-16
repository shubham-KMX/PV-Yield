import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  // Pin the project root so Next.js doesn't get confused by a stray
  // package-lock.json in a parent directory (e.g. the user's home folder).
  turbopack: {
    root: path.join(__dirname),
  },
};

export default nextConfig;
