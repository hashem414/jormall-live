import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { headers } from "next/headers";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export async function generateMetadata():Promise<Metadata>{
  const h=await headers(); const host=h.get("x-forwarded-host")??h.get("host")??"localhost:5040"; const protocol=h.get("x-forwarded-proto")??(host.startsWith("localhost")?"http":"https"); const base=new URL(`${protocol}://${host}`);
  return {metadataBase:base,title:"Nova — AI Division Operations",description:"Plan AI projects, balance specialist capacity, manage delivery risk and report outcomes from one trusted operating system.",icons:{icon:"/favicon.svg",shortcut:"/favicon.svg"},openGraph:{title:"Nova — AI Division Operations",description:"From project brief to delivered outcome.",type:"website",images:[{url:new URL("/og.png",base),width:1200,height:630,alt:"Nova AI Division Operations"}]},twitter:{card:"summary_large_image",title:"Nova — AI Division Operations",description:"From project brief to delivered outcome.",images:[new URL("/og.png",base)]}};
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body className={`${geistSans.variable} ${geistMono.variable}`}>{children}</body></html>;
}
