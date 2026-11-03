import { Button, Tab, TabList } from "@fluentui/react-components";
import {
  DismissRegular,
  DocumentRegular,
  CubeRegular,
} from "@fluentui/react-icons";
import { DocumentRef } from "../project/types";
export function DocumentTabs({
  documents,
  active,
  select,
  close,
}: {
  documents: DocumentRef[];
  active: string;
  select(id: string): void;
  close(id: string): void;
}) {
  return (
    <div className="document-tabs">
      <TabList
        size="small"
        selectedValue={active}
        onTabSelect={(_, d) => select(String(d.value))}
        aria-label="文档标签"
      >
        {documents.map((doc) => (
          <div
            className={"document-tab " + (active === doc.id ? "active" : "")}
            key={doc.id}
          >
            <Tab
              value={doc.id}
              icon={doc.type === "cad" ? <CubeRegular /> : <DocumentRegular />}
            >
              {doc.title}
            </Tab>
            <Button
              size="small"
              appearance="subtle"
              icon={<DismissRegular />}
              aria-label={"关闭 " + doc.title}
              onClick={() => close(doc.id)}
            />
          </div>
        ))}
      </TabList>
    </div>
  );
}
