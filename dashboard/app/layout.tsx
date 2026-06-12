import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Retail Trading System | Live Command Deck",
  description: "Professional live paper-trading command deck for the routed multi-sleeve system."
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
