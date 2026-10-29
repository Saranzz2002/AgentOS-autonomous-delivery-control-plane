import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "AgentOS — Software Delivery Workspace",
    template: "%s · AgentOS",
  },
  description: "Plan, implement, test, and review software changes with human approval at the ship gate.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
