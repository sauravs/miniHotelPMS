/**
 * The engine is a separate process; the browser never talks to it. Data is fetched server-side
 * (lib/api.ts), and even the engine's stylesheet is served from this origin by a route handler
 * (app/style.css/route.ts) - so no CORS header is ever needed and the engine's policy is
 * untouched.
 *
 * No `rewrites()`: Next compiles them at build time, which froze the stylesheet to the build's
 * engine address while every data request read HOTELCONTROLS_API_URL at run time.
 */

/** @type {import('next').NextConfig} */
const config = {
  reactStrictMode: true,
  poweredByHeader: false,
};

export default config;
