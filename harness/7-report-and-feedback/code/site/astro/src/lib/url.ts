// Prefix a site-absolute path with the configured base (astro.config `base`),
// so the site works both at a domain root and under a subpath such as
// GitHub Pages' /<repo>/. Pass paths starting with '/'.
const BASE = import.meta.env.BASE_URL.replace(/\/$/, '');
export const url = (p: string) => `${BASE}${p}`;
