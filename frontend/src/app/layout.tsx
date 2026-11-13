import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Tech Job Radar | Seu próximo passo em tech",
  description: "Encontre vagas e organize seu currículo com base na sua experiência real.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="pt-BR"><body>{children}</body></html>;
}
