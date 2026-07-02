/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  experimental: {
    // Enable path aliases for imports
  },
  // Webpack config to resolve @/ paths
  webpack: (config) => {
    config.resolve.alias = {
      ...config.resolve.alias,
      '@/components': require('path').resolve(__dirname, 'components'),
      '@/hooks': require('path').resolve(__dirname, 'hooks'),
      '@/services': require('path').resolve(__dirname, 'services'),
      '@/utils': require('path').resolve(__dirname, 'utils'),
    };
    return config;
  },
};

module.exports = nextConfig;