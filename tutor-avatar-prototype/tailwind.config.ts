import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0a0a0f",
        panel: "#13131a",
        accent: "#7c5cff",
        accent2: "#22d3ee",
      },
    },
  },
  plugins: [],
};
export default config;
