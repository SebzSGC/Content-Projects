import { Nunito } from "next/font/google";

// Rounded, friendly type for the gaming studio; loaded by next/font (self-hosted at build).
const nunito = Nunito({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800", "900"],
  display: "swap",
});

// Soft dark surface for the whole /sessions area: slate instead of pure black,
// with two blurred glows behind the glass cards.
export default function GamingStudioLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className={`${nunito.className} relative isolate min-h-[calc(100vh-3.5rem)] overflow-hidden bg-slate-950 text-slate-100`}>
      <div aria-hidden className="pointer-events-none absolute -top-40 -left-32 -z-10 h-[28rem] w-[28rem] rounded-full bg-amber-500/10 blur-3xl" />
      <div aria-hidden className="pointer-events-none absolute top-1/3 -right-40 -z-10 h-[32rem] w-[32rem] rounded-full bg-indigo-500/10 blur-3xl" />
      {children}
    </div>
  );
}
