import type { Metadata } from "next";
import { Inter, Geist_Mono } from "next/font/google";
import "./globals.css";
import Providers from "./providers";

// FONT: decided to use a free font (Inter, via Google Fonts) rather than a
// licensed/paid typeface.
//
// TO SWAP THE FONT LATER: replace this whole block with:
//
//   import localFont from "next/font/local";
//   const urbane = localFont({
//     src: [
//       { path: "./fonts/Urbane-Regular.woff2", weight: "400", style: "normal" },
//       { path: "./fonts/Urbane-Medium.woff2", weight: "500", style: "normal" },
//       { path: "./fonts/Urbane-Bold.woff2", weight: "700", style: "normal" },
//     ],
//     variable: "--font-urbane-placeholder",
//   });
//
// No other file needs to change — every className using font-display
// (via globals.css's --font-display token) updates automatically.
const urbane = Inter({
  variable: "--font-urbane-placeholder",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "TBE Workbench",
  description: "AI-Assisted Technical Bid Evaluation",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${urbane.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-background text-foreground">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
