import { SetupProvider } from "@/components/setup/setup-provider";

export default function SetupLayout({ children }: { children: React.ReactNode }) {
  return <SetupProvider>{children}</SetupProvider>;
}
