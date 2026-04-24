import type { Metadata } from "next";
import "./globals.css";
import { SiteHeader } from "@/components/shared/site-header";

export const metadata: Metadata = {
  title: "EchoClass",
  description: "EchoClass 课堂教案与课堂管理主页",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className="bg-slate-50 text-slate-900 antialiased">
        <SiteHeader />
        {children}
      </body>
    </html>
  );
}
