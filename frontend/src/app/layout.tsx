import type { Metadata } from "next";

import "./globals.css";

import { SiteHeader } from "@/components/SiteHeader";
import { DISCLAIMER } from "@/lib/court";

export const metadata: Metadata = {
  title: "Court Simulation - Republic of Arandia",
  description:
    "A visual courtroom dashboard for the multi-agent legal simulation. " +
    DISCLAIMER,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased">
        <SiteHeader />
        <main className="mx-auto w-full max-w-[1400px] px-4 pb-16 sm:px-6">
          {children}
        </main>
        <footer className="mx-auto w-full max-w-[1400px] px-4 pb-10 sm:px-6">
          <p className="border-t border-slate-800 pt-4 text-xs text-slate-500">
            {DISCLAIMER} The Republic of Arandia, its laws, cases, and parties
            are fictional.
          </p>
        </footer>
      </body>
    </html>
  );
}
