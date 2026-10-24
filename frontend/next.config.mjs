/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  async rewrites() {
    return [
      {
        source: '/health',
        destination: 'http://localhost:8000/health',
      },
      {
        source: '/ingestion/history',
        destination: 'http://localhost:8000/ingestion/history',
      },
      {
        source: '/me',
        destination: 'http://localhost:8000/me',
      },
      {
        source: '/graph/stats',
        destination: 'http://localhost:8000/graph/stats',
      },
      {
        source: '/auth/login',
        destination: 'http://localhost:8000/auth/login',
      },
      {
        source: '/auth/logout',
        destination: 'http://localhost:8000/auth/logout',
      },
      {
        source: '/engagements',
        destination: 'http://localhost:8000/engagements',
      },
      {
        source: '/ingest/bloodhound',
        destination: 'http://localhost:8000/ingest/bloodhound',
      },
      {
        source: '/paths',
        destination: 'http://localhost:8000/paths',
      },
      {
        source: '/plan/generate',
        destination: 'http://localhost:8000/plan/generate',
      },
      {
        source: '/gnn/status',
        destination: 'http://localhost:8000/gnn/status',
      },
      {
        source: '/actors',
        destination: 'http://localhost:8000/actors',
      },
      {
        source: '/ingestion/history/:hash*',
        destination: 'http://localhost:8000/ingestion/history/:hash*',
      },
    ];
  },
}

export default nextConfig
