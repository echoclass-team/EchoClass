import Link from "next/link";

const navItems = [
  { href: "/", label: "首页" },
  { href: "/setup", label: "开始陪练" },
  { href: "/lessons/manage", label: "教案管理" },
];

export function SiteHeader() {
  return (
    <header className="border-b border-slate-200 bg-white/80 backdrop-blur">
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between px-6 sm:px-10 lg:px-12">
        <Link href="/" className="text-sm font-semibold tracking-[0.2em] text-slate-900 uppercase">
          EchoClass
        </Link>

        <nav className="flex items-center gap-6 text-sm text-slate-600">
          {navItems.map((item) => (
            <Link key={item.href} href={item.href} className="transition hover:text-slate-950">
              {item.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
