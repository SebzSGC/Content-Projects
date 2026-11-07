import type { Metadata } from "next";
import { Nunito } from "next/font/google";
import "./globals.css";
import { TopNav } from "@/components/TopNav";

// Rounded, friendly type for the whole studio; next/font self-hosts it at build time.
const nunito = Nunito({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800", "900"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "ClipsApp — Arquitectura Híbrida (IA por API, Proceso Local)",
  description: "Pipeline local + IA por API para Shorts verticales Hormozi Gaming con Editor sobre EditPlan v2",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className="dark">
      <body className={`${nunito.className} relative isolate min-h-screen overflow-x-hidden bg-slate-950 text-slate-100`}>
        {/* Two soft glows behind the glass cards: depth without pure black. */}
        <div aria-hidden className="pointer-events-none fixed -top-40 -left-32 -z-10 h-[28rem] w-[28rem] rounded-full bg-amber-500/10 blur-3xl" />
        <div aria-hidden className="pointer-events-none fixed top-1/3 -right-40 -z-10 h-[32rem] w-[32rem] rounded-full bg-indigo-500/10 blur-3xl" />
        <TopNav />
        <main className="mx-auto max-w-[1440px] px-4 py-8 sm:px-6">{children}</main>
      </body>
    </html>
  );
}
