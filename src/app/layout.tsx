import type { Metadata } from "next";
import { Faculty_Glyphic, Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

// Datum family type (CAT-WO-02 item 1): Geist for text, Geist Mono for captions and codes, a serif for page titles.
const sans = Geist({ variable: "--font-sans", subsets: ["latin"], display: "swap" });
const mono = Geist_Mono({ variable: "--font-mono", subsets: ["latin"], display: "swap" });
const serif = Faculty_Glyphic({ variable: "--font-serif", subsets: ["latin"], weight: "400", display: "swap" });

export const metadata: Metadata = {
  title: "Allegis Catalog",
  description: "Find and review catalogued Allegis Drive files",
  robots: { index: false, follow: false },
  icons: { icon: "/allegis-emblem.svg" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable} ${serif.variable}`}>
      <body>{children}</body>
    </html>
  );
}
