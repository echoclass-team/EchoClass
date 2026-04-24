import { SetupProvider } from "@/components/setup/setup-provider";

export default function LessonManageLayout({ children }: { children: React.ReactNode }) {
  return <SetupProvider>{children}</SetupProvider>;
}
