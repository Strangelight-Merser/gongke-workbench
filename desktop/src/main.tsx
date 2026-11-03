import { createRoot } from "react-dom/client";
import { AppShell } from "./app/AppShell";
import "./styles/tokens.css";
import "./styles/workspace.css";
import "./styles/documents.css";
import "./styles/agent.css";
createRoot(document.getElementById("root")!).render(<AppShell />);
