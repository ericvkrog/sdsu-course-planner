/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        sdsu: {
          red: "#A6192E",
          black: "#000000",
          gray: "#6B7280",
        },
      },
    },
  },
  plugins: [],
};
