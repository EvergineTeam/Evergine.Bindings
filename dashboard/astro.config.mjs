// @ts-check
import { defineConfig } from "astro/config";

// The hub is a public repository, so Pages serves it from a sub-path rather than
// a domain root. Every internal link goes through `import.meta.env.BASE_URL` so
// the site works the same locally and once deployed.
export default defineConfig({
  site: "https://evergineteam.github.io",
  base: "/Evergine.Bindings",
  trailingSlash: "always",
  build: { format: "directory" },
});
