import { Space_Grotesk, IBM_Plex_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const displayFont = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-display"
});

const monoFont = IBM_Plex_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500"]
});

export const metadata = {
  title: "Esyy Tesla Connector Dashboard",
  description: "Read-only monitoring dashboard for inverter and controller data."
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className={`${displayFont.variable} ${monoFont.variable}`}>
        <div className="bg-layer" />
        <header className="top-nav">
          <div className="brand">
            <div className="brand-dot" />
            <span>Esyy Tesla Connector</span>
          </div>
          <nav className="nav-links">
            <Link href="/dashboard">Dashboard</Link>
            <Link href="/history">History</Link>
          </nav>
        </header>
        <main className="main-content">{children}</main>
      </body>
    </html>
  );
}
