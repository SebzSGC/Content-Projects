import type { Metadata } from "next";
import "./globals.css";
import { TopNav } from "@/components/TopNav";

export const metadata: Metadata = {
  title: "ClipsApp — Arquitectura Híbrida (IA por API, Proceso Local)",
  description: "Pipeline local + IA por API para Shorts verticales Hormozi Gaming con Editor sobre EditPlan v2",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className="dark">
      <body className="min-h-screen bg-[#090A0F] text-zinc-100">
        <TopNav />
        <main className="mx-auto max-w-[1440px] px-5 py-6">{children}</main>
      </body>
    </html>
  );
}
