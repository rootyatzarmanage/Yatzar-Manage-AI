/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#EEF2FF',
          100: '#E0E7FF',
          400: '#5F75EE',
          500: '#465FFF',
          600: '#3C50E0',
          700: '#2A3FCD',
        },
        dark: {
          bg: '#0B1120',         // Deep obsidian background
          surface: '#0E172E',    // Sidebar / Header surface
          card: '#131E3D',       // TailAdmin Dark Card
          cardHover: '#172449',
          border: '#1E2C52',     // Crisp dark border
          borderLight: '#263765',
          text: '#FFFFFF',
          muted: '#8D9CB8',
          input: '#0F1832',
        },
        light: {
          bg: '#F1F5F9',
          card: '#FFFFFF',
          border: '#E2E8F0',
          text: '#1C2434',
          muted: '#64748B',
        },
        success: '#10B981',
        danger: '#EF4444',
        warning: '#F59E0B',
      },
      fontFamily: {
        sans: ['Inter', 'Outfit', 'sans-serif'],
      },
      boxShadow: {
        'tailadmin': '0px 8px 13px -3px rgba(0, 0, 0, 0.25)',
        'tailadmin-card': '0px 1px 3px 0px rgba(0, 0, 0, 0.2)',
        'tailadmin-dark': '0px 4px 20px -2px rgba(0, 0, 0, 0.4)',
      }
    },
  },
  plugins: [],
}
