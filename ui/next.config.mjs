/**
 * The engine is a separate process; the browser never talks to it. Data is fetched server-side
 * (lib/api.ts). The one thing the browser does fetch from the engine is its stylesheet, so the
 * two surfaces share one set of criterion-2 rules - and it arrives through this rewrite, on this
 * origin, so no CORS header is ever needed and the engine's policy is untouched.
 */
const ENGINE = process.env.HOTELCONTROLS_API_URL ?? "http://127.0.0.1:8765";

/** @type {import('next').NextConfig} */
const config = {
  reactStrictMode: true,
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/style.css", destination: `${ENGINE}/style.css` }];
  },
};

export default config;
