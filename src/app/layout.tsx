import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Allegis Catalog",
  description: "Find and review catalogued Allegis Drive files",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
