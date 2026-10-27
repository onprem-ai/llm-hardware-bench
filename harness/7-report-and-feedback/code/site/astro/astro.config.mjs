import { defineConfig } from 'astro/config';

// SITE_BASE lets the same build serve from a subpath (GitHub Pages serves this
// repository under /<repo>/). Local builds keep the default root.
export default defineConfig({
  output: 'static',
  trailingSlash: 'always',
  build: { format: 'directory' },
  base: process.env.SITE_BASE || '/',
});
