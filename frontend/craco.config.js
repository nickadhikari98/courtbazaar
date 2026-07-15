// craco.config.js
const path = require("path");
require("dotenv").config();

// Check if we're in development/preview mode (not production build)
// Craco sets NODE_ENV=development for start, NODE_ENV=production for build
const isDevServer = process.env.NODE_ENV !== "production";

// Environment variable overrides
const config = {
  enableHealthCheck: process.env.ENABLE_HEALTH_CHECK === "true",
};

// Conditionally load health check modules only if enabled
let WebpackHealthPlugin;
let setupHealthEndpoints;
let healthPluginInstance;

if (config.enableHealthCheck) {
  WebpackHealthPlugin = require("./plugins/health-check/webpack-health-plugin");
  setupHealthEndpoints = require("./plugins/health-check/health-endpoints");
  healthPluginInstance = new WebpackHealthPlugin();
}

let webpackConfig = {
  eslint: {
    configure: {
      extends: ["plugin:react-hooks/recommended"],
      rules: {
        "react-hooks/rules-of-hooks": "error",
        "react-hooks/exhaustive-deps": "warn",
        // --- Design-system drift guardrails ---
        // See PRODUCT_DESIGN_SYSTEM.md §8.4 (Do/Don't) and DESIGN_SYSTEM_AUDIT.md
        // for the history behind each of these. Warnings, not errors: `npm run
        // build` doesn't set CI=true, so these surface in the console without
        // blocking a build — bump to "error" if the team wants them enforced.
        "no-restricted-syntax": [
          "warn",
          {
            // Raw hex colors bypass the design tokens in tailwind.config.js /
            // index.css. Import the token (bg-primary, text-accent, etc.)
            // instead of a literal like "#0F172A".
            selector: "Literal[value=/#[0-9a-fA-F]{3}([0-9a-fA-F]{3}([0-9a-fA-F]{2})?)?\\b/]",
            message:
              "Avoid hardcoded hex colors — use a design token from tailwind.config.js/index.css instead (see PRODUCT_DESIGN_SYSTEM.md §4.1).",
          },
          {
            // The exact magic number this pass just tokenized as `text-2xs`
            // (PRODUCT_DESIGN_SYSTEM.md §5.2) — guards against it creeping back in.
            selector: "Literal[value=/text-\\[10px\\]/]",
            message: "Use `text-2xs` instead of the arbitrary value `text-[10px]` — see PRODUCT_DESIGN_SYSTEM.md §5.2.",
          },
          {
            // Inline style props bypass the token system entirely and can't be
            // themed/audited the way a Tailwind class can. Computed values
            // (widths, transforms) are the accepted exception — this only
            // warns, so those aren't blocked, just flagged for a second look.
            selector: "JSXAttribute[name.name='style']",
            message:
              "Inline style props bypass design tokens — prefer a Tailwind class. If the value is genuinely computed at runtime (e.g. a progress-bar width), this warning is expected to be suppressed inline, not worked around.",
          },
        ],
        // Deliberately NOT lint-enforcing "no raw <button>": the audit found
        // 40+ raw <button> call sites, and a real chunk of them are filter
        // chips, selection cards, and Popover/Combobox triggers that are
        // correctly NOT the Button component (see DESIGN_SYSTEM_AUDIT.md §2.G).
        // A mechanical AST rule can't tell those apart from a standard action
        // button styled by hand, so it would train the team to ignore this
        // rule's warnings rather than catch real drift. Enforce this one via
        // code review against PRODUCT_DESIGN_SYSTEM.md §8.4 instead.
      },
    },
  },
  webpack: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
    configure: (webpackConfig) => {

      // Add ignored patterns to reduce watched directories
        webpackConfig.watchOptions = {
          ...webpackConfig.watchOptions,
          ignored: [
            '**/node_modules/**',
            '**/.git/**',
            '**/build/**',
            '**/dist/**',
            '**/coverage/**',
            '**/public/**',
        ],
      };

      // Add health check plugin to webpack if enabled
      if (config.enableHealthCheck && healthPluginInstance) {
        webpackConfig.plugins.push(healthPluginInstance);
      }
      return webpackConfig;
    },
  },
};

webpackConfig.devServer = (devServerConfig) => {
  // Add health check endpoints if enabled
  if (config.enableHealthCheck && setupHealthEndpoints && healthPluginInstance) {
    const originalSetupMiddlewares = devServerConfig.setupMiddlewares;

    devServerConfig.setupMiddlewares = (middlewares, devServer) => {
      // Call original setup if exists
      if (originalSetupMiddlewares) {
        middlewares = originalSetupMiddlewares(middlewares, devServer);
      }

      // Setup health endpoints
      setupHealthEndpoints(devServer, healthPluginInstance);

      return middlewares;
    };
  }

  return devServerConfig;
};

// Wrap with visual edits (automatically adds babel plugin, dev server, and overlay in dev mode)
if (isDevServer) {
  try {
    const { withVisualEdits } = require("@emergentbase/visual-edits/craco");
    webpackConfig = withVisualEdits(webpackConfig);
  } catch (err) {
    if (err.code === 'MODULE_NOT_FOUND' && err.message.includes('@emergentbase/visual-edits/craco')) {
      console.warn(
        "[visual-edits] @emergentbase/visual-edits not installed — visual editing disabled."
      );
    } else {
      throw err;
    }
  }
}

module.exports = webpackConfig;
