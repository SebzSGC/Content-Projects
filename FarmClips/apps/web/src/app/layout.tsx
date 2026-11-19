import type { Metadata } from "next";
import { Figtree, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { AppShell } from "@/components/TopNav";

// Astryx Neutral Studio Typography:
// - Figtree: clean geometric sans for UI, controls, and headings
// - JetBrains Mono: tabular monospace for timecodes, metrics, budgets, and paths
const figtree = Figtree({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-sans",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "FarmClips Studio — Tus mejores jugadas, listas para publicar",
  description:
    "Estudio profesional para convertir grabaciones de juego y cámara en Shorts verticales 9:16 con subtítulos dinámicos y edición inteligente a 60 fps.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="es"
      data-theme="dark"
      className={`${figtree.variable} ${jetbrainsMono.variable} dark`}
    >
      <body
        className={`${figtree.className} min-h-screen overflow-x-hidden bg-[var(--color-background-body)] text-[var(--color-text-primary)] antialiased`}
      >
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
