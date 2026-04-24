"use client";

import { createContext, useContext } from "react";
import { useLessonLibraryState, useSetupDraftState } from "@/hooks/use-setup-state";

const SetupContext = createContext<ReturnType<typeof useSetupDraftState> & ReturnType<typeof useLessonLibraryState> | null>(null);

export function SetupProvider({ children }: { children: React.ReactNode }) {
  const draftState = useSetupDraftState();
  const libraryState = useLessonLibraryState();
  return <SetupContext.Provider value={{ ...draftState, ...libraryState }}>{children}</SetupContext.Provider>;
}

export function useSetup() {
  const value = useContext(SetupContext);
  if (!value) throw new Error("useSetup must be used within SetupProvider");
  return value;
}
